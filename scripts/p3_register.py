"""Register every P3 candidate BEFORE any of them is tested.

Run this once. It writes each hypothesis — the claim, why the market should behave
that way, the pass bar, and how many parameter combinations will be tried — into the
hash-chained log. The runner refuses to score anything that is not in here.

The order is the point. Registering first makes "we expected that" checkable, and it
fixes the trial count before anyone has seen which candidate looks good.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.research.prereg import Hypothesis, PreRegistrationLog  # noqa: E402

LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"

PASS_BAR = {
    "control_rotation_z": 2.0,
    "deflated_sharpe": 0.95,
    "wf_efficiency": 0.50,
    "max_drawdown_pct": 15.0,
    "beats_baseline_sharpe": 0.502,
}

SCOPE_D1 = "XAUUSD D1, 2014-01-14..2026-08-07, 3,867 bars, Exness Zero, costs per COSTS.md"

HYPOTHESES = [
    Hypothesis(
        name="A1a-timeseries-momentum",
        family="A1",
        claim="Gold's daily returns show positive serial dependence over 50-200 day horizons, "
              "so the sign of the trailing return predicts the next day's direction.",
        economic_rationale="Macro information relevant to gold (real yields, central bank demand, "
                           "reserve diversification) diffuses slowly into a market whose "
                           "participants have very different horizons, producing under-reaction. "
                           "This is the one price-only effect with published out-of-sample "
                           "survival across a century and across asset classes.",
        pass_criteria=PASS_BAR,
        n_param_combinations=3,
        data_scope=SCOPE_D1,
        predicted_outcome="Most likely to survive of anything here, but I expect it to land close "
                          "to the +0.502 baseline rather than clearly above it — because the "
                          "baseline IS a trend rule, so this is largely being tested against "
                          "itself.",
    ),
    Hypothesis(
        name="A1b-ma-crossover",
        family="A1",
        claim="A fast moving average above a slow one predicts positive gold returns, and below "
              "predicts negative.",
        economic_rationale="Same under-reaction mechanism as A1a, expressed as a smoothed state "
                           "rather than a point-to-point return. Smoothing should cut turnover, "
                           "which matters because this venue charges $11/lot on every open.",
        pass_criteria=PASS_BAR,
        n_param_combinations=3,
        data_scope=SCOPE_D1,
        predicted_outcome="Very close to A1a and to the baseline. If it differs much from either, "
                          "that difference is more likely parameter luck than a distinct effect.",
    ),
    Hypothesis(
        name="A1c-confidence-trend",
        family="A1",
        claim="Scaling exposure by trend CONVICTION, rather than flipping between full long and "
              "full short, improves risk-adjusted return net of costs.",
        economic_rationale="The published gold-futures result attributes its performance to the "
                           "pipeline — bounded confidence mapping, volatility targeting, "
                           "friction-aware sizing — rather than to the signal, which is a plain "
                           "EMA. If that is right, the same weak signal shaped this way should "
                           "beat the binary version, mostly by trading less.",
        pass_criteria=PASS_BAR,
        n_param_combinations=2,
        data_scope=SCOPE_D1,
        predicted_outcome="Better than A1a/A1b on turnover and therefore on net Sharpe, but by a "
                          "small margin. I do not expect it to reach the Sharpe 2.88 of the "
                          "published result — that figure sits at 0.91% realised volatility where "
                          "estimation error is large.",
    ),
    Hypothesis(
        name="A10-volatility-breakout",
        family="A10",
        claim="A close beyond an N-day channel, taken only when volatility sits in a middle band, "
              "predicts continuation.",
        economic_rationale="Breakouts and trend are the same effect sampled differently; the "
                           "volatility band adds the requirement that the expected move can cover "
                           "its own transaction costs, which is a real constraint at $11/lot.",
        pass_criteria=PASS_BAR,
        n_param_combinations=2,
        data_scope=SCOPE_D1,
        predicted_outcome="Fails. The equivalent rule was already shown indistinguishable from "
                          "random entry on this owner's M15 data (z=+0.27). Daily bars give it a "
                          "better chance, but I expect it to be a noisier version of A1.",
    ),
    Hypothesis(
        name="B1-real-yield-regime",
        family="B1",
        claim="Gold outperforms while the 10-year real yield's own multi-month trend is FALLING — "
              "as a slow state, not as a reaction to daily changes.",
        economic_rationale="Gold pays no coupon, so its relative attractiveness rises as the real "
                           "return on the risk-free alternative falls. A 100bp rise in real yields "
                           "has historically accompanied roughly an 18% fall in real gold. The "
                           "level trend moves over months, so a 4-day publication lag cannot "
                           "destroy it — unlike the daily change, which FINDINGS F5 already showed "
                           "collapses from -0.33 to -0.03 once only published data is used.",
        pass_criteria=PASS_BAR,
        n_param_combinations=2,
        data_scope=SCOPE_D1 + "; FRED DFII10 with a 4-day publication lag",
        predicted_outcome="Weak on its own — the state is slow and mostly already in the price. "
                          "More useful as a gate on A1 than as a standalone signal.",
    ),
    Hypothesis(
        name="B2-dollar-regime",
        family="B2",
        claim="Gold outperforms while the broad trade-weighted dollar's multi-month trend is "
              "FALLING.",
        economic_rationale="Gold is priced in dollars, so a weakening dollar mechanically raises "
                           "the dollar price for unchanged demand elsewhere. The broad index is "
                           "used rather than DXY because DXY is heavily euro-weighted and "
                           "correlates with gold less well.",
        pass_criteria=PASS_BAR,
        n_param_combinations=2,
        data_scope=SCOPE_D1 + "; FRED DTWEXBGS with a 10-day publication lag",
        predicted_outcome="Same as B1 — weak alone, possibly useful as a gate.",
    ),
    Hypothesis(
        name="A1xB1-macro-gated-trend",
        family="A1+B1",
        claim="Taking the trend signal ONLY when the real-yield regime agrees beats taking it "
              "unconditionally, net of costs.",
        economic_rationale="Two independent reasons to be long should be better than one. On this "
                           "venue standing aside also stops paying -5.66%/yr financing, so a gate "
                           "earns twice: it avoids bad trades and it avoids rent.",
        pass_criteria=PASS_BAR,
        n_param_combinations=2,
        data_scope=SCOPE_D1 + "; FRED DFII10, 4-day lag",
        predicted_outcome="This is where I would put my money if forced to choose. But BASELINE.md "
                          "showed roughly half of a filter's value here is avoided financing, not "
                          "signal — so any gain must be split before it is called an edge.",
    ),
    Hypothesis(
        name="A1xB2-dollar-gated-trend",
        family="A1+B2",
        claim="Taking the trend signal ONLY when the dollar regime agrees beats taking it "
              "unconditionally.",
        economic_rationale="Same as A1xB1 with the other documented driver.",
        pass_criteria=PASS_BAR,
        n_param_combinations=2,
        data_scope=SCOPE_D1 + "; FRED DTWEXBGS, 10-day lag",
        predicted_outcome="Similar to A1xB1, marginally weaker because the dollar series is "
                          "published later and is therefore staler when used.",
    ),
    Hypothesis(
        name="B3-gold-silver-reversion",
        family="B3",
        claim="The log gold/silver ratio mean-reverts, so a stretched ratio predicts the gold leg "
              "underperforming or outperforming silver accordingly.",
        economic_rationale="Both metals respond to the same macro factors with different betas, "
                           "and silver carries an industrial demand component gold does not. That "
                           "gives the spread an economic anchor a directional gold bet has none of.",
        pass_criteria=PASS_BAR,
        n_param_combinations=2,
        data_scope="XAUUSD and XAGUSD D1, 2014-01-14..2026-08-07",
        predicted_outcome="The idea may have merit but it CANNOT ship on this venue: COSTS.md "
                          "measured that a short earns no financing credit here, so either "
                          "direction pays about -5.7%/yr just to exist. Tested with financing "
                          "reported separately, to decide whether the futures venue is worth "
                          "pursuing. A pass here is a reason to price futures, not to trade CFDs.",
    ),
]


def main() -> int:
    log = PreRegistrationLog(LOG)
    print("=" * 88)
    print("P3 — REGISTERING CANDIDATES (before any is tested)")
    print("=" * 88)

    newly = 0
    for hypothesis in HYPOTHESES:
        if log.is_registered(hypothesis.name):
            print(f"  already registered: {hypothesis.name}")
            continue
        log.register(hypothesis)
        newly += 1
        print(f"  registered  {hypothesis.name:<28} {hypothesis.n_param_combinations:>2} combinations")

    ok, message = log.verify()
    print()
    print(f"  chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    print(f"  newly registered this run: {newly}")
    print(f"  TOTAL TRIALS NOW COUNTED:  {log.trial_count()}")
    print()
    print("  That total is what the Deflated Sharpe will deflate by. It already includes")
    print("  the 19 exploratory cells examined in P2 and the 3 baseline variants, so no")
    print("  candidate gets scored as though it were the first thing anyone looked at.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
