"""P4 — is a portfolio of weak signals better than the best single one?

P3 killed every candidate individually. That is not the end of the question,
because the standard professional answer to a weak single signal is not a better
signal — it is several imperfectly-correlated ones run together. Two uncorrelated
Sharpe-0.4 streams combine to about 0.57; three to about 0.69. No new insight
required, only genuine diversification.

The catch is the word *genuine*. If every candidate is the same trend signal wearing
different parameters, combining them changes nothing except the illusion of breadth.
So this measures the correlation matrix FIRST, and only then asks what a combination
does.

The specific thing being tested — a multi-speed trend ensemble — is registered as a
new hypothesis before it is scored, exactly like everything in P3.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.gauntlet import run_gauntlet  # noqa: E402
from goldlab.research.metrics import summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, turnover, vol_target  # noqa: E402
from goldlab.research.splits import purged_walk_forward  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
BASELINE_SHARPE = 0.502
CAPITAL = 10_000.0
SPEEDS = (20, 50, 100, 200, 400)

HYPOTHESIS = Hypothesis(
    name="P4-multispeed-trend-ensemble",
    family="A1-portfolio",
    claim="Averaging trend signals across several lookback horizons produces a higher "
          "return-per-drawdown than the best single horizon, because the horizons "
          "disagree at turning points and their errors partly cancel.",
    economic_rationale="Trend following has one signal and many possible speeds. A fast "
                       "horizon catches reversals early and whipsaws in chop; a slow one "
                       "rides long moves and gives back more at the turn. Their mistakes "
                       "are made at different times, so an average is smoother than any "
                       "component even though every component is the same idea. This is "
                       "why managed-futures funds run a spectrum of speeds rather than "
                       "picking one — and it is a diversification claim, not an alpha claim.",
    pass_criteria={
        "control_rotation_z": 2.0, "deflated_sharpe": 0.95, "wf_efficiency": 0.50,
        "max_drawdown_pct": 15.0, "beats_baseline_sharpe": 0.502,
    },
    n_param_combinations=2,
    data_scope="XAUUSD D1, 2014-01-14..2026-08-07, speeds 20/50/100/200/400",
    predicted_outcome="I expect a REAL but SMALL improvement — a higher Sharpe than any single "
                      "speed and a shallower drawdown, but not enough to clear the deflated "
                      "Sharpe bar after 44 trials. The components are all the same signal, so "
                      "their correlations should be high (I would guess 0.6-0.85) and "
                      "diversification maths only pays when correlations are low.",
)


def costs(carry_long: float = -5.66) -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=carry_long, carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR,
    )


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    close = hist.load(ROOT, "XAUUSD", "D1")["close"]

    # --- 1. Are the components actually different from each other? ---
    raw = {f"trend_{n}": C.a1_timeseries_momentum(close, n) for n in SPEEDS}
    streams = {
        name: strategy_returns(
            vol_target(pos, close, 0.10, 60, BARS_PER_YEAR), close, costs()
        )
        for name, pos in raw.items()
    }
    corr = pd.DataFrame(streams).corr()

    print("=" * 96)
    print("P4 — CORRELATION FIRST: are these different bets, or one bet five times?")
    print("=" * 96)
    print(corr.round(3).to_string())

    off_diagonal = corr.to_numpy()[np.triu_indices(len(corr), k=1)]
    mean_corr = float(off_diagonal.mean())
    print(f"\n  mean pairwise correlation: {mean_corr:.3f}  "
          f"(range {off_diagonal.min():.3f} .. {off_diagonal.max():.3f})")

    # The diversification maths, stated before the result so it cannot be spun after.
    n = len(SPEEDS)
    multiplier = np.sqrt(n / (1 + (n - 1) * mean_corr))
    print(f"  a {n}-stream average at that correlation multiplies Sharpe by "
          f"{multiplier:.3f}x in theory")
    print(f"  best single-speed Sharpe here is "
          f"{max(summarise(s, BARS_PER_YEAR).sharpe for s in streams.values()):+.3f}, so the")
    print(f"  theoretical ceiling for the ensemble is about "
          f"{max(summarise(s, BARS_PER_YEAR).sharpe for s in streams.values()) * multiplier:+.3f}")

    # --- 2. The ensemble itself ---
    equal_weight = sum(raw.values()) / len(raw)
    ensembles = {
        "equal-weight, long/short": equal_weight,
        "equal-weight, long-only": equal_weight.clip(lower=0.0),
    }

    print("\n" + "=" * 96)
    print("MEASURED — single speeds versus the ensemble, all vol-targeted to 10%")
    print("=" * 96)
    print(f"  {'strategy':<30} {'Sharpe':>8} {'ret%':>7} {'maxDD':>7} {'Calmar':>7} {'turn/yr':>8}")
    print("  " + "-" * 76)

    rows = []
    for name, pos in list(raw.items()) + list(ensembles.items()):
        sized = vol_target(pos, close, 0.10, 60, BARS_PER_YEAR)
        perf = summarise(strategy_returns(sized, close, costs()), BARS_PER_YEAR, turnover(sized))
        calmar = perf.ann_return_pct / perf.max_drawdown_pct if perf.max_drawdown_pct > 0 else 0.0
        rows.append((name, perf, calmar))
        marker = "  <-- ensemble" if name in ensembles else ""
        print(f"  {name:<30} {perf.sharpe:>+8.3f} {perf.ann_return_pct:>+7.2f} "
              f"{perf.max_drawdown_pct:>7.2f} {calmar:>7.3f} {perf.turnover_per_year:>8.0f}{marker}")

    best_single = max((r for r in rows if r[0] in raw), key=lambda r: r[2])
    best_ens = max((r for r in rows if r[0] in ensembles), key=lambda r: r[2])
    print(f"\n  best single speed by Calmar: {best_single[0]} ({best_single[2]:.3f})")
    print(f"  best ensemble by Calmar:     {best_ens[0]} ({best_ens[2]:.3f})")
    print(f"  improvement: {(best_ens[2] / best_single[2] - 1) * 100:+.1f}% return per unit "
          f"of drawdown")

    # --- 3. What it pays at a size that respects the owner's limit ---
    print("\n" + "=" * 96)
    print("AT A COMPLIANT SIZE — the only number that matters")
    print("=" * 96)
    for name, pos in ensembles.items():
        for target in (0.10, 0.06, 0.05, 0.04, 0.03):
            sized = vol_target(pos, close, target, 60, BARS_PER_YEAR)
            perf = summarise(strategy_returns(sized, close, costs()), BARS_PER_YEAR)
            if perf.max_drawdown_pct <= 10.0:
                print(f"  {name:<30} largest compliant size {target:.0%}: "
                      f"{perf.ann_return_pct:+.2f}%/yr = "
                      f"${CAPITAL * perf.ann_return_pct / 100:+,.0f} on ${CAPITAL:,.0f} "
                      f"(maxDD {perf.max_drawdown_pct:.2f}%)")
                break
        else:
            print(f"  {name:<30} no tested size respects the 10% live limit")

    # --- 4. Through the gauntlet, same bar as everything else ---
    folds = purged_walk_forward(
        close.index, n_folds=4, lookback_bars=400, holding_bars=20, min_train_bars=900
    )
    n_trials = log.trial_count()
    best_out = None
    print("\n" + "=" * 96)
    print(f"THE GAUNTLET — deflating by {n_trials} trials")
    print("=" * 96)
    for name, pos in ensembles.items():
        sized = vol_target(pos, close, 0.10, 60, BARS_PER_YEAR)
        out = run_gauntlet(
            name=f"P4 {name}", position=sized, close=close, costs=costs(),
            bars_per_year=BARS_PER_YEAR, n_trials=n_trials,
            sharpe_variance_across_trials=0.1030 / BARS_PER_YEAR,
            folds=folds, baseline_sharpe=BASELINE_SHARPE, n_controls=100, seed=20260809,
        )
        print("\n" + out.verdict.report())
        if best_out is None or out.performance.sharpe > best_out[1].performance.sharpe:
            best_out = (name, out)

    name, out = best_out
    rotation = next(c for c in out.controls if c.method == "rotation")
    failed = [lbl for lbl, ok, _ in out.verdict.checks if not ok]
    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if out.verdict.passed else "FAIL",
        metrics={
            "best_variant": name,
            "mean_pairwise_correlation": round(mean_corr, 3),
            "theoretical_sharpe_multiplier": round(float(multiplier), 3),
            "sharpe": round(out.performance.sharpe, 4),
            "max_drawdown_pct": round(out.performance.max_drawdown_pct, 3),
            "calmar_improvement_vs_best_single_pct": round(
                (best_ens[2] / best_single[2] - 1) * 100, 1
            ),
            "control_rotation_z": round(rotation.z_score, 3),
            "deflated_sharpe": round(out.dsr, 4),
        },
        notes=("passed every gate" if out.verdict.passed else "failed: " + "; ".join(failed)),
    ))

    ok, message = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
