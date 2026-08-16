"""Test COT's ACTUAL claim, which is about extremes, not a straight line.

The linear correlation between positioning and next week's gold return came out at
roughly zero (see the fetch script). That is not enough to dismiss COT, because
nobody claims it is linear. The published claim is contrarian and conditional:
when speculative positioning reaches a multi-year extreme, the subsequent move
tends to run against the crowd.

A linear correlation is blind to that by construction, so this tests the real
thing — forward returns bucketed by where positioning sits in its own 3-year range,
using only data that had actually been released.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import cot  # noqa: E402
from goldlab.data import history as hist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
HORIZONS_WEEKS = (1, 4, 13)


def newey_west_t(x: np.ndarray, lags: int) -> tuple[float, float]:
    """t-statistic for a mean, corrected for overlapping observations.

    A 13-week forward return sampled weekly overlaps 12 of its 13 weeks with its
    neighbour, so consecutive observations are nearly the same number. A plain
    t-statistic treats them as independent and inflates by roughly sqrt(overlap) —
    which is how a first pass here produced t=10.5 on an effective sample of about
    38. Newey-West widens the standard error to account for that autocorrelation.

    Returns (t_statistic, effective_sample_size).
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        return float("nan"), float(n)

    demeaned = x - x.mean()
    gamma0 = float(demeaned @ demeaned) / n
    variance = gamma0
    for k in range(1, min(lags, n - 1) + 1):
        gamma_k = float(demeaned[k:] @ demeaned[:-k]) / n
        bartlett = 1.0 - k / (lags + 1.0)
        variance += 2.0 * bartlett * gamma_k

    variance = max(variance, 1e-12)
    se = np.sqrt(variance / n)
    t = x.mean() / se if se > 0 else float("nan")
    effective_n = n * gamma0 / variance if variance > 0 else float(n)
    return float(t), float(effective_n)


def main() -> int:
    df = pd.read_parquet(ROOT / "cot_gold.parquet")
    series = cot.CotSeries(contract_code=cot.GOLD_CONTRACT_CODE, frame=df)
    gold = hist.load(ROOT, "XAUUSD", "D1")["close"]

    weekly = gold.resample("W-TUE").last()
    published = series.as_known_on(weekly.index, columns=list(df.columns))
    mm_index = cot.cot_index(published["managed_money_net_pct_oi"])

    print("=" * 96)
    print("COT AT EXTREMES — gold, managed money positioning, AS PUBLISHED")
    print("=" * 96)
    print("  Contrarian claim: crowded longs (index near 1.0) precede WEAKNESS,")
    print("  crowded shorts (near 0.0) precede STRENGTH. So we need the top bucket")
    print("  to underperform the bottom one, by more than noise.")

    buckets = pd.cut(
        mm_index,
        bins=[-0.001, 0.10, 0.30, 0.70, 0.90, 1.001],
        labels=["0.0-0.1 (max short)", "0.1-0.3", "0.3-0.7 (neutral)", "0.7-0.9", "0.9-1.0 (max long)"],
    )

    for weeks in HORIZONS_WEEKS:
        fwd = weekly.pct_change(weeks).shift(-weeks) * 100.0
        data = pd.DataFrame({"bucket": buckets, "fwd": fwd}).dropna()

        overlap = weeks - 1
        print(f"\n  Forward {weeks}-week gold return by positioning bucket  (n={len(data):,}, "
              f"{overlap}-week overlap)")
        print(f"    {'bucket':<22} {'n':>5} {'mean %':>9} {'median %':>9} "
              f"{'naive t':>8} {'NW t':>7} {'eff n':>7}")
        print("    " + "-" * 76)

        means = {}
        for label in buckets.cat.categories:
            grp = data.loc[data["bucket"] == label, "fwd"]
            if len(grp) < 10:
                print(f"    {label:<22} {len(grp):>5}   too few observations")
                continue
            naive_t = stats.ttest_1samp(grp, 0.0).statistic
            nw_t, eff_n = newey_west_t(grp.to_numpy(), lags=overlap)
            means[label] = grp.mean()
            print(f"    {label:<22} {len(grp):>5} {grp.mean():>+9.2f} {grp.median():>+9.2f} "
                  f"{naive_t:>+8.2f} {nw_t:>+7.2f} {eff_n:>7.0f}")

        top, bottom = "0.9-1.0 (max long)", "0.0-0.1 (max short)"
        if top in means and bottom in means:
            a = data.loc[data["bucket"] == bottom, "fwd"]
            b = data.loc[data["bucket"] == top, "fwd"]
            res = stats.ttest_ind(a, b, equal_var=False)
            direction = "as theory predicts" if means[bottom] > means[top] else "OPPOSITE to theory"
            print(f"    spread (max short - max long): {means[bottom] - means[top]:+.2f}%  "
                  f"t={res.statistic:+.2f}  p={res.pvalue:.3f}   [{direction}]")

    # ---- the control that matters: is this COT, or is it just the trend? ----
    #
    # 2013-2026 was a large gold bull market and managed money are trend followers.
    # "Specs are long" and "gold is in an uptrend" are close to the same statement,
    # so a raw bucket result can be the trend signal wearing a COT costume. The
    # test is whether COT still separates returns INSIDE a single trend state.
    print("\n" + "=" * 96)
    print("CONTROL — does COT say anything the trend does not already say?")
    print("=" * 96)

    trend_up = (gold > gold.rolling(200, min_periods=200).mean()).resample("W-TUE").last()
    fwd4 = weekly.pct_change(4).shift(-4) * 100.0
    ctrl = pd.DataFrame({
        "cot": mm_index,
        "up": trend_up.reindex(mm_index.index),
        "fwd": fwd4.reindex(mm_index.index),
    }).dropna()
    ctrl["crowded"] = ctrl["cot"] >= 0.70

    print(f"  Forward 4-week return, split by trend state AND positioning (n={len(ctrl):,})")
    print(f"    {'trend':<12} {'positioning':<16} {'n':>5} {'mean %':>9} {'NW t':>7}")
    print("    " + "-" * 54)
    cells = {}
    for up in (True, False):
        for crowded in (True, False):
            grp = ctrl[(ctrl["up"] == up) & (ctrl["crowded"] == crowded)]["fwd"]
            if len(grp) < 10:
                continue
            nw_t, _ = newey_west_t(grp.to_numpy(), lags=3)
            cells[(up, crowded)] = grp.mean()
            print(f"    {'UPTREND' if up else 'DOWNTREND':<12} "
                  f"{'crowded long' if crowded else 'not crowded':<16} "
                  f"{len(grp):>5} {grp.mean():>+9.2f} {nw_t:>+7.2f}")

    print()
    for up in (True, False):
        if (up, True) in cells and (up, False) in cells:
            gap = cells[(up, True)] - cells[(up, False)]
            state = "uptrend" if up else "downtrend"
            print(f"    Within {state:<10} crowded minus not-crowded = {gap:+.2f}%")
    print()
    print("    If those within-trend gaps are near zero, COT adds nothing beyond a")
    print("    200-day moving average — and A1 already carries that information for free.")

    print("\n" + "=" * 96)
    print("  Reading all of this: a |NW t| under about 2 is noise. With three horizons and")
    print("  five buckets examined, one marginal reading is what chance produces — so a")
    print("  single t just over 2 is not evidence, and would have to be pre-registered and")
    print("  retested out-of-sample to count.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
