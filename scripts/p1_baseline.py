"""The honest baseline: what could you get WITHOUT a bot?

The question a trading system has to answer is not "did it make money" but "did it
beat the simple thing anyone could have done instead". Most retail bots never run
this comparison, which is why so many of them are elaborate ways to underperform
holding the asset.

The number produced here is written down BEFORE any strategy is tested, so it
cannot be quietly chosen afterwards to be one a candidate happens to clear.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.metrics import summarise  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, turnover, vol_target  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
BARS_PER_YEAR = 260.0
TARGET_VOL = 0.10
VOL_LOOKBACK = 60

# Spread is charged as a flat, conservative assumption rather than read per bar.
# The archive's own spread column records ZERO on 32% of D1 bars (see the quality
# gate), and a zero spread makes a trade free — which manufactures edge out of a
# data artefact. A single honest assumption beats a dishonest measurement.
SPREAD_BP = 0.12          # ~50 points on ~$434k notional; PROVISIONAL, market was shut
COMMISSION_BP = 0.25      # $11.00/lot round turn, owner-supplied, unverified
SLIPPAGE_BP = 0.10        # assumption; no tick data yet
CARRY_LONG_PCT = -5.66    # MEASURED 2026-08-08
CARRY_SHORT_PCT = 0.0     # MEASURED 2026-08-08


def costs(with_carry: bool = True) -> CostModel:
    return CostModel(
        spread_bp=SPREAD_BP,
        commission_bp=COMMISSION_BP,
        slippage_bp=SLIPPAGE_BP,
        carry_long_annual_pct=CARRY_LONG_PCT if with_carry else 0.0,
        carry_short_annual_pct=CARRY_SHORT_PCT if with_carry else 0.0,
        bars_per_year=BARS_PER_YEAR,
    )


def show(label: str, position: pd.Series, close: pd.Series, cost: CostModel) -> dict:
    net = strategy_returns(position, close, cost)
    perf = summarise(net, BARS_PER_YEAR, turnover(position))
    print(
        f"  {label:<40} return {perf.ann_return_pct:+7.2f}%  vol {perf.ann_vol_pct:5.2f}%  "
        f"Sharpe {perf.sharpe:+6.3f}  maxDD {perf.max_drawdown_pct:6.2f}%"
    )
    return {"label": label, "perf": perf}


def main() -> int:
    df = hist.load(ROOT, "XAUUSD", "D1")
    close = df["close"]
    print("=" * 100)
    print("HONEST BASELINE — XAUUSD D1")
    print("=" * 100)
    print(f"  {len(close):,} bars, {close.index[0]:%Y-%m-%d} .. {close.index[-1]:%Y-%m-%d}")
    print(f"  gold went from ${close.iloc[0]:,.2f} to ${close.iloc[-1]:,.2f} "
          f"({(close.iloc[-1] / close.iloc[0] - 1) * 100:+.1f}% over the period)")

    flat_long = pd.Series(1.0, index=close.index)
    sized_long = vol_target(flat_long, close, TARGET_VOL, VOL_LOOKBACK, BARS_PER_YEAR)

    # A 200-day trend overlay: hold gold only while it is above its own long average.
    # The simplest possible "system" — the thing a person with no bot might do.
    above_trend = (close > close.rolling(200, min_periods=200).mean()).astype(float)
    sized_trend = vol_target(above_trend, close, TARGET_VOL, VOL_LOOKBACK, BARS_PER_YEAR)

    print()
    print("  WITHOUT financing — what OWNING gold would have given you")
    print("  " + "-" * 96)
    free = costs(with_carry=False)
    show("buy and hold, unsized", flat_long, close, free)
    show(f"buy and hold, vol-targeted to {TARGET_VOL:.0%}", sized_long, close, free)
    show(f"200d trend overlay, vol-targeted to {TARGET_VOL:.0%}", sized_trend, close, free)

    print()
    print("  WITH this broker's financing — what the CFD account actually gives you")
    print("  " + "-" * 96)
    paid = costs(with_carry=True)
    b1 = show("buy and hold, unsized", flat_long, close, paid)
    b2 = show(f"buy and hold, vol-targeted to {TARGET_VOL:.0%}", sized_long, close, paid)
    b3 = show(f"200d trend overlay, vol-targeted to {TARGET_VOL:.0%}", sized_trend, close, paid)

    benchmark = max(b1["perf"].sharpe, b2["perf"].sharpe, b3["perf"].sharpe)
    winner = max((b1, b2, b3), key=lambda b: b["perf"].sharpe)

    print()
    print("=" * 100)
    print("THE NUMBER TO BEAT")
    print("=" * 100)
    print(f"  Best no-bot baseline: {winner['label']}")
    print(f"  Sharpe = {benchmark:+.3f}   (net of this broker's costs and financing)")
    print()
    print("  Any candidate strategy must beat this Sharpe, on out-of-sample data,")
    print("  after the same costs. Written down now, before any candidate exists.")
    print()
    print("  Note the financing drag: holding gold long on this account costs")
    print(f"  {abs(CARRY_LONG_PCT):.2f}% of notional per year before the price moves at all.")
    print("  A long-biased strategy starts that far behind; a short-biased one does not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
