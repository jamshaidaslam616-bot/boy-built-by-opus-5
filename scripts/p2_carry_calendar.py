"""Is it worth going flat over the triple-swap night?

A measured, actionable question rather than a general hunt for seasonality.

This broker charges 3x financing on Wednesday's rollover (MT5 `swap_rollover3days`
= 3, and its weekday enum starts at Sunday). A long lot pays -$52.38 on a normal
night and -$157.14 on that one. Against a $434k notional that extra charge is about
2.4 bp, every week, on any long position that stays open.

Getting flat avoids it — but costs a round trip (~0.37 bp measured) and gives up
whatever Wednesday-to-Thursday was going to do. Whether that trade is worth making
is arithmetic, not opinion, so here is the arithmetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.metrics import sharpe_ratio, summarise  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, turnover, vol_target  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
BARS_PER_YEAR = 260.0

SWAP_LONG_PER_LOT_NIGHT = -52.38   # MEASURED 2026-08-08
NOTIONAL_PER_LOT = 434_233.20      # MEASURED 2026-08-08
TRIPLE_SWAP_WEEKDAY = 2            # pandas: Monday=0, so 2 = Wednesday
ROUND_TRIP_BP = 0.47               # 0.12 spread + 0.25 commission + 0.10 slippage


def costs(carry_long: float = -5.66) -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=carry_long, carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR,
    )


def main() -> int:
    close = hist.load(ROOT, "XAUUSD", "D1")["close"]
    rets = close.pct_change().dropna()

    print("=" * 92)
    print("THE TRIPLE-SWAP NIGHT — is going flat worth it?")
    print("=" * 92)

    normal_bp = abs(SWAP_LONG_PER_LOT_NIGHT) / NOTIONAL_PER_LOT * 10_000
    extra_bp = normal_bp * 2  # 3x night = two extra nights
    print(f"  normal night financing     {normal_bp:.3f} bp of notional")
    print(f"  triple night, extra charge {extra_bp:.3f} bp")
    print(f"  round trip to get flat     {ROUND_TRIP_BP:.3f} bp")
    print(f"  -> gross saving per week   {extra_bp - ROUND_TRIP_BP:+.3f} bp")
    print(f"  -> annualised (52 weeks)   {(extra_bp - ROUND_TRIP_BP) * 52 / 100:+.3f} % of notional")

    # What is actually given up: the Wednesday-to-Thursday move.
    print("\n  What we would give up — the move over that night")
    print("  " + "-" * 88)
    print(f"    {'weekday':<12} {'n':>5} {'mean %':>9} {'t':>7} {'ann. contribution %':>21}")
    for wd, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri")):
        grp = rets[rets.index.weekday == wd]
        if len(grp) < 30:
            continue
        t = stats.ttest_1samp(grp, 0.0).statistic
        marker = "   <-- triple swap night" if wd == TRIPLE_SWAP_WEEKDAY else ""
        print(f"    {name:<12} {len(grp):>5} {grp.mean() * 100:>+9.4f} {t:>+7.2f} "
              f"{grp.mean() * len(grp) / (len(rets) / BARS_PER_YEAR) * 100:>+20.3f}%{marker}")

    print("\n  Day-of-week means are a classic multiple-comparisons trap: five cells means")
    print("  one |t| near 2 is expected from chance. These are reported to size what is")
    print("  given up, NOT as a signal.")

    # The honest test: same strategy, with and without the Wednesday-night exit.
    print("\n" + "=" * 92)
    print("MEASURED — the 200-day baseline, with and without flattening for that night")
    print("=" * 92)

    above = (close > close.rolling(200, min_periods=200).mean()).astype(float)
    held = vol_target(above, close, 0.10, 60, BARS_PER_YEAR)

    # Go flat on the bar whose CLOSE precedes the triple-swap rollover.
    flat_wed = held.copy()
    flat_wed[flat_wed.index.weekday == TRIPLE_SWAP_WEEKDAY] = 0.0

    rows = []
    for label, pos in (("hold through", held), ("flat over triple night", flat_wed)):
        net = strategy_returns(pos, close, costs())
        perf = summarise(net, BARS_PER_YEAR, turnover(pos))
        rows.append((label, perf))
        print(f"  {label:<26} return {perf.ann_return_pct:+6.2f}%  "
              f"Sharpe {perf.sharpe:+.3f}  maxDD {perf.max_drawdown_pct:5.2f}%  "
              f"turnover {perf.turnover_per_year:5.0f}/yr")

    delta_sharpe = rows[1][1].sharpe - rows[0][1].sharpe
    delta_return = rows[1][1].ann_return_pct - rows[0][1].ann_return_pct
    print(f"\n  difference: {delta_return:+.2f}% return, {delta_sharpe:+.3f} Sharpe")

    # A carry-free control isolates whether any gain is financing or price.
    print("\n  Control — the same comparison with financing switched OFF:")
    free = costs(carry_long=0.0)
    a = sharpe_ratio(strategy_returns(held, close, free), BARS_PER_YEAR)
    b = sharpe_ratio(strategy_returns(flat_wed, close, free), BARS_PER_YEAR)
    print(f"    hold through {a:+.3f}   flat over night {b:+.3f}   difference {b - a:+.3f}")
    print()
    print("    With financing off, flattening can only LOSE (it forfeits a day's move and")
    print("    pays a round trip). If the difference flips positive once financing is on,")
    print("    the gain is genuinely the avoided charge and not a price effect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
