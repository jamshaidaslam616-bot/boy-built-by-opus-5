"""Measure WHERE predictability exists before building anything else.

This corrects a real methodological error in how this project has been run. Every
phase so far picked a strategy and tested it. The scientific order is the reverse:
measure where serial structure exists across every available timeframe, then build
only where something is there.

Three questions per timeframe, and one that decides:

  1. **Autocorrelation** — do returns depend on their own past at all?
  2. **Variance ratio** (Lo-MacKinlay) — does the series trend (>1), revert (<1), or
     wander (=1)? Reported with a heteroskedasticity-robust z, because gold's
     volatility clusters and a naive test would call clustering "structure".
  3. **Conditional continuation** — after an up bar, what does the next one do?

  4. **The one that decides: is any of it bigger than a round trip?** A t-statistic
     of 3 on an effect worth a quarter of the spread is a real discovery and an
     untradeable one.

The H4 timeframe gets particular attention because the owner's earlier project
flagged it as the only place its diagnostics found anything, and this project
skipped straight past it to daily bars.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"

# Round-trip cost in basis points of notional, from COSTS.md. The same absolute cost
# applies whatever the bar length, which is why it bites hardest on fast timeframes.
ROUND_TRIP_BP = 0.47

SERIES = [
    ("XAUUSD", "M15", 96 * 260.0),
    ("XAUUSD", "H1", 24 * 260.0),
    ("XAUUSD", "H4", 6 * 260.0),
    ("XAUUSD", "D1", 260.0),
]

# Windows shown by the earlier project's quality gate to be full-resolution.
USABLE_FROM = {"M15": "2022-01-01", "H1": "2017-01-01", "H4": "2017-01-01", "D1": "2014-01-01"}


def variance_ratio(returns: np.ndarray, q: int) -> tuple[float, float]:
    """Lo-MacKinlay variance ratio with a heteroskedasticity-robust z-statistic.

    VR > 1 means trending, < 1 means reverting, = 1 means a random walk. The robust
    z matters here: gold's volatility clusters heavily, and the homoskedastic test
    reads clustering as structure.
    """
    n = len(returns)
    if n < q * 10:
        return float("nan"), float("nan")

    mu = returns.mean()
    var_1 = np.sum((returns - mu) ** 2) / (n - 1)
    if var_1 <= 0:
        return float("nan"), float("nan")

    rolled = np.convolve(returns, np.ones(q), mode="valid")
    m = q * (n - q + 1) * (1 - q / n)
    var_q = np.sum((rolled - q * mu) ** 2) / m
    vr = var_q / var_1

    # Heteroskedasticity-robust standard error (Lo & MacKinlay 1988, theorem 2).
    delta_sum = 0.0
    dev2 = (returns - mu) ** 2
    for j in range(1, q):
        num = np.sum(dev2[j:] * dev2[:-j])
        den = np.sum(dev2) ** 2 / n
        delta_j = num / den if den > 0 else 0.0
        delta_sum += ((2.0 * (q - j) / q) ** 2) * delta_j

    se = np.sqrt(delta_sum / n) if delta_sum > 0 else np.nan
    z = (vr - 1.0) / se if se and np.isfinite(se) and se > 0 else np.nan
    return float(vr), float(z)


def main() -> int:
    print("=" * 100)
    print("WHERE IS THE STRUCTURE? — measuring before building")
    print("=" * 100)
    print(f"  Round trip costs {ROUND_TRIP_BP:.2f} bp. Any effect smaller than that is real")
    print("  only in the sense that a coin is real.")

    summary = []

    for symbol, timeframe, bars_per_year in SERIES:
        try:
            df = hist.load(ROOT, symbol, timeframe)
        except FileNotFoundError:
            print(f"\n  {timeframe}: not cached, skipping")
            continue

        df = df.loc[df.index >= USABLE_FROM[timeframe]]
        rets = df["close"].pct_change().dropna()
        n = len(rets)
        bp = rets * 10_000  # returns in basis points

        print("\n" + "=" * 100)
        print(f"  {symbol} {timeframe} — {n:,} bars, {df.index[0]:%Y-%m-%d} .. "
              f"{df.index[-1]:%Y-%m-%d}")
        print("=" * 100)
        print(f"    mean |move| per bar: {bp.abs().mean():.2f} bp   "
              f"vs round trip {ROUND_TRIP_BP:.2f} bp   "
              f"ratio {bp.abs().mean() / ROUND_TRIP_BP:.1f}x")

        # 1. Autocorrelation
        lags = [1, 2, 4, 8, 16, 32]
        print(f"\n    autocorrelation   " + "  ".join(f"lag{lag}" for lag in lags))
        acf = [rets.autocorr(lag) for lag in lags]
        se = 1.0 / np.sqrt(n)
        print("                      " + "  ".join(f"{a:+.3f}" for a in acf))
        print("                      " + "  ".join(
            f"{'  sig' if abs(a) > 2 * se else '     '}" for a in acf
        ) + f"    (2 s.e. = {2 * se:.3f})")

        # 2. Variance ratios
        print(f"\n    {'q':>4} {'variance ratio':>16} {'robust z':>10}   reading")
        best_vr = None
        for q in (2, 4, 8, 16, 32):
            vr, z = variance_ratio(rets.to_numpy(), q)
            if not np.isfinite(vr):
                continue
            reading = ("trending" if vr > 1 else "reverting") if abs(z) > 2 else "random walk"
            flag = "  <--" if abs(z) > 2 else ""
            print(f"    {q:>4} {vr:>16.4f} {z:>+10.2f}   {reading}{flag}")
            if best_vr is None or abs(z) > abs(best_vr[2]):
                best_vr = (q, vr, z)

        # 3. Conditional continuation, net of costs
        up = rets.shift(1) > 0
        after_up, after_down = bp[up], bp[~up]
        diff = after_up.mean() - after_down.mean()
        t = stats.ttest_ind(after_up, after_down, equal_var=False).statistic
        print(f"\n    after an UP bar   next bar {after_up.mean():+.3f} bp  (n={len(after_up):,})")
        print(f"    after a DOWN bar  next bar {after_down.mean():+.3f} bp  (n={len(after_down):,})")
        print(f"    differential      {diff:+.3f} bp   t={t:+.2f}")
        print(f"    -> versus a {ROUND_TRIP_BP:.2f} bp round trip: "
              f"{'TRADEABLE' if abs(diff) > ROUND_TRIP_BP else 'SMALLER THAN COSTS'} "
              f"({abs(diff) / ROUND_TRIP_BP:.2f}x)")

        summary.append({
            "timeframe": timeframe,
            "bars": n,
            "best_vr_q": best_vr[0] if best_vr else np.nan,
            "best_vr": best_vr[1] if best_vr else np.nan,
            "best_vr_z": best_vr[2] if best_vr else np.nan,
            "continuation_bp": diff,
            "continuation_t": t,
            "cost_multiple": abs(diff) / ROUND_TRIP_BP,
        })

    print("\n" + "=" * 100)
    print("  SUMMARY — where to build, if anywhere")
    print("=" * 100)
    table = pd.DataFrame(summary)
    print(f"    {'TF':<5} {'bars':>9} {'best VR':>9} {'VR z':>7} {'contin. bp':>11} "
          f"{'t':>7} {'vs costs':>9}")
    for _, r in table.iterrows():
        flag = ""
        if abs(r["best_vr_z"]) > 2 and r["cost_multiple"] > 1:
            flag = "   <-- WORTH BUILDING FOR"
        elif abs(r["best_vr_z"]) > 2:
            flag = "   <-- structure, but under costs"
        print(f"    {r['timeframe']:<5} {r['bars']:>9,.0f} {r['best_vr']:>9.3f} "
              f"{r['best_vr_z']:>+7.2f} {r['continuation_bp']:>+11.3f} "
              f"{r['continuation_t']:>+7.2f} {r['cost_multiple']:>8.2f}x{flag}")

    print()
    print("  Reading this honestly: a significant variance ratio says the series is not a")
    print("  random walk. It does NOT say the deviation is large enough to trade. Both")
    print("  columns have to clear their bar, and the cost column is the harder one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
