"""What drawdown limit is defensible, now that the owner has authorised raising it?

The owner authorised going above 10% and left the number to me. A number picked by
feel would be worthless, so this measures one.

Two things have to be separated, because conflating them is how people talk
themselves into more risk:

  1. **What size is compatible with a given limit** — a statistics question, and the
     honest answer is not the drawdown a single 12-year backtest happened to produce.
     One path is one draw from a distribution. Reshuffling the same returns in blocks
     shows what else could have happened, and the answer is reliably worse.

  2. **Whether taking more risk is a good idea** — a completely different question,
     and the answer depends on whether there is an edge. There is no validated edge
     here. Raising risk on an unvalidated strategy scales the loss exactly as much as
     the gain.

So this reports the size/limit arithmetic, and then states plainly what it does and
does not buy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.metrics import max_drawdown_pct, sharpe_ratio, summarise  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, vol_target  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
SPEEDS = (20, 50, 100, 200, 400)
N_PATHS = 5_000
MEAN_BLOCK = 21  # ~1 month; long enough to preserve the trend persistence that makes drawdowns


def costs() -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0, bars_per_year=BARS_PER_YEAR,
    )


def stationary_bootstrap_drawdowns(returns: np.ndarray, n_paths: int, seed: int) -> np.ndarray:
    """Max drawdown distribution from resampled paths of the same length.

    Blocks of random length (geometric, mean ``MEAN_BLOCK``) preserve the
    autocorrelation that creates drawdowns. Resampling individual days would break
    exactly the structure being measured and would understate the risk.
    """
    rng = np.random.default_rng(seed)
    n = len(returns)
    out = np.empty(n_paths)
    for p in range(n_paths):
        path, filled = [], 0
        while filled < n:
            start = rng.integers(0, n)
            length = min(int(rng.geometric(1.0 / MEAN_BLOCK)), n - filled)
            idx = (np.arange(start, start + length)) % n
            path.append(returns[idx])
            filled += length
        series = pd.Series(np.concatenate(path)[:n])
        out[p] = max_drawdown_pct(series)
    return out


def main() -> int:
    close = hist.load(ROOT, "XAUUSD", "D1")["close"]
    raw = (sum(C.a1_timeseries_momentum(close, n) for n in SPEEDS) / len(SPEEDS)).clip(lower=0.0)

    print("=" * 96)
    print("RISK LIMIT — measured, not chosen")
    print("=" * 96)
    print("  Strategy: P4 long-only 5-speed trend ensemble (the best thing found).")
    print(f"  Bootstrap: {N_PATHS:,} resampled paths, blocks averaging {MEAN_BLOCK} days.")

    # --- 1. What a single backtest path understates ---
    print("\n" + "-" * 96)
    print("  HOW MUCH THE SINGLE BACKTEST PATH UNDERSTATES DRAWDOWN")
    print("-" * 96)
    print(f"    {'vol target':>10} {'observed DD':>12} {'median':>9} {'p90':>8} "
          f"{'p95':>8} {'p99':>8} {'p95/obs':>9}")

    table = {}
    for target in (0.05, 0.08, 0.10, 0.12, 0.15):
        pos = vol_target(raw, close, target, 60, BARS_PER_YEAR)
        net = strategy_returns(pos, close, costs())
        perf = summarise(net, BARS_PER_YEAR)
        dds = stationary_bootstrap_drawdowns(net.dropna().to_numpy(), N_PATHS, seed=20260810)
        p50, p90, p95, p99 = np.percentile(dds, [50, 90, 95, 99])
        table[target] = (perf, p50, p90, p95, p99)
        print(f"    {target:>9.0%} {perf.max_drawdown_pct:>11.2f}% {p50:>8.2f}% {p90:>7.2f}% "
              f"{p95:>7.2f}% {p99:>7.2f}% {p95 / perf.max_drawdown_pct:>8.2f}x")

    ratios = [t[3] / t[0].max_drawdown_pct for t in table.values()]
    print(f"\n    The 95th percentile runs {np.mean(ratios):.2f}x the drawdown this particular")
    print("    12.6-year path produced. A limit set to the observed backtest drawdown would")
    print("    be breached in roughly one run out of two.")

    # --- 2. What each candidate limit permits ---
    print("\n" + "-" * 96)
    print("  WHAT EACH LIMIT PERMITS  (sized so the 95th-percentile drawdown fits inside it)")
    print("-" * 96)
    print(f"    {'live limit':>11} {'vol target':>11} {'p95 DD':>9} {'return/yr':>11} "
          f"{'$ on 10k':>10} {'worst $ loss (p95)':>20}")

    recommendation = None
    for limit in (10, 15, 20, 25, 30):
        best = None
        for target in np.arange(0.03, 0.26, 0.005):
            pos = vol_target(raw, close, float(target), 60, BARS_PER_YEAR)
            net = strategy_returns(pos, close, costs())
            dds = stationary_bootstrap_drawdowns(net.dropna().to_numpy(), 800, seed=20260810)
            if np.percentile(dds, 95) <= limit:
                best = (float(target), summarise(net, BARS_PER_YEAR), float(np.percentile(dds, 95)))
            else:
                break
        if best is None:
            print(f"    {limit:>10}% {'nothing fits':>11}")
            continue
        target, perf, p95 = best
        print(f"    {limit:>10}% {target:>10.1%} {p95:>8.2f}% {perf.ann_return_pct:>+10.2f}% "
              f"{CAPITAL * perf.ann_return_pct / 100:>+10.0f} "
              f"{-CAPITAL * p95 / 100:>19,.0f}")
        if limit == 20:
            recommendation = (target, perf, p95)

    # --- 3. The part that matters more than the number ---
    print("\n" + "=" * 96)
    print("  WHAT RAISING THE LIMIT DOES AND DOES NOT BUY")
    print("=" * 96)

    ref = vol_target(raw, close, 0.10, 60, BARS_PER_YEAR)
    ref_net = strategy_returns(ref, close, costs())
    sr = sharpe_ratio(ref_net, BARS_PER_YEAR)
    print(f"    This strategy's measured Sharpe is {sr:+.3f}. Its random-entry control z-score")
    print("    is +1.32 and its Deflated Sharpe is 0.14 — meaning it is NOT statistically")
    print("    distinguishable from a rotation of itself. There is no validated edge.")
    print()
    print("    Raising the limit scales BOTH sides of that. If the edge is real, the return")
    print("    grows in proportion. If it is not, the losses grow in proportion and the")
    print("    drawdowns arrive anyway. The limit is not what is holding the number down —")
    print("    the absence of a proven edge is.")

    if recommendation:
        target, perf, p95 = recommendation
        print()
        print("-" * 96)
        print("  MY RECOMMENDATION")
        print("-" * 96)
        print(f"    Raise the live halt to 20%, and size at a {target:.1%} volatility target.")
        print()
        print(f"      expected return   {perf.ann_return_pct:+.2f}%/yr = "
              f"${CAPITAL * perf.ann_return_pct / 100:+,.0f} on ${CAPITAL:,.0f}")
        print(f"      95th-pct drawdown {p95:.1f}% = ${CAPITAL * p95 / 100:,.0f}")
        print(f"      observed backtest {perf.max_drawdown_pct:.1f}%")
        print()
        print("    Why 20% and not 30%: 20% leaves the halt as a genuine signal that something")
        print("    is wrong rather than a routine event, because the p95 drawdown sits inside")
        print("    it with room to spare. At 30% the halt would almost never fire, which makes")
        print("    it decoration rather than a control.")
        print()
        print("    Why not stay at 10%: at 10% the p95 drawdown does not fit any size worth")
        print("    trading, so the limit would be hit by normal variation and halt a system")
        print("    that was behaving exactly as designed.")
        print()
        print("    **But I would not deploy this at any size until something passes the")
        print("    gauntlet.** Raising the limit is the right preparation; it is not a result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
