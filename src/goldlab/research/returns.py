"""The position/return contract.

Every strategy in this project is a function from bars to a **position series**.
Nothing returns a trade list, and nothing computes its own P&L.

The contract, stated once:

    position[t]  is the exposure HELD OVER bar t+1,
                 decided using only information available at the CLOSE of bar t.

So the strategy's return in bar t+1 is ``position[t] * asset_return[t+1]``, which
this module writes as ``position.shift(1) * asset_return``.

That single shift is the whole anti-look-ahead design. A strategy physically cannot
trade on bar t's close using bar t's close-to-close return, because the framework —
not the strategy — applies the lag. The most expensive bug class in retail backtests
is removed by construction rather than by vigilance.

Costs are charged on **turnover**, which is derived from the position series, so a
strategy also cannot forget to pay for its own trading.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    """Round-trip costs, expressed in basis points of notional traded.

    Defaults are deliberately absent. A cost model must be constructed from
    measured figures (see ``COSTS.md``); there is no "sensible default" that is
    not also a way to silently inflate every result.
    """

    spread_bp: float
    """Cost of one full round trip crossing the spread, in bp of notional."""

    commission_bp: float
    """Round-trip commission, in bp of notional."""

    slippage_bp: float
    """Assumed execution slippage per round trip, in bp of notional."""

    carry_long_annual_pct: float
    """Financing on a long position, % of notional per year. Negative = we pay."""

    carry_short_annual_pct: float
    """Financing on a short position, % of notional per year. Negative = we pay."""

    bars_per_year: float
    """Used to convert annual carry into a per-bar charge."""

    multiplier: float = 1.0
    """Stress factor. D10's cost-sensitivity check runs this at 1.5."""

    @property
    def round_trip_bp(self) -> float:
        return (self.spread_bp + self.commission_bp + self.slippage_bp) * self.multiplier

    def scaled(self, multiplier: float) -> "CostModel":
        return CostModel(
            spread_bp=self.spread_bp,
            commission_bp=self.commission_bp,
            slippage_bp=self.slippage_bp,
            carry_long_annual_pct=self.carry_long_annual_pct,
            carry_short_annual_pct=self.carry_short_annual_pct,
            bars_per_year=self.bars_per_year,
            multiplier=multiplier,
        )


def asset_returns(close: pd.Series) -> pd.Series:
    """Simple close-to-close returns. First bar is NaN and stays NaN."""
    if not isinstance(close.index, pd.DatetimeIndex):
        raise TypeError("close must be indexed by DatetimeIndex")
    if not close.index.is_monotonic_increasing:
        raise ValueError("close index must be sorted ascending")
    if close.index.has_duplicates:
        raise ValueError("close index contains duplicate timestamps")
    return close.pct_change()


def turnover(position: pd.Series) -> pd.Series:
    """Fraction of notional traded at each bar.

    ``|Δposition|`` — going from flat to full long is 1.0 of turnover, and a
    reversal from -1 to +1 is 2.0, which is correct: it is two round trips' worth
    of notional crossing the spread.
    """
    pos = position.fillna(0.0)
    prev = pos.shift(1).fillna(0.0)  # we start flat, so the first bar's turnover is |pos[0]|
    return (pos - prev).abs()


ROLLOVER_HOUR_UTC = 0
"""Server midnight, when this broker books the overnight financing."""

TRIPLE_SWAP_WEEKDAY = 2
"""Wednesday (pandas Monday=0). Measured: `swap_rollover3days` = 3 with MT5's
0=Sunday enum. Positions held across this rollover pay three nights, not one."""


