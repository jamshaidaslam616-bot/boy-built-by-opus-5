"""Fetch the free macro series and prove their alignment is not optimistic.

Reports, for each series, how stale the live feed actually is against the
publication lag we configured. A configured lag shorter than observed staleness
would let a backtest read unpublished numbers, so that case raises rather than
warns.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.data import macro as mac  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"


def main() -> int:
    gold = hist.load(ROOT, "XAUUSD", "D1")
    today = pd.Timestamp.now(tz="UTC")

    print("=" * 92)
    print("P2 — FREE MACRO SERIES, ALIGNED POINT-IN-TIME")
    print("=" * 92)

    series = [mac.real_yield_10y(), mac.broad_dollar_index()]

    for m in series:
        observed = mac.measure_publication_lag(m.values, today)
        mac.assert_lag_is_not_optimistic(m, today)  # raises if we would be reading the future

        aligned = m.as_known_on(gold.index)
        coverage = aligned.notna().mean() * 100.0
        first_known = aligned.first_valid_index()

        print(f"\n  {m.name}  ({m.series_id})")
        print(f"    raw span          {m.values.index[0]:%Y-%m-%d} .. {m.values.index[-1]:%Y-%m-%d}"
              f"   ({len(m.values):,} observations)")
        print(f"    feed staleness    {observed} days   <= configured lag {m.publication_lag_days} days  [OK]")
        print(f"    latest value      {m.values.iloc[-1]:,.4f}")
        print(f"    aligned to gold   {coverage:.1f}% of {len(gold):,} bars covered, "
              f"usable from {first_known:%Y-%m-%d}")
        print(f"    cached -> {mac.cache(m, ROOT).name}")

    # The overlap is what actually constrains any macro-conditioned candidate.
    aligned = pd.DataFrame({m.name: m.as_known_on(gold.index) for m in series})
    both = aligned.dropna()
    print("\n" + "-" * 92)
    print(f"  Both series available on {len(both):,} of {len(gold):,} gold bars "
          f"({len(both) / len(gold) * 100:.1f}%), from {both.index[0]:%Y-%m-%d}.")
    print("  That overlap, not the gold history, is the sample any macro-conditioned")
    print("  candidate gets. Recorded now so it cannot be discovered as a surprise in P3.")

    # Two different questions, and conflating them is the whole trap.
    #
    #   TRUE   — does gold co-move with these drivers on the SAME observation date?
    #            Validates the data. Not tradeable: it needs figures we did not have.
    #   USABLE — does gold co-move with what had actually been PUBLISHED by then?
    #            This is the only one a strategy could ever act on.
    gold_ret = gold["close"].pct_change().rename("gold_ret")

    print("\n" + "=" * 92)
    print("  THE RELATIONSHIP, MEASURED TWICE")
    print("=" * 92)
    print(f"  {'driver':<26} {'TRUE (same date)':>20} {'USABLE (as published)':>24}")
    print("  " + "-" * 88)

    for m, transform in ((series[0], "diff"), (series[1], "pct_change")):
        raw = m.values.diff() if transform == "diff" else m.values.pct_change()
        true_df = pd.concat([gold_ret, raw.rename("drv")], axis=1, join="inner").dropna()
        true_corr = true_df["gold_ret"].corr(true_df["drv"])

        pub = m.as_known_on(gold.index)
        pub_chg = pub.diff() if transform == "diff" else pub.pct_change()
        # Forward-filled days publish nothing new; a zero there is "no news", not
        # "no change", and keeping them would dilute the correlation mechanically.
        usable_df = pd.concat([gold_ret, pub_chg.rename("drv")], axis=1).dropna()
        usable_df = usable_df[usable_df["drv"] != 0.0]
        usable_corr = usable_df["gold_ret"].corr(usable_df["drv"])

        print(f"  {m.name:<26} {true_corr:>+19.4f} {usable_corr:>+23.4f}"
              f"   (n={len(true_df):,} / {len(usable_df):,})")

    print("\n  The TRUE column should be clearly NEGATIVE for both — that is the documented")
    print("  relationship and it confirms the data is sound. The USABLE column is what a")
    print("  strategy could actually have traded on.")
    print()
    print("  If USABLE collapses towards zero, the honest reading is that gold's best-known")
    print("  macro drivers are real but ALREADY PRICED by the time we can see them. That")
    print("  would not kill B1/B2 — it would mean they belong as slow REGIME FILTERS on a")
    print("  level, not as triggers on a change. P3 tests exactly that, pre-registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
