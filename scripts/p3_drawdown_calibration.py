"""At what size does gold trend-following actually respect the owner's risk limits?

P3 surfaced an inconsistency I had not noticed: **the baseline itself fails the
gauntlet's drawdown gate.** BASELINE.md reports a 24.36% maximum drawdown for the
200-day overlay at a 10% volatility target, against a 15% backtest limit and a 10%
live limit. So the bar to beat on Sharpe was set by a strategy that would be
rejected on risk.

The gate is not the thing to change — it is the owner's. What has to change is the
size. This measures the size that actually complies, and what return that leaves.

The answer here is the honest headline of the whole project so far, because it
converts "does gold trend-following work" into "what does it pay at a risk level
this owner accepted".
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
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0

LIVE_DD_LIMIT = 10.0      # owner-set, hard stop
BACKTEST_DD_LIMIT = 15.0  # owner-set acceptance threshold


def costs() -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR,
    )


def main() -> int:
    close = hist.load(ROOT, "XAUUSD", "D1")["close"]

    # The baseline (long or flat) and the best P3 survivor-by-Sharpe (long or short).
    long_flat = (close > close.rolling(200, min_periods=200).mean()).astype(float)
    long_short = C.a1_ma_crossover(close, 50, 200)

    print("=" * 100)
    print("DRAWDOWN CALIBRATION — what size actually respects the owner's limits?")
    print("=" * 100)
    print(f"  Owner limits: {LIVE_DD_LIMIT:.0f}% live hard stop, "
          f"{BACKTEST_DD_LIMIT:.0f}% backtest acceptance. Capital basis ${CAPITAL:,.0f}.")

    for label, raw in (("200d overlay (long or flat)", long_flat),
                       ("MA 50/200 (long or short)", long_short)):
        print(f"\n  {label}")
        print(f"    {'vol target':>10} {'return/yr':>10} {'Sharpe':>8} {'max DD':>8} "
              f"{'$ on 10k':>9}  {'verdict':<28}")
        print("    " + "-" * 84)

        compliant = None
        for target in (0.10, 0.08, 0.06, 0.05, 0.04, 0.03):
            pos = vol_target(raw, close, target, 60, BARS_PER_YEAR)
            perf = summarise(strategy_returns(pos, close, costs()), BARS_PER_YEAR, turnover(pos))

            if perf.max_drawdown_pct <= LIVE_DD_LIMIT:
                verdict = "OK — inside the live limit"
            elif perf.max_drawdown_pct <= BACKTEST_DD_LIMIT:
                verdict = "passes backtest, breaches live"
            else:
                verdict = "breaches both"

            if compliant is None and perf.max_drawdown_pct <= LIVE_DD_LIMIT:
                compliant = (target, perf)

            print(f"    {target:>9.0%} {perf.ann_return_pct:>+9.2f}% {perf.sharpe:>+8.3f} "
                  f"{perf.max_drawdown_pct:>7.2f}% "
                  f"{CAPITAL * perf.ann_return_pct / 100:>+9.0f}  {verdict:<28}")

        if compliant:
            target, perf = compliant
            print(f"\n    -> Largest compliant size: {target:.0%} volatility target.")
            print(f"       That pays {perf.ann_return_pct:+.2f}%/yr = "
                  f"${CAPITAL * perf.ann_return_pct / 100:+,.0f} a year on ${CAPITAL:,.0f}, "
                  f"before tax and before a single thing goes wrong.")
        else:
            print("\n    -> No tested size respects the 10% live drawdown limit.")

    # What the drawdown limit costs, stated plainly.
    print("\n" + "=" * 100)
    print("WHAT THIS MEANS")
    print("=" * 100)
    pos10 = vol_target(long_flat, close, 0.10, 60, BARS_PER_YEAR)
    perf10 = summarise(strategy_returns(pos10, close, costs()), BARS_PER_YEAR)
    print(f"  At a 10% volatility target the baseline returns {perf10.ann_return_pct:+.2f}%/yr but")
    print(f"  draws down {perf10.max_drawdown_pct:.1f}% — over twice the owner's live limit. Sized")
    print("  down to comply, the same strategy earns proportionally less.")
    print()
    print("  This is not a defect in the strategy. It is what gold trend-following costs at a")
    print("  drawdown tolerance of 10%, on a venue charging 5.66%/yr to hold a long. The")
    print("  arithmetic was always going to produce this; it just had not been written down.")
    print()
    print("  Three honest options, and none of them is 'loosen the limit':")
    print("    1. Accept the small number. A few hundred dollars a year on $10,000 is what")
    print("       this risk budget buys, and it compounds.")
    # Quantify the financing share rather than assert it.
    free = CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=0.0, carry_short_annual_pct=0.0, bars_per_year=BARS_PER_YEAR,
    )
    gross = summarise(strategy_returns(pos10, close, free), BARS_PER_YEAR).ann_return_pct
    share = (gross - perf10.ann_return_pct) / gross * 100.0
    print(f"    2. Fix the venue. Financing takes {gross:+.2f}% gross down to "
          f"{perf10.ann_return_pct:+.2f}% net —")
    print(f"       {share:.0f}% of the gross return. Futures do not charge it; see COSTS.md §6.")
    print("    3. Find a better signal. Everything tested in P3 failed, so this would mean")
    print("       new information (order flow), not new parameters.")
    print()
    print("  The limit stays where the owner set it. I do not raise it to make a number look")
    print("  better, including this one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