def _carry_per_bar(position: pd.Series, costs: CostModel) -> pd.Series:
    """Financing charged per bar, as a return, signed by which side is held.

    **Charged at the rollover, not smeared across every bar.** Swap is booked once
    a night at server midnight; a position opened at 09:00 and closed at 17:00 pays
    none of it. Spreading the annual rate evenly over all bars is correct only for a
    position that is always open, and it silently penalises exactly the strategy
    that avoids the charge — which is how a first version of this scored a
    flat-overnight day-trading variant as paying 3.77% a year in swap it would
    never actually have owed.

    On a daily series each bar spans one rollover, so this reduces to the old
    behaviour. On intraday bars it does not.
    """
    long_leg = position.clip(lower=0.0)
    short_leg = (-position).clip(lower=0.0)

    index = position.index
    # The MEDIAN gap, not the first one. Taking the first two bars reads a weekend
    # gap as the bar length, which sends hourly data down the daily branch and
    # charges one night per bar — 6,240 nights a year instead of 260. That mistake
    # turned a +0.75% strategy into -22.64% and looked like a real result.
    if len(index) > 2:
        bar_hours = float(np.median(np.diff(index.asi8)) / 3.6e12)
    else:
        bar_hours = 24.0

    if bar_hours >= 24.0:
        # One bar, one night. Nights per bar is 1, plus the triple-swap extra.
        nights = pd.Series(1.0, index=index)
        nights[index.weekday == TRIPLE_SWAP_WEEKDAY] = 3.0
    else:
        # Only bars that cross server midnight are charged, and they carry the whole
        # night's financing rather than a fraction of it.
        crosses = pd.Series(0.0, index=index)
        is_rollover = index.hour == ROLLOVER_HOUR_UTC
        crosses[is_rollover] = 1.0
        crosses[is_rollover & (index.weekday == TRIPLE_SWAP_WEEKDAY)] = 3.0
        nights = crosses

    # Annual rates are quoted over 469 nights (365 plus 52 triple rollovers), so a
    # single night costs the annual figure divided by 469.
    long_per_night = costs.carry_long_annual_pct / 100.0 / 469.0
    short_per_night = costs.carry_short_annual_pct / 100.0 / 469.0

    return nights * (long_leg * long_per_night + short_leg * short_per_night)


def strategy_returns(
    position: pd.Series,
    close: pd.Series,
    costs: CostModel | None = None,
) -> pd.Series:
    """Net per-bar returns of holding ``position``.

    The ``shift(1)`` here is the load-bearing line of the whole project.
    """
    if not position.index.equals(close.index):
        raise ValueError("position and close must share an index")

    pos = position.fillna(0.0)
    gross = pos.shift(1) * asset_returns(close)

    if costs is None:
        return gross.fillna(0.0)

    # Turnover is charged in the bar where the position CHANGES, i.e. at the same
    # timestamp the new position is established — not shifted, because the trade
    # happens at that bar's close alongside the decision.
    trade_cost = turnover(pos) * (costs.round_trip_bp / 10_000.0)
    carry = _carry_per_bar(pos.shift(1).fillna(0.0), costs)

    return (gross - trade_cost + carry).fillna(0.0)


def equity_curve(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    return initial * (1.0 + returns.fillna(0.0)).cumprod()


def vol_target(
    raw_position: pd.Series,
    close: pd.Series,
    target_annual_vol: float,
    lookback: int,
    bars_per_year: float,
    max_leverage: float = 2.0,
) -> pd.Series:
    """Scale a position so realised volatility sits near ``target_annual_vol``.

    This is a sizing rule, not a signal. It is the single most reliable Sharpe
    improver in the literature and it is applied to every candidate, so that no
    strategy wins the bake-off merely by having been sized more aggressively.

    The volatility estimate uses only data up to and including bar t, and is then
    shifted by one bar so the size applied over bar t+1 cannot use bar t+1's own
    volatility.
    """
    if target_annual_vol <= 0:
        raise ValueError("target_annual_vol must be positive")
    if lookback < 2:
        raise ValueError("lookback must be at least 2 bars")

    realised = asset_returns(close).rolling(lookback, min_periods=lookback).std()
    annualised = realised * np.sqrt(bars_per_year)
    scale = (target_annual_vol / annualised).clip(upper=max_leverage)
    return (raw_position * scale.shift(1)).fillna(0.0)
