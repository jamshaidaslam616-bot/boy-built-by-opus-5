"""Build where the measurement points: H4, not D1.

P7 corrected a real error. Every strategy in P3/P4 was a TREND rule on DAILY bars —
but daily gold's variance ratios run BELOW 1.0 (0.848 at q=32), which is the
signature of mild mean reversion. Trend rules were being run on the one timeframe
whose own statistics say it does not trend. That is a large part of why all nine
hypotheses failed.

H4 is the only timeframe where both conditions point the same way:

    variance ratio  1.034 (> 1, trending)
    continuation    +1.079 bp after an up bar, 2.30x the round-trip cost

Neither reading is individually significant (VR z = +0.67, continuation t = +1.64),
so this is a direction to look, not a discovery. But it is the only direction the
data offers, and it agrees with the owner's earlier project, which flagged H4 from
independent diagnostics before this project existed.

Everything registered before it is scored, and it faces the identical gauntlet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.gauntlet import run_gauntlet  # noqa: E402
from goldlab.research.metrics import annualised_to_per_bar_sharpe_variance, summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, turnover, vol_target  # noqa: E402
from goldlab.research.sizing import largest_compliant_size  # noqa: E402
from goldlab.research.splits import purged_walk_forward  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 6 * 260.0  # H4
CAPITAL = 10_000.0
USABLE_FROM = "2017-01-01"

HYPOTHESES = [
    Hypothesis(
        name="P8a-h4-trend",
        family="A1-H4",
        claim="Time-series momentum on H4 gold bars predicts the next bar's direction, at an "
              "effect size larger than the round-trip cost.",
        economic_rationale="P7 measured H4 as the only timeframe where the variance ratio "
                           "exceeds 1.0 and where post-up-bar continuation (+1.079 bp) is "
                           "larger than a round trip (0.47 bp). Daily bars, by contrast, show "
                           "variance ratios BELOW 1.0 — mild reversion — which is why running "
                           "trend rules there failed. This tests trend on the timeframe whose "
                           "own statistics say it trends.",
        pass_criteria={"control_rotation_z": 2.0, "deflated_sharpe": 0.95,
                       "max_drawdown_pct": 12.5, "beats_baseline_sharpe": 0.502},
        n_param_combinations=5,
        data_scope=f"XAUUSD H4, {USABLE_FROM}..2026-08-07, 15,094 bars",
        predicted_outcome="Better than the D1 versions, because the timeframe now matches the "
                          "signal. But H4 trades roughly six times as often as D1, and "
                          "commission on this account is charged wholly on OPEN, so the cost "
                          "burden scales with trade count. My honest expectation is that the "
                          "gross edge improves and the net edge does not clear the bar. "
                          "Neither of the two supporting statistics was significant on its own.",
    ),
    Hypothesis(
        name="P8b-h4-trend-d1-filtered",
        family="A1-H4",
        claim="H4 momentum taken only in the direction of the daily trend beats H4 momentum "
              "alone.",
        economic_rationale="If H4 carries the tradeable continuation and D1 carries the slower "
                           "regime, using the slow one to choose direction and the fast one to "
                           "choose timing uses each where it measures best. It also cuts trade "
                           "count, which matters when commission is charged per open.",
        pass_criteria={"control_rotation_z": 2.0, "deflated_sharpe": 0.95,
                       "max_drawdown_pct": 12.5, "beats_baseline_sharpe": 0.502},
        n_param_combinations=3,
        data_scope=f"XAUUSD H4 + D1 regime, {USABLE_FROM}..2026-08-07",
        predicted_outcome="The most likely of the two to survive costs, because filtering cuts "
                          "turnover. Still expect it to fall short of the deflated-Sharpe bar "
                          "with 50+ trials counted.",
    ),
]


def costs(multiplier: float = 1.0) -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR, multiplier=multiplier,
    )


def main() -> int:
    log = PreRegistrationLog(LOG)
    for h in HYPOTHESES:
        if not log.is_registered(h.name):
            log.register(h)
            print(f"registered {h.name} ({h.n_param_combinations} combinations)")

    h4 = hist.load(ROOT, "XAUUSD", "H4")
    h4 = h4.loc[h4.index >= USABLE_FROM]
    close = h4["close"]

    d1 = hist.load(ROOT, "XAUUSD", "D1")["close"]
    d1_trend = (d1 > d1.rolling(200, min_periods=200).mean()).astype(float)
    # Reindex the daily regime onto H4 bars, shifted so an H4 bar only ever sees the
    # PREVIOUS completed daily bar's state.
    d1_on_h4 = d1_trend.shift(1).reindex(close.index, method="ffill").fillna(0.0)

    print("\n" + "=" * 104)
    print(f"P8 — H4 STRATEGIES  ({len(close):,} bars, {close.index[0]:%Y-%m-%d} .. "
          f"{close.index[-1]:%Y-%m-%d})")
    print("=" * 104)

    variants: list[tuple[str, str, pd.Series]] = []
    for n in (6, 12, 30, 60, 120):  # ~1 day, 2 days, 1 week, 2 weeks, 1 month
        variants.append(("P8a-h4-trend", f"lookback={n}", C.a1_timeseries_momentum(close, n)))
    for n in (12, 30, 60):
        raw = C.a1_timeseries_momentum(close, n)
        variants.append(("P8b-h4-trend-d1-filtered", f"lookback={n}", raw * d1_on_h4))

    n_trials = log.trial_count()
    folds = purged_walk_forward(
        close.index, n_folds=4, lookback_bars=120, holding_bars=30, min_train_bars=4000
    )

    print(f"  deflating by {n_trials} trials · {len(folds)} walk-forward folds")
    print(f"\n  {'hypothesis':<26} {'params':<14} {'Sharpe':>8} {'ret%':>7} {'maxDD':>7} "
          f"{'ctrl z':>7} {'DSR':>7} {'turn/yr':>8} {'verdict':>8}")
    print("  " + "-" * 100)

    sized_all, results = [], {}
    for name, label, raw in variants:
        pos = vol_target(raw, close, 0.10, 120, BARS_PER_YEAR)
        sized_all.append((name, label, pos))

    trial_sharpes = [
        summarise(strategy_returns(p, close, costs()), BARS_PER_YEAR).sharpe
        for _, _, p in sized_all
    ]
    per_bar_var = annualised_to_per_bar_sharpe_variance(
        float(np.var(trial_sharpes, ddof=1)), BARS_PER_YEAR
    )

    for name, label, pos in sized_all:
        out = run_gauntlet(
            name=f"{name} [{label}]", position=pos, close=close, costs=costs(),
            bars_per_year=BARS_PER_YEAR, n_trials=n_trials,
            sharpe_variance_across_trials=per_bar_var, folds=folds,
            baseline_sharpe=0.502, n_controls=100, seed=20260810,
        )
        rot = next(c for c in out.controls if c.method == "rotation")
        p = out.performance
        print(f"  {name:<26} {label:<14} {p.sharpe:>+8.3f} {p.ann_return_pct:>+7.2f} "
              f"{p.max_drawdown_pct:>7.2f} {rot.z_score:>+7.2f} {out.dsr:>7.4f} "
              f"{p.turnover_per_year:>8.0f} {'PASS' if out.verdict.passed else 'FAIL':>8}")
        best = results.get(name)
        if best is None or p.sharpe > best[1].performance.sharpe:
            results[name] = (label, out, pos)

    print("\n" + "=" * 104)
    print("  BEST OF EACH, AT A COMPLIANT SIZE (20% halt, p95 drawdown)")
    print("=" * 104)
    for name, (label, out, pos) in results.items():
        raw = next(r for n, l, r in variants if n == name and l == label)
        sized = largest_compliant_size(raw, close, costs(), BARS_PER_YEAR, n_paths=300)
        if sized is None:
            print(f"  {name:<26} [{label}] no compliant size")
        else:
            print(f"  {name:<26} [{label}] {sized.vol_target:.0%} vol -> "
                  f"{sized.performance.ann_return_pct:+.2f}%/yr = "
                  f"${sized.dollars(CAPITAL):+,.0f} on ${CAPITAL:,.0f} "
                  f"(p95 DD {sized.p95_drawdown_pct:.1f}%)")

        failed = [lbl for lbl, ok, _ in out.verdict.checks if not ok]
        rot = next(c for c in out.controls if c.method == "rotation")
        log.record_result(Result(
            hypothesis_name=name,
            verdict="PASS" if out.verdict.passed else "FAIL",
            metrics={
                "best_params": label,
                "sharpe": round(out.performance.sharpe, 4),
                "control_rotation_z": round(rot.z_score, 3),
                "deflated_sharpe": round(out.dsr, 4),
                "turnover_per_year": round(out.performance.turnover_per_year, 1),
                "compliant_usd_on_10k": round(sized.dollars(CAPITAL)) if sized else None,
            },
            notes=("passed every gate" if out.verdict.passed else "failed: " + "; ".join(failed)),
        ))

    # Was it the timeframe, or the costs? Report the gross edge separately.
    print("\n" + "=" * 104)
    print("  IS IT THE SIGNAL OR THE COSTS? — best H4 variant, costs on and off")
    print("=" * 104)
    label, out, pos = results["P8a-h4-trend"]
    for mult, tag in ((1.0, "measured costs"), (0.0, "zero costs"), (1.5, "1.5x costs")):
        perf = summarise(strategy_returns(pos, close, costs(mult)), BARS_PER_YEAR, turnover(pos))
        print(f"    {tag:<18} Sharpe {perf.sharpe:+.3f}  return {perf.ann_return_pct:+6.2f}%  "
              f"turnover {perf.turnover_per_year:.0f}/yr")

    ok, message = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
