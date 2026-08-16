"""The shipped strategy. Parameters are FROZEN and a test enforces that.

Cross-sectional momentum across 19 instruments: hold the seven strongest against
the seven weakest, in equal risk, rebalanced weekly.

**What this is, honestly.** It is the best of roughly seventy pre-registered
parameter combinations tested across twenty hypotheses, and it did NOT clear its
random-entry control (z = +0.56 against a +2.00 bar). Its measured Sharpe of 0.395
would need 25.6 years of data to establish; the test window held 6.5. So it is not a
validated edge, and nothing downstream of this file is permitted to describe it as
one.

**Why ship it anyway.** Because the only remaining way to answer the question is to
accumulate out-of-sample observations, and that clock does not start until the
system runs. Paper trading costs nothing, risks nothing, and produces exactly the
data that is missing.

**Why the parameters are frozen.** Every re-tune spends statistical budget that the
deflated Sharpe already charges against this candidate. Changing a number here after
seeing live results would convert an honest forward test into another in-sample fit,
which is the failure mode this entire project was built to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- FROZEN
# Locked 2026-08-14 from P15. Do not edit. A test asserts these exact values.
LOOKBACK_BARS = 120
LEGS_PER_SIDE = 7
REBALANCE_BARS = 5          # weekly — inside the broker-confirmed 7-day free window
VOL_LOOKBACK_BARS = 60
MAX_LEG_WEIGHT = 0.25       # no single market may exceed a quarter of gross exposure

# Widened from 19 to 25 on 2026-08-16 after P19 measured that breadth helps at the
# capital levels that matter: Sharpe +0.357 -> +0.440 at $30k and +0.421 -> +0.499 at
# $100k. It does NOT help at $10k, where only 12 markets clear their minimum lot and a
# wider list just produces more unfillable legs.
#
# US single stocks were considered and rejected on measurement, not preference: ten US
# large caps correlate at +0.308 with each other against +0.070 across this universe,
# so ninety of them would contribute about 3.2 effective independent bets where these
# 25 already contribute 9.3 — while adding dividend and corporate-action handling and
# roughly 4x the spread.
UNIVERSE = (
    # FX majors
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    # FX scandies and EM
    "USDNOK", "USDSEK", "USDMXN", "USDZAR", "USDPLN", "USDSGD", "USDCNH",
    # Precious metals
    "XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD",
    # Energy
    "USOIL", "UKOIL",
    # Indices
    "US500", "USTEC", "US30",
    # Crypto
    "BTCUSD", "ETHUSD",
)

# Measured, not assumed. Sources in COSTS.md and FINDINGS.md.
MEASURED = {
    "control_z": 0.78,          # P19, 25 markets at $100k, lot-constrained
    "control_bar": 2.00,
    "sharpe": 0.499,
    "years_to_prove": 16.1,
    "years_tested": 6.5,
    "usd_per_year_at_100k": 3395.0,
    "mean_pairwise_correlation": 0.070,
    "effective_independent_bets": 9.3,
}

# Capital thresholds, measured in P17. Below these a leg simply cannot be expressed,
# which is what made an earlier $10,000 backtest fictional (F18).
CAPITAL_ALL_TRADEABLE = 100_000
CAPITAL_MINIMUM_SENSIBLE = 30_000

VALIDATION_STATUS = (
    "NOT VALIDATED — control z = +0.78 against a +2.00 bar. This is the best of roughly "
    "eighty pre-registered combinations and it is not distinguishable from a rotation of "
    "itself. Establishing a Sharpe of 0.499 needs about 16 years of data; the test window "
    "held 6.5. Every figure this produces is an experiment in progress, not a forecast."
)


@dataclass(frozen=True)
class Target:
    """What the book should hold, as a fraction of gross exposure."""

    symbol: str
    weight: float
    """Signed. Positive is long. The absolute values across all targets sum to 1.0."""

    rank: int
    trailing_return: float


def compute_targets(closes: pd.DataFrame, as_of: pd.Timestamp | None = None) -> list[Target]:
    """Rank the universe and return the book to hold over the NEXT bar.

    ``closes`` must be a panel of daily closes indexed by timestamp, one column per
    symbol, with no data after ``as_of``. The caller is responsible for that; this
    function reads the last row and does not look beyond it.
    """
    if as_of is not None:
        closes = closes.loc[:as_of]

    missing = [s for s in UNIVERSE if s not in closes.columns]
    if missing:
        raise ValueError(f"universe incomplete, missing: {missing}")

    panel = closes[list(UNIVERSE)]
    if len(panel) < max(LOOKBACK_BARS, VOL_LOOKBACK_BARS) + 1:
        raise ValueError(
            f"need at least {max(LOOKBACK_BARS, VOL_LOOKBACK_BARS) + 1} bars, got {len(panel)}"
        )

    trailing = (panel.iloc[-1] / panel.iloc[-1 - LOOKBACK_BARS] - 1.0)
    vol = panel.pct_change().rolling(VOL_LOOKBACK_BARS).std().iloc[-1]

    usable = trailing.dropna().index.intersection(vol[vol > 0].dropna().index)
    if len(usable) < LEGS_PER_SIDE * 2:
        raise ValueError(
            f"only {len(usable)} markets have usable data; need {LEGS_PER_SIDE * 2}"
        )

    ranked = trailing[usable].sort_values(ascending=False)
    longs, shorts = ranked.index[:LEGS_PER_SIDE], ranked.index[-LEGS_PER_SIDE:]

    raw: dict[str, float] = {}
    for i, symbol in enumerate(longs):
        raw[symbol] = 1.0 / float(vol[symbol])
    for i, symbol in enumerate(shorts):
        raw[symbol] = -1.0 / float(vol[symbol])

    gross = sum(abs(w) for w in raw.values())
    if gross <= 0:
        raise ValueError("all weights are zero; refusing to produce a book")

    # Normalise to unit gross, then cap any single leg. Capping is a safety rule,
    # not a tuned parameter: one market blowing out its volatility estimate must not
    # be able to become the whole book.
    weights = {s: w / gross for s, w in raw.items()}
    weights = {s: float(np.clip(w, -MAX_LEG_WEIGHT, MAX_LEG_WEIGHT)) for s, w in weights.items()}
    gross = sum(abs(w) for w in weights.values())
    weights = {s: w / gross for s, w in weights.items()}

    order = {s: i for i, s in enumerate(ranked.index)}
    return sorted(
        (Target(symbol=s, weight=w, rank=order[s] + 1, trailing_return=float(trailing[s]))
         for s, w in weights.items()),
        key=lambda t: t.rank,
    )


def is_rebalance_day(bar_index: int) -> bool:
    """Weekly grid. Between rebalances the book is held, not re-derived."""
    return bar_index % REBALANCE_BARS == 0
