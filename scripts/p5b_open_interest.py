"""Open interest as a flow signal — the last free, untested, non-price input.

Free real futures VOLUME turned out not to be obtainable: Stooq refuses automated
requests and Yahoo's GC=F volume has a median of 232 contracts a day against a true
figure near 250,000, so it is a continuous-contract artefact rather than data.

But open interest is already in hand, from the CFTC COT files fetched in P2, and it
was never tested. It is worth testing precisely because it is NOT derived from
price: it counts how many contracts exist, which is a statement about participation
rather than about what the price did.

The classic claim, which is what gets tested here:

    rising price + rising OI   = new money entering, trend is well supported
    rising price + falling OI  = short covering, the move is being closed not opened
    falling price + rising OI  = new shorts, decline is well supported
    falling price + falling OI = long liquidation, decline is running out of fuel

If that is real, conditioning the trend signal on OI direction should beat the trend
signal alone. It is weekly and slow, which suits an $11/lot open-charge commission.
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
from goldlab.research.metrics import summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns  # noqa: E402
from goldlab.research.sizing import largest_compliant_size  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
SPEEDS = (20, 50, 100, 200, 400)

HYPOTHESIS = Hypothesis(
    name="P5b-open-interest-confirmation",
    family="E-flow",
    claim="A trend accompanied by RISING open interest continues more reliably than one "
          "accompanied by falling open interest, so gating the trend signal on the "
          "direction of open interest beats the ungated signal.",
    economic_rationale="Open interest counts contracts outstanding, so it separates new "
                       "positioning from the unwinding of old positioning — information that "
                       "price alone cannot contain. A rally on rising open interest is being "
                       "bought by someone taking new risk; the same rally on falling open "
                       "interest is shorts buying back, which is demand that exhausts itself "
                       "by construction. This is the only genuinely non-price input still "
                       "untested and available for free.",
    pass_criteria={"beats_ungated_calmar_pct": 15.0, "control_rotation_z": 2.0},
    n_param_combinations=3,
    data_scope="XAUUSD D1 2014-2026; CFTC COT gold open interest, weekly, 5-day release lag",
    predicted_outcome="Weak. COT positioning already failed (F6) and open interest is a coarser "
                      "cousin of it. The mechanism is genuine but it is also very well known, "
                      "which usually means it is priced. I expect the gated version to trade "
                      "less and end up close to the ungated one, with any difference inside "
                      "noise. I have been wrong on 3 of 6 predictions so far, and each time by "
                      "being too optimistic.",
)


def costs() -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0, bars_per_year=BARS_PER_YEAR,
    )


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    close = hist.load(ROOT, "XAUUSD", "D1")["close"]
    frame = pd.read_parquet(ROOT / "cot_gold.parquet")
    series = cot.CotSeries(contract_code=cot.GOLD_CONTRACT_CODE, frame=frame)

    published = series.as_known_on(close.index, columns=["open_interest"])
    oi = published["open_interest"]

    print("=" * 94)
    print("P5b — OPEN INTEREST AS FLOW CONFIRMATION")
    print("=" * 94)
    print(f"  open interest available on {oi.notna().mean():.1%} of {len(close):,} bars, "
          f"from {oi.first_valid_index():%Y-%m-%d}")
    print(f"  latest {oi.dropna().iloc[-1]:,.0f} contracts")

    # --- 1. Does the four-quadrant claim hold at all? ---
    weekly = close.resample("W-TUE").last()
    px_chg = weekly.pct_change()
    oi_chg = oi.resample("W-TUE").last().diff()
    fwd = weekly.pct_change(4).shift(-4) * 100.0

    quad = pd.DataFrame({"px": px_chg, "oi": oi_chg, "fwd": fwd}).dropna()
    print(f"\n  Forward 4-week gold return by quadrant  (n={len(quad):,})")
    print(f"    {'price':<10} {'open interest':<16} {'n':>5} {'mean %':>9} {'t':>7}")
    print("    " + "-" * 52)
    for px_up in (True, False):
        for oi_up in (True, False):
            grp = quad[(quad["px"] > 0) == px_up][lambda d: (d["oi"] > 0) == oi_up]["fwd"]
            if len(grp) < 15:
                continue
            t = stats.ttest_1samp(grp, 0.0).statistic
            print(f"    {'rising' if px_up else 'falling':<10} "
                  f"{'rising' if oi_up else 'falling':<16} {len(grp):>5} "
                  f"{grp.mean():>+9.2f} {t:>+7.2f}")
    print("\n    (4-week windows overlap 3 weeks, so these t-statistics are inflated; they")
    print("     are here to show direction, and the strategy test below is what decides.)")

    # --- 2. The test that decides: does gating on OI beat not gating? ---
    trend = (sum(C.a1_timeseries_momentum(close, n) for n in SPEEDS) / len(SPEEDS)).clip(lower=0.0)
    oi_rising = (oi.diff() > 0).astype(float).reindex(close.index).ffill().fillna(0.0)

    variants = {
        "ungated trend (P4 best)": trend,
        "trend, OI rising only": trend * oi_rising,
        "trend, OI falling only": trend * (1.0 - oi_rising),
    }

    print("\n" + "=" * 94)
    print("  DOES GATING HELP? — each sized to the largest compliant position (20% halt, p95)")
    print("=" * 94)
    print(f"    {'variant':<26} {'vol tgt':>8} {'return':>9} {'p95 DD':>8} "
          f"{'$ on 10k':>10} {'Calmar':>8}")
    print("    " + "-" * 76)

    results = {}
    for label, pos in variants.items():
        sized = largest_compliant_size(pos, close, costs(), BARS_PER_YEAR, n_paths=400)
        if sized is None:
            print(f"    {label:<26} no compliant size")
            continue
        perf = sized.performance
        calmar = perf.ann_return_pct / sized.p95_drawdown_pct
        results[label] = (sized, calmar)
        print(f"    {label:<26} {sized.vol_target:>7.0%} {perf.ann_return_pct:>+8.2f}% "
              f"{sized.p95_drawdown_pct:>7.2f}% {sized.dollars(CAPITAL):>+10.0f} {calmar:>8.3f}")

    verdict = "FAIL"
    if "ungated trend (P4 best)" in results and "trend, OI rising only" in results:
        base = results["ungated trend (P4 best)"][1]
        gated = results["trend, OI rising only"][1]
        change = (gated / base - 1) * 100
        print(f"\n    Calmar change from gating on rising OI: {change:+.1f}%")
        verdict = "PASS" if change >= 15.0 else "FAIL"
        if verdict == "FAIL":
            print("    Below the +15% pre-registered bar. The gate does not earn its place.")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict=verdict,
        metrics={
            label: {
                "vol_target": s.vol_target,
                "return_pct": round(s.performance.ann_return_pct, 3),
                "p95_dd_pct": round(s.p95_drawdown_pct, 2),
                "usd_on_10k": round(s.dollars(CAPITAL)),
            }
            for label, (s, _) in results.items()
        },
        notes="Open interest was the last free non-price input available.",
    ))

    ok, message = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
