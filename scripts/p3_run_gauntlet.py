"""Run every registered candidate through the gauntlet, once.

Refuses to score anything that was not pre-registered. Two passes: the first
collects each combination's Sharpe so the spread across trials can be measured,
the second applies the full gauntlet with deflation calibrated to that spread and
to the trial count the log has been accumulating since P2.

Results are written back into the hash-chained log, so the record shows what was
predicted and what happened, side by side, with neither editable afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.data.macro import MacroSeries  # noqa: E402
from goldlab.research.gauntlet import run_gauntlet  # noqa: E402
from goldlab.research.metrics import sharpe_ratio  # noqa: E402
from goldlab.research.prereg import PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, vol_target  # noqa: E402
from goldlab.research.splits import purged_walk_forward  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
TARGET_VOL = 0.10
VOL_LOOKBACK = 60
BASELINE_SHARPE = 0.502


def costs(carry_long: float = -5.66) -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=carry_long, carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR,
    )


def load_macro(series_id: str, index: pd.DatetimeIndex) -> pd.Series:
    df = pd.read_parquet(ROOT / f"macro_{series_id}.parquet")
    macro = MacroSeries(
        series_id=series_id, name=series_id, values=df["value"],
        publication_lag_days=int(df["publication_lag_days"].iloc[0]),
    )
    return macro.as_known_on(index)


def build_all() -> dict[str, list[tuple[str, pd.Series]]]:
    """Every candidate, every parameter combination. Raw positions, unsized."""
    gold = hist.load(ROOT, "XAUUSD", "D1")
    close, high, low = gold["close"], gold["high"], gold["low"]

    silver = hist.load(ROOT, "XAGUSD", "D1")["close"].reindex(close.index).ffill()
    real_yield = load_macro("DFII10", close.index)
    dollar = load_macro("DTWEXBGS", close.index)

    base_trend = C.a1_timeseries_momentum(close, 100)

    return {
        "A1a-timeseries-momentum": [
            (f"lookback={n}", C.a1_timeseries_momentum(close, n)) for n in (50, 100, 200)
        ],
        "A1b-ma-crossover": [
            (f"fast={f},slow={s}", C.a1_ma_crossover(close, f, s))
            for f, s in ((20, 100), (50, 200), (20, 200))
        ],
        "A1c-confidence-trend": [
            (f"span={sp},mom={m}", C.a1_confidence_trend(close, sp, m))
            for sp, m in ((50, 100), (100, 200))
        ],
        "A10-volatility-breakout": [
            (f"channel={ch}", C.a10_volatility_breakout(high, low, close, ch, 14, 0.2, 0.8))
            for ch in (20, 50)
        ],
        "B1-real-yield-regime": [
            (f"lookback={n}", C.b1_real_yield_regime(real_yield, n)) for n in (60, 120)
        ],
        "B2-dollar-regime": [
            (f"lookback={n}", C.b2_dollar_regime(dollar, n)) for n in (60, 120)
        ],
        "A1xB1-macro-gated-trend": [
            (f"gate={n}", C.combine_gate(base_trend, C.b1_real_yield_regime(real_yield, n)))
            for n in (60, 120)
        ],
        "A1xB2-dollar-gated-trend": [
            (f"gate={n}", C.combine_gate(base_trend, C.b2_dollar_regime(dollar, n)))
            for n in (60, 120)
        ],
        "B3-gold-silver-reversion": [
            (f"lookback={n}", C.b3_ratio_reversion(close, silver, n, 2.0)) for n in (60, 120)
        ],
    }, close


def main() -> int:
    log = PreRegistrationLog(LOG)
    ok, message = log.verify()
    if not ok:
        print(f"REFUSING TO RUN — pre-registration chain is broken: {message}")
        return 1

    all_candidates, close = build_all()

    unregistered = [n for n in all_candidates if not log.is_registered(n)]
    if unregistered:
        print(f"REFUSING TO RUN — not pre-registered: {unregistered}")
        return 1

    n_trials = log.trial_count()
    folds = purged_walk_forward(
        close.index, n_folds=4, lookback_bars=200, holding_bars=20, min_train_bars=900
    )

    print("=" * 108)
    print("P3 — THE GAUNTLET")
    print("=" * 108)
    print(f"  {len(all_candidates)} registered hypotheses, "
          f"{sum(len(v) for v in all_candidates.values())} parameter combinations")
    print(f"  deflating by {n_trials} trials counted since P2")
    print(f"  baseline to beat: Sharpe {BASELINE_SHARPE:+.3f}")
    print(f"  {len(folds)} walk-forward folds, 20-bar purge")

    # Pass 1 — measure the spread of Sharpes across every trial, for deflation.
    sized: dict[str, list[tuple[str, pd.Series]]] = {}
    trial_sharpes: list[float] = []
    for name, combos in all_candidates.items():
        sized[name] = []
        for label, raw in combos:
            pos = vol_target(raw, close, TARGET_VOL, VOL_LOOKBACK, BARS_PER_YEAR)
            sized[name].append((label, pos))
            trial_sharpes.append(sharpe_ratio(strategy_returns(pos, close, costs()), BARS_PER_YEAR))

    ann_var = float(np.var(np.asarray(trial_sharpes), ddof=1))
    per_bar_var = ann_var / BARS_PER_YEAR
    print(f"  observed spread of trial Sharpes: variance {ann_var:.4f} annualised "
          f"({per_bar_var:.6f} per bar)")

    # Pass 2 — the full gauntlet on each.
    print("\n" + "=" * 108)
    print(f"  {'candidate':<30} {'params':<18} {'Sharpe':>8} {'ret%':>7} {'maxDD':>7} "
          f"{'ctrl z':>7} {'DSR':>7} {'long%':>6} {'verdict':>8}")
    print("  " + "-" * 104)

    survivors, per_hypothesis = [], {}
    for name, combos in sized.items():
        best = None
        for label, pos in combos:
            out = run_gauntlet(
                name=f"{name} [{label}]", position=pos, close=close, costs=costs(),
                bars_per_year=BARS_PER_YEAR, n_trials=n_trials,
                sharpe_variance_across_trials=per_bar_var, folds=folds,
                baseline_sharpe=BASELINE_SHARPE, n_controls=100, seed=20260809,
            )
            rotation = next(c for c in out.controls if c.method == "rotation")
            exposure = pos[pos != 0]
            long_share = float((exposure > 0).mean() * 100.0) if len(exposure) else 0.0
            p = out.performance

            print(f"  {name:<30} {label:<18} {p.sharpe:>+8.3f} {p.ann_return_pct:>+7.2f} "
                  f"{p.max_drawdown_pct:>7.2f} {rotation.z_score:>+7.2f} {out.dsr:>7.4f} "
                  f"{long_share:>6.1f} {'PASS' if out.verdict.passed else 'FAIL':>8}")

            if out.verdict.passed:
                survivors.append((name, label, out))
            if best is None or p.sharpe > best[2].performance.sharpe:
                best = (name, label, out)
        per_hypothesis[name] = best

    # Record every outcome back into the log.
    for name, best in per_hypothesis.items():
        _, label, out = best
        rotation = next(c for c in out.controls if c.method == "rotation")
        failed = [lbl for lbl, passed, _ in out.verdict.checks if not passed]
        log.record_result(Result(
            hypothesis_name=name,
            verdict="PASS" if out.verdict.passed else "FAIL",
            metrics={
                "best_params": label,
                "sharpe": round(out.performance.sharpe, 4),
                "ann_return_pct": round(out.performance.ann_return_pct, 3),
                "max_drawdown_pct": round(out.performance.max_drawdown_pct, 3),
                "control_rotation_z": round(rotation.z_score, 3),
                "deflated_sharpe": round(out.dsr, 4),
                "n_trials_deflated_by": n_trials,
            },
            notes=("passed every gate" if out.verdict.passed
                   else "failed: " + "; ".join(failed)),
        ))

    print("\n" + "=" * 108)
    print("VERDICT")
    print("=" * 108)
    if survivors:
        print(f"  {len(survivors)} combination(s) cleared every gate:")
        for name, label, out in survivors:
            print(f"    {name} [{label}]  Sharpe {out.performance.sharpe:+.3f}, DSR {out.dsr:.4f}")
        print("\n  Detailed scorecards:")
        for _, _, out in survivors:
            print("\n" + out.verdict.report())
    else:
        print("  NOTHING PASSED.")
        print()
        print("  This is a legitimate result, and it was cheap. Per the plan, the next step")
        print("  that brings genuinely NEW information is order flow (P5) — everything tested")
        print("  here reads the same OHLCV every retail trader already has.")

    print("\n  Gate failure counts across all combinations:")
    tally: dict[str, int] = {}
    for name, combos in sized.items():
        for label, pos in combos:
            pass
    for name, best in per_hypothesis.items():
        for gate, passed, _ in best[2].verdict.checks:
            if not passed:
                tally[gate] = tally.get(gate, 0) + 1
    for gate, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"    {gate:<28} failed by {count} of {len(per_hypothesis)} hypotheses")

    ok, message = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
