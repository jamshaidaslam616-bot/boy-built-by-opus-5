"""Venue analysis — and a correction to something I overstated.

In FINDINGS F9 I wrote that financing takes 41% of the gross return and pointed at
futures as the fix. The 41% is measured and correct. The implication was not.

Most of that -5.66%/yr is **not** a broker charge that a different venue removes. It
is the cost of carry, which any leveraged long gold position pays anywhere, because
holding gold with borrowed money costs the interest rate. Gold futures embed exactly
the same carry in their basis: a long futures position pays it as the contract rolls
down toward spot.

What the broker genuinely takes is:
  * a **markup** over the risk-free rate on the long side, and
  * the **entire credit** on the short side, where it pays 0.00% instead of the
    positive carry a short futures position earns.

That distinction matters enormously here, because P4's best strategy was LONG-ONLY —
which is precisely the side where switching venue buys the least.

This script decomposes the charge against live market rates and restates the venue
case honestly.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import _http  # noqa: E402
from goldlab.data import history as hist  # noqa: E402
from goldlab.research.metrics import summarise  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, vol_target  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0

CFD_CARRY_LONG = -5.66   # MEASURED 2026-08-08
CFD_CARRY_SHORT = 0.0    # MEASURED 2026-08-08

# MGC micro gold: 10 oz, $0.10 tick = $1.00. Commission is broker-dependent;
# $1.50/side round turn $3.00 is a realistic retail figure and is flagged as an
# assumption, not a measurement, until an account exists to measure it on.
MGC_CONTRACT_OZ = 10
MGC_COMMISSION_RT_USD = 3.00
MGC_TICK_USD = 1.00


def fetch_rate(series_id: str, label: str) -> float | None:
    # Fail fast: this figure is illustrative and the venue decision does not rest on
    # it, so a long retry budget here just stalls the report for nothing.
    try:
        body = _http.get_text(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
            timeout=15, attempts=2,
        )
    except Exception as exc:
        print(f"  {label:<24} unavailable ({type(exc).__name__})")
        return None
    df = pd.read_csv(io.StringIO(body))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    clean = df.dropna()
    value = float(clean["value"].iloc[-1])
    print(f"  {label:<24} {value:5.2f}%   as of {clean['date'].iloc[-1]}")
    return value


def main() -> int:
    close = hist.load(ROOT, "XAUUSD", "D1")["close"]
    spot = float(close.iloc[-1])

    print("=" * 98)
    print("VENUE ANALYSIS — decomposing the financing charge")
    print("=" * 98)
    print("\n  Live US rates (FRED):")
    sofr = fetch_rate("SOFR", "overnight SOFR")
    one_year = fetch_rate("DGS1", "1-year Treasury")

    benchmark = sofr if sofr is not None else one_year
    assumed = benchmark is None
    if assumed:
        # The decomposition is illustrative, not load-bearing — the decision below
        # rests on contract granularity, which needs no rate at all. So a labelled
        # assumption is better than abandoning the section.
        benchmark = 4.00
        print(f"\n  FRED unreachable. Using an ASSUMED {benchmark:.2f}% short rate for the")
        print("  decomposition below. It is illustrative only; the venue decision at the")
        print("  bottom of this report does not depend on it.")

    print("\n" + "-" * 98)
    print("  THE DECOMPOSITION")
    print("-" * 98)
    markup_long = abs(CFD_CARRY_LONG) - benchmark
    print(f"    CFD charges on a long        {CFD_CARRY_LONG:+.2f}% / yr   (MEASURED)")
    print(f"    of which, genuine carry      {-benchmark:+.2f}% / yr   "
          f"(the risk-free rate; unavoidable anywhere)")
    print(f"    of which, broker markup      {-markup_long:+.2f}% / yr   "
          f"(this is the part a venue change can remove)")
    print()
    print(f"    CFD pays on a short          {CFD_CARRY_SHORT:+.2f}% / yr   (MEASURED)")
    print(f"    a short futures earns        {benchmark:+.2f}% / yr   (approximately, via the basis)")
    print(f"    so the broker keeps          {benchmark:+.2f}% / yr   on every short")

    print("\n" + "=" * 98)
    print("  WHAT SWITCHING TO FUTURES ACTUALLY BUYS")
    print("=" * 98)
    print(f"    {'strategy shape':<28} {'CFD carry':>12} {'futures carry':>15} {'gain':>10}")
    print("    " + "-" * 70)
    print(f"    {'long only':<28} {CFD_CARRY_LONG:>+11.2f}% {-benchmark:>+14.2f}% "
          f"{markup_long:>+9.2f}%")
    print(f"    {'long/short, 50/50':<28} "
          f"{CFD_CARRY_LONG / 2:>+11.2f}% {0.0:>+14.2f}% {abs(CFD_CARRY_LONG) / 2:>+9.2f}%")
    print(f"    {'short only':<28} {CFD_CARRY_SHORT:>+11.2f}% {benchmark:>+14.2f}% "
          f"{benchmark:>+9.2f}%")

    print("\n  *** THE CORRECTION ***")
    print(f"    FINDINGS F9 implied futures would recover most of the 41% that financing")
    print(f"    takes. For a LONG-ONLY strategy it recovers only the markup — about")
    print(f"    {markup_long:.2f} percentage points a year, not {abs(CFD_CARRY_LONG):.2f}.")
    print(f"    And P4's best surviving shape was long-only, which is the side where")
    print(f"    switching buys the least. I overstated this and am correcting it.")

    # Quantify it on the actual strategy rather than in the abstract.
    print("\n" + "=" * 98)
    print("  MEASURED ON P4'S BEST STRATEGY (long-only 5-speed ensemble)")
    print("=" * 98)
    ensemble = (sum(C.a1_timeseries_momentum(close, n) for n in (20, 50, 100, 200, 400)) / 5.0)
    long_only = ensemble.clip(lower=0.0)

    scenarios = {
        "CFD as measured": CFD_CARRY_LONG,
        "futures (carry = risk-free)": -benchmark,
        "no financing at all (unreal)": 0.0,
    }
    for label, carry in scenarios.items():
        model = CostModel(
            spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
            carry_long_annual_pct=carry, carry_short_annual_pct=0.0,
            bars_per_year=BARS_PER_YEAR,
        )
        for target in (0.10, 0.08, 0.06, 0.05, 0.04, 0.03):
            pos = vol_target(long_only, close, target, 60, BARS_PER_YEAR)
            perf = summarise(strategy_returns(pos, close, model), BARS_PER_YEAR)
            if perf.max_drawdown_pct <= 10.0:
                print(f"    {label:<30} at {target:.0%} vol: {perf.ann_return_pct:+.2f}%/yr "
                      f"= ${CAPITAL * perf.ann_return_pct / 100:+,.0f} on ${CAPITAL:,.0f} "
                      f"(maxDD {perf.max_drawdown_pct:.2f}%)")
                break

    print("\n" + "=" * 98)
    print("  THE OTHER SIDE OF THE LEDGER — what futures COST that the CFD does not")
    print("=" * 98)
    gold_vol = float(close.pct_change().std() * (BARS_PER_YEAR ** 0.5))
    print(f"    gold's own annual volatility, measured: {gold_vol:.1%}")
    print()
    print(f"    {'instrument':<22} {'size':>8} {'notional':>12} {'annual vol':>12} "
          f"{'need @5% tgt':>13} {'oversized':>10}")
    print("    " + "-" * 82)
    for label, oz in (("MGC micro futures", MGC_CONTRACT_OZ), ("GC full futures", 100),
                      ("CFD minimum (0.01 lot)", 1)):
        notional = oz * spot
        contract_vol = gold_vol * notional
        needed = (0.05 * CAPITAL) / contract_vol
        over = "n/a" if oz == 1 else f"{1 / needed:.1f}x"
        print(f"    {label:<22} {oz:>5} oz {notional:>12,.0f} {contract_vol:>12,.0f} "
              f"{needed:>13.3f} {over:>10}")

    mgc_vol = gold_vol * MGC_CONTRACT_OZ * spot
    print()
    print("    *** THE BINDING CONSTRAINT IS GRANULARITY, NOT CARRY ***")
    print(f"    At a 5% volatility target on ${CAPITAL:,.0f}, the correct position is 0.077 of")
    print("    one micro contract. The minimum tradeable size is 1. Futures cannot be made")
    print(f"    small enough for this account — the smallest position is 13x too large.")
    print()
    print(f"    One MGC contract becomes a sensible position at roughly "
          f"${mgc_vol / 0.05:,.0f} of capital")
    print(f"    (5% vol target) or ${mgc_vol / 0.10:,.0f} (10% vol target).")
    print()
    print("    The CFD's 0.01-lot minimum is 1 oz — ten times finer — and that is the only")
    print("    reason this strategy is implementable at all at this account size.")

    print("\n" + "=" * 98)
    print("  VENUE VERDICT — reversing what F9 implied")
    print("=" * 98)
    print("    STAY ON THE CFD. Not because its financing is good; it is not, and the")
    print(f"    markup is real. But at ${CAPITAL:,.0f} with a 10% drawdown limit, futures are")
    print("    unusable regardless of their carry advantage.")
    print()
    print("    COSTS.md section 6 pre-wrote a switch trigger based on carry alone. That")
    print("    trigger was incomplete: it never checked whether the target venue could")
    print("    express the position. Amending it now, with the reason, rather than")
    print("    quietly leaving a trigger that would have fired wrongly.")
    print()
    print("    Revisit futures when EITHER capital reaches roughly $65,000, OR a strategy")
    print("    emerges that is genuinely two-sided — because the short side is where the")
    print(f"    broker keeps the entire {benchmark:.1f}% credit and futures would pay it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
