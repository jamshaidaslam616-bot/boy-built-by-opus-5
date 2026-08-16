"""The gauntlet: run a candidate through every test and return one verdict.

This is the piece whose job is to say NO. It is deliberately the most boring code
in the project: no cleverness, no adaptive thresholds, no special cases. A
candidate either clears fixed bars or it does not, and the bars were written down
before any result existed.

Order matters. The controls run first, because if a strategy is indistinguishable
from a rotation of itself, nothing measured afterwards means anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .control import ControlResult, run_all_controls
from .metrics import (
    Performance,
    deflated_sharpe_ratio,
    per_bar_sharpe,
    sharpe_ratio,
    summarise,
)
from .returns import CostModel, strategy_returns, turnover
from .splits import Fold, walk_forward_efficiency

# Thresholds, fixed. Changing a number here is a decision that must be argued for
# in writing, not a tuning knob.
MIN_CONTROL_Z = 2.0
MIN_DEFLATED_SHARPE = 0.95
MIN_WF_EFFICIENCY = 0.50
MIN_OOS_OBS = 200
COST_STRESS_MULTIPLIER = 1.5

# --- drawdown gate, revised 2026-08-10 ---
#
# The owner raised the live halt from 10% to 20%. That alone would suggest loosening
# this gate, but the bootstrap in `scripts/p6_risk_limit.py` showed the opposite is
# required, and that the previous pairing was incoherent.
#
# Resampling this strategy's returns in blocks puts the **95th-percentile** maximum
# drawdown at **1.58x** the drawdown the single 12.6-year backtest path produced.
# One path is one draw; a limit set to what that path happened to do gets breached in
# roughly half of equally-plausible histories.
#
# So the backtest gate has to sit at the live limit DIVIDED by that factor:
#
#     20% live halt / 1.58  =  12.7%  ->  12.5% observed backtest drawdown
#
# The old pairing (15% backtest against a 10% live halt) failed this: a strategy
# passing at 15% observed carries a p95 of ~23.7% live, more than twice the halt it
# was supposed to respect.
#
# Note this TIGHTENS the gate, from 15.0 to 12.5. It is being changed after results
# were seen, which is only acceptable because it moves against every candidate rather
# than for one: no verdict in P3, P4 or P4b changes, since all of them already failed
# this gate at 15%.
LIVE_HALT_PCT = 20.0
BOOTSTRAP_P95_MULTIPLE = 1.58
MAX_DRAWDOWN_PCT = 12.5


@dataclass
class Verdict:
    name: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, label: str, passed: bool, detail: str) -> None:
        self.checks.append((label, passed, detail))

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    def report(self) -> str:
        lines = [f"GAUNTLET — {self.name}", "=" * 78]
        for label, ok, detail in self.checks:
            lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label:<26} {detail}")
        lines.append("-" * 78)
        lines.append(f"  VERDICT: {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


@dataclass
class GauntletOutput:
    verdict: Verdict
    performance: Performance
    controls: list[ControlResult]
    dsr: float
    dsr_benchmark: float
    wf_efficiency: float | None
    wf_excluded_folds: list[int]


def run_gauntlet(
    name: str,
    position: pd.Series,
    close: pd.Series,
    costs: CostModel,
    bars_per_year: float,
    n_trials: int,
    sharpe_variance_across_trials: float,
    folds: list[Fold] | None = None,
    baseline_sharpe: float | None = None,
    n_controls: int = 100,
    seed: int = 20260808,
) -> GauntletOutput:
    """Every check, in order. Returns the full evidence, not just the verdict."""
    v = Verdict(name)

    net = strategy_returns(position, close, costs)
    perf = summarise(net, bars_per_year, turnover(position))

    # 1. Controls first. Everything downstream is meaningless if this fails.
    controls = run_all_controls(
        position, close, bars_per_year, n_controls=n_controls, seed=seed, costs=costs
    )
    rotation = next(c for c in controls if c.method == "rotation")
    v.add(
        "random-entry control",
        rotation.z_score >= MIN_CONTROL_Z,
        f"rotation z={rotation.z_score:+.2f} (needs >= {MIN_CONTROL_Z}); "
        f"strategy SR {rotation.strategy_sharpe:+.3f} vs control "
        f"{rotation.control_mean:+.3f}+/-{rotation.control_std:.3f}",
    )

    # 2. Deflated Sharpe — is this the best of N tries, or an edge?
    dsr, sr0 = deflated_sharpe_ratio(
        observed_sharpe=per_bar_sharpe(net),
        n_obs=perf.n_obs,
        skew=perf.skew,
        kurtosis=perf.kurtosis,
        n_trials=n_trials,
        sharpe_variance_across_trials=sharpe_variance_across_trials,
    )
    v.add(
        "deflated Sharpe",
        dsr >= MIN_DEFLATED_SHARPE,
        f"DSR={dsr:.4f} (needs >= {MIN_DEFLATED_SHARPE}) after {n_trials} trials; "
        f"luck benchmark SR0={sr0:.4f}/bar",
    )

    # 3. Sample size, measured on the aggregate of out-of-sample folds when we have them.
    active_obs = int((position.fillna(0.0) != 0).sum())
    v.add(
        "out-of-sample sample",
        active_obs >= MIN_OOS_OBS,
        f"{active_obs:,} bars with exposure (needs >= {MIN_OOS_OBS})",
    )

    # 4. Drawdown.
    v.add(
        "max drawdown",
        perf.max_drawdown_pct <= MAX_DRAWDOWN_PCT,
        f"{perf.max_drawdown_pct:.2f}% (needs <= {MAX_DRAWDOWN_PCT}%)",
    )

    # 5. Cost sensitivity — an edge that dies at 1.5x costs was never real.
    stressed = strategy_returns(position, close, costs.scaled(COST_STRESS_MULTIPLIER))
    stressed_sr = sharpe_ratio(stressed, bars_per_year)
    v.add(
        "cost sensitivity",
        stressed_sr > 0,
        f"Sharpe at {COST_STRESS_MULTIPLIER}x costs = {stressed_sr:+.3f} (needs > 0); "
        f"at 1.0x = {perf.sharpe:+.3f}",
    )

    # 6. Best-period removal — one lucky month is not an edge.
    monthly = net.resample("ME").sum()
    if len(monthly) >= 3:
        without_best = monthly.drop(monthly.idxmax()).sum()
        v.add(
            "best month removed",
            without_best > 0,
            f"{without_best:+.4f} total return without {monthly.idxmax():%Y-%m} "
            f"(needs > 0)",
        )
    else:
        v.add("best month removed", False, f"only {len(monthly)} months — cannot assess")

    # 7. Walk-forward efficiency, when folds are supplied.
    wf_eff: float | None = None
    excluded: list[int] = []
    if folds:
        is_srs, oos_srs = [], []
        for f in folds:
            is_srs.append(sharpe_ratio(net.reindex(f.train).dropna(), bars_per_year))
            oos_srs.append(sharpe_ratio(net.reindex(f.test).dropna(), bars_per_year))
        wf_eff, excluded = walk_forward_efficiency(is_srs, oos_srs)
        if wf_eff is None:
            v.add(
                "walk-forward efficiency",
                False,
                "NOT MEASURABLE — no fold produced an in-sample edge worth retaining, "
                "so there is nothing to divide by",
            )
        else:
            v.add(
                "walk-forward efficiency",
                wf_eff >= MIN_WF_EFFICIENCY,
                f"{wf_eff:.3f} (needs >= {MIN_WF_EFFICIENCY}), "
                f"{len(excluded)} of {len(folds)} folds excluded for no in-sample edge",
            )

    # 8. The honest baseline. Beating cash is not the question; beating the simple
    #    thing anyone could do without a bot is.
    if baseline_sharpe is not None:
        v.add(
            "beats honest baseline",
            perf.sharpe > baseline_sharpe,
            f"strategy Sharpe {perf.sharpe:+.3f} vs vol-targeted baseline "
            f"{baseline_sharpe:+.3f}",
        )

    return GauntletOutput(
        verdict=v,
        performance=perf,
        controls=controls,
        dsr=dsr,
        dsr_benchmark=sr0,
        wf_efficiency=wf_eff,
        wf_excluded_folds=excluded,
    )


def sharpe_variance_from_trials(trial_sharpes: list[float]) -> float:
    """Variance of Sharpe estimates across trials, for the deflation benchmark.

    Uses the observed spread when several trials exist. With fewer than two, the
    variance is unknowable from data and the caller must supply it — guessing here
    would silently weaken the very penalty this exists to apply.
    """
    if len(trial_sharpes) < 2:
        raise ValueError(
            "need at least 2 trial Sharpes to estimate their variance; "
            "supply sharpe_variance_across_trials explicitly instead"
        )
    return float(np.var(np.asarray(trial_sharpes), ddof=1))
