"""Candidate strategies. Every one returns a position series, nothing else.

The contract (see ``research.returns``): ``position[t]`` is the exposure held over
bar t+1, decided from information available at bar t's close. The framework applies
the one-bar lag, so no strategy here shifts anything itself — and none of them can
peek, by construction rather than by care.

**Sizing lives outside.** Nothing here decides how big to be; every candidate is
volatility-targeted by the runner. That way no strategy wins the bake-off by having
been sized more aggressively than its rivals.

**A note on shorts on this venue.** Financing is -5.66%/yr on longs and exactly
0.00% on shorts (COSTS.md). A long/short strategy therefore gets a structural
advantage on its short leg that has nothing to do with gold. Any candidate whose
edge comes from that will be labelled as reflecting this broker's rate card, not a
market insight — the runner reports the long/short split for exactly this reason.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _finite(series: pd.Series) -> pd.Series:
    return series.replace([np.inf, -np.inf], np.nan).fillna(0.0)


# --------------------------------------------------------------- A1: trend

def a1_timeseries_momentum(close: pd.Series, lookback: int) -> pd.Series:
    """Long if the last ``lookback`` bars were up, short if down.

    The canonical time-series momentum rule — the only price-only family with
    published out-of-sample survival across a century (Moskowitz et al.).
    """
    return _finite(np.sign(close / close.shift(lookback) - 1.0))


def a1_ma_crossover(close: pd.Series, fast: int, slow: int) -> pd.Series:
    """Long above the slow average, short below, gated by the fast one."""
    if fast >= slow:
        raise ValueError("fast window must be shorter than slow")
    fast_ma = close.rolling(fast, min_periods=fast).mean()
    slow_ma = close.rolling(slow, min_periods=slow).mean()
    return _finite(np.sign(fast_ma - slow_ma))


def a1_confidence_trend(close: pd.Series, span: int, momentum_lookback: int) -> pd.Series:
    """Trend strength as a bounded exposure, not a binary flip.

    Follows the structure of the published gold-futures result: an EMA of log price
    turned into a z-score, mapped to a bounded confidence, then blended with a
    slower momentum check. Positions scale with conviction instead of jumping
    between full long and full short, which cuts turnover — and turnover is what
    an $11/lot open-charge commission punishes.
    """
    log_px = np.log(close)
    ema = log_px.ewm(span=span, adjust=False).mean()
    deviation = log_px - ema
    z = deviation / deviation.rolling(span * 2, min_periods=span * 2).std()

    confidence = np.tanh(z)  # bounded to [-1, 1], smooth, no free parameter
    momentum = np.sign(close / close.shift(momentum_lookback) - 1.0)
    return _finite(0.6 * confidence + 0.4 * momentum)


# ------------------------------------------------- A10: volatility breakout

def a10_volatility_breakout(
    high: pd.Series, low: pd.Series, close: pd.Series, channel: int, atr_window: int,
    atr_low_pct: float, atr_high_pct: float,
) -> pd.Series:
    """Break of an N-day channel, taken only when volatility is in a usable band.

    Uses the bar CLOSE against the PRIOR bars' channel — an intrabar touch would be
    look-ahead, and it is the single most common way breakout backtests lie.

    Too little volatility means the move cannot cover its own costs; too much means
    a news spike where fills are unpredictable. Both are skipped.
    """
    prior_high = high.shift(1).rolling(channel, min_periods=channel).max()
    prior_low = low.shift(1).rolling(channel, min_periods=channel).min()

    true_range = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = true_range.rolling(atr_window, min_periods=atr_window).mean()
    atr_rank = atr.rolling(252, min_periods=252).rank(pct=True)
    tradeable = (atr_rank >= atr_low_pct) & (atr_rank <= atr_high_pct)

    raw = pd.Series(0.0, index=close.index)
    raw[close > prior_high] = 1.0
    raw[close < prior_low] = -1.0
    # Hold the last signal until the opposite one fires; a breakout system that
    # exits on the next bar is a scalper wearing a trend system's clothes.
    held = raw.replace(0.0, np.nan).ffill().fillna(0.0)
    return _finite(held.where(tradeable, 0.0))


# ------------------------------- B1 / B2: macro as SLOW REGIME LEVELS only

def b1_real_yield_regime(real_yield: pd.Series, lookback: int) -> pd.Series:
    """Long gold while the real yield's own multi-month trend is falling.

    Deliberately a LEVEL trend, not a change. FINDINGS F5 showed the daily change
    in real yields co-moves with gold at -0.33 on the same date but at -0.03 once
    only published data is used — the relationship is real and untradeable as a
    trigger. A slow state ("real yields have been falling for a quarter") moves too
    slowly for a 4-day publication lag to destroy, so that is the only version
    tested here.
    """
    trend = real_yield - real_yield.rolling(lookback, min_periods=lookback).mean()
    return _finite(-np.sign(trend))


def b2_dollar_regime(dollar: pd.Series, lookback: int) -> pd.Series:
    """Long gold while the broad dollar's multi-month trend is falling. Same logic as B1."""
    trend = dollar - dollar.rolling(lookback, min_periods=lookback).mean()
    return _finite(-np.sign(trend))


def combine_gate(signal: pd.Series, gate: pd.Series) -> pd.Series:
    """Take the signal only when the gate agrees; otherwise stand aside.

    Standing aside is not neutral on this venue — it also stops paying -5.66%/yr
    financing, which BASELINE.md showed is roughly half of a trend filter's measured
    value here. The runner reports that split so a rate-card effect is never
    presented as a market insight.
    """
    agree = np.sign(signal) == np.sign(gate)
    return _finite(signal.where(agree, 0.0))


# ------------------------------------------------- B3: gold / silver spread

def b3_ratio_reversion(
    gold: pd.Series, silver: pd.Series, lookback: int, entry_z: float
) -> pd.Series:
    """Fade stretched gold/silver ratios. Returns exposure to the GOLD leg.

    The silver leg is the mirror, so this is a two-legged position and on this
    broker BOTH directions pay roughly -5.7%/yr, because the short leg earns no
    financing credit (COSTS.md). It is tested anyway — with financing reported
    separately — because on futures the short leg earns that carry back and the
    pair is close to carry-neutral. The question worth answering is whether the
    idea has merit at all; the venue question follows only if it does.
    """
    ratio = np.log(gold / silver)
    mean = ratio.rolling(lookback, min_periods=lookback).mean()
    sd = ratio.rolling(lookback, min_periods=lookback).std()
    z = (ratio - mean) / sd.where(sd > 0)

    raw = pd.Series(0.0, index=gold.index)
    raw[z > entry_z] = -1.0   # gold rich versus silver -> short gold
    raw[z < -entry_z] = 1.0   # gold cheap -> long gold
    # Hold until the stretch closes, rather than flipping every bar.
    held = raw.replace(0.0, np.nan).where(z.abs() > 0.5).ffill().fillna(0.0)
    return _finite(held)
