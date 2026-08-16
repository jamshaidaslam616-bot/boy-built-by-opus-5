"""Open the pre-registration log by declaring the exploration ALREADY done.

Every look at the data spends statistical budget, including the exploratory ones
that came before any hypothesis was written. P2's COT work examined 19 separate
cells (5 buckets x 3 horizons, plus 4 trend-control cells) before anything was
registered. Leaving those out of the trial count would understate the
multiple-testing penalty on everything registered afterwards.

So the first entry in the log is a confession, not a hypothesis.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402

LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"


def main() -> int:
    log = PreRegistrationLog(LOG)

    if not log.is_registered("P2-exploration-already-spent"):
        log.register(Hypothesis(
            name="P2-exploration-already-spent",
            family="bookkeeping",
            claim=(
                "Exploratory analysis performed during P2, declared so that the "
                "multiple-testing penalty on later hypotheses is not understated."
            ),
            economic_rationale=(
                "Not a market claim. Every cell examined before a hypothesis is written "
                "still spends search budget, and a trial count that omits the looking "
                "already done makes every subsequent Deflated Sharpe too generous."
            ),
            pass_criteria={},
            n_param_combinations=19,
            data_scope=(
                "XAUUSD D1 2014-2026 and CFTC COT gold 2013-2026. Cells examined: "
                "5 positioning buckets x 3 forward horizons (1/4/13 weeks) = 15, "
                "plus 4 trend-control cells (uptrend/downtrend x crowded/not) = 19."
            ),
            predicted_outcome=(
                "No prediction — this records cost, not a claim."
            ),
        ))
        log.record_result(Result(
            hypothesis_name="P2-exploration-already-spent",
            verdict="NOT-MEASURABLE",
            metrics={"cells_examined": 19},
            notes=(
                "Findings from this exploration are in FINDINGS.md F5 and F6 and are "
                "explicitly labelled exploratory. Nothing from it may ship without being "
                "re-registered as a hypothesis and re-tested out-of-sample."
            ),
        ))

    if not log.is_registered("P1-baseline-locked"):
        log.register(Hypothesis(
            name="P1-baseline-locked",
            family="bookkeeping",
            claim=(
                "The no-bot baseline on XAUUSD D1, net of measured costs and financing, "
                "is a Sharpe of +0.502 (200-day trend overlay, vol-targeted to 10%)."
            ),
            economic_rationale=(
                "A trading system's job is to beat what the owner could have done without "
                "it. Fixing that number before any candidate exists prevents a baseline "
                "being chosen later that a candidate happens to clear."
            ),
            pass_criteria={"baseline_sharpe_to_beat": 0.502},
            n_param_combinations=3,
            data_scope="XAUUSD D1, 2014-01-14..2026-08-07, Exness Zero, 3,867 bars",
            predicted_outcome=(
                "Most candidates will fail to beat this. A 200-day moving average is a "
                "stronger benchmark than its simplicity suggests, especially once this "
                "broker's -5.66%/yr long financing rewards being out of the market."
            ),
        ))
        log.record_result(Result(
            hypothesis_name="P1-baseline-locked",
            verdict="PASS",
            metrics={
                "buy_hold_sharpe_net": 0.260,
                "buy_hold_voltargeted_sharpe_net": 0.277,
                "trend_overlay_sharpe_net": 0.502,
                "trend_overlay_sharpe_gross": 0.814,
            },
            notes="Full detail in BASELINE.md. This is the gauntlet's 'beats honest baseline' gate.",
        ))

    ok, message = log.verify()
    print("=" * 84)
    print("PRE-REGISTRATION LOG")
    print("=" * 84)
    print(f"  path            {LOG}")
    print(f"  chain           {'INTACT' if ok else 'BROKEN'} — {message}")
    print(f"  trials counted  {log.trial_count()}")
    print()
    for entry in log.entries():
        if entry.kind == "hypothesis":
            print(f"  [{entry.seq}] {entry.payload['name']:<32} "
                  f"{entry.payload['n_param_combinations']:>3} combinations   "
                  f"{entry.timestamp_utc}")
        else:
            print(f"      -> result: {entry.payload['verdict']}")
    print()
    print("  Every hypothesis registered from here on inherits this trial count, so the")
    print("  Deflated Sharpe bar starts already raised by the searching done in P2.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
