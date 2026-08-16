"""Test the direction the data actually points, which is the opposite of everything so far.

P7's diagnostic said two things this project then ignored:

  * **D1 variance ratios run BELOW 1.0** (0.848 at q=32). That is the signature of
    mean reversion. Every D1 strategy built in P3 and P4 was a TREND rule — run on
    the one timeframe whose own statistics say it does not trend.

  * **H1 carries the strongest single statistic in the whole project**: post-up-bar
    continuation of -0.381 bp with t = -2.14. Negative continuation is reversion.
    On average it is 0.81x the round-trip cost, so untradeable as a per-bar effect —
    but an average hides its own tail. Reversion after a LARGE move can be much
    bigger than reversion after a typical one, and only the large ones need to clear
    costs, because only they get traded.

So: mean reversion on D1, and magnitude-conditional reversion on H1. Both are the
opposite of what has been tested for four phases, and both are what the measurement
asked for rather than what the plan assumed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.gauntlet import run_gauntlet  # noqa: E402
from goldlab.research.metrics import annualised_to_per_bar_sharpe_variance, summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, turnover, vol_target  # noqa: E402
from goldlab.research.sizing import largest_compliant_size  # noqa: E402
from goldlab.research.splits import purged_walk_forward  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
CAPITAL = 10_000.0
ROUND_TRIP_BP = 0.47

HYPOTHESES = [
    Hypothesis(
        name="P9a-d1-mean-reversion",
        family="A3-D1",
        claim="Daily gold mean-reverts over multi-week windows, so fading a stretched price "
              "relative to its own moving average predicts positive returns.",
        economic_rationale="P7 measured D1 variance ratios at 0.848 (q=32) — below 1.0 across "
                           "every horizon tested, which is the statistical signature of "
                           "reversion rather than trend. Every previous phase ran trend rules "
                           "here, against what the series itself reports. Economically, gold "
                           "has no cash flow to anchor value, so its price is set by "
                           "positioning flows that overshoot and correct.",
        pass_criteria={"control_rotation_z": 2.0, "deflated_sharpe": 0.95,
                       "max_drawdown_pct": 12.5, "beats_baseline_sharpe": 0.502},
        n_param_combinations=6,
        data_scope="XAUUSD D1, 2014-01-14..2026-08-07, 3,866 bars",
        predicted_outcome="Better than the trend versions on the same data, because the "
                          "direction now matches the measurement. But none of the D1 variance "
                          "ratios was significant (best z = -0.98), so 'reverting' is a lean, "
                          "not a finding, and I expect it to fall short of the bar.",
    ),
    Hypothesis(
        name="P9b-h1-extreme-reversion",
        family="A3-H1",
        claim="On H1, reversion after a LARGE move is big enough to clear costs, even though "
              "the average per-bar reversion is not.",
        economic_rationale="P7 found H1 post-bar continuation of -0.381 bp at t = -2.14, the "
                           "strongest single statistic measured anywhere in this project, and "
                           "it is negative — reversion. It averages 0.81x the round trip, so "
                           "trading every bar loses. But an average is not a tail: a large "
                           "hourly move is more likely to be liquidity-driven overshoot than a "
                           "small one, and only large moves would be traded, so only they have "
                           "to clear the cost.",
        pass_criteria={"control_rotation_z": 2.0, "deflated_sharpe": 0.95,
                       "max_drawdown_pct": 12.5, "beats_baseline_sharpe": 0.502},
        n_param_combinations=4,
        data_scope="XAUUSD H1, 2017-01-01..2026-08-07, 55,683 bars",
        predicted_outcome="This is the most interesting thing the diagnostic found and the one "
                          "I would most like to be right about. But H1 trades often and "
                          "commission is charged wholly on open, so it needs a large "
                          "conditional effect to survive. I expect the effect to grow with move "
                          "size and still lose to costs.",
    ),
]


def costs(bars_per_year: float, multiplier: float = 1.0) -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0,
        bars_per_year=bars_per_year, multiplier=multiplier,
    )


def zscore_reversion(close: pd.Series, lookback: int, entry_z: float) -> pd.Series:
    """Fade a stretched price. Long when cheap versus its own mean, short when rich."""
    mean = close.rolling(lookback, min_periods=lookback).mean()
    sd = close.rolling(lookback, min_periods=lookback).std()
    z = (close - mean) / sd.where(sd > 0)
    raw = pd.Series(0.0, index=close.index)
    raw[z < -entry_z] = 1.0
    raw[z > entry_z] = -1.0
    # Hold until the stretch closes to roughly half, rather than flipping each bar.
    return raw.replace(0.0, np.nan).where(z.abs() > entry_z / 2).ffill().fillna(0.0)


def main() -> int:
    log = PreRegistrationLog(LOG)
    for h in HYPOTHESES:
        if not log.is_registered(h.name):
            log.register(h)
            print(f"registered {h.name} ({h.n_param_combinations} combinations)")

    # --- First: does reversion after a large H1 move actually grow with size? ---
    h1 = hist.load(ROOT, "XAUUSD", "H1")
    h1 = h1.loc[h1.index >= "2017-01-01"]
    h1_ret_bp = h1["close"].pct_change() * 10_000

    print("\n" + "=" * 96)
    print("  DOES H1 REVERSION GROW WITH THE SIZE OF THE MOVE?")
    print("=" * 96)
    prev = h1_ret_bp.shift(1)
    size_rank = prev.abs().rolling(500, min_periods=500).rank(pct=True)
    print(f"    {'prior move size':<22} {'n':>7} {'next bar bp':>13} {'t':>8} {'vs cost':>9}")
    print("    " + "-" * 64)
    for lo, hi, label in ((0.0, 0.5, "smallest half"), (0.5, 0.8, "50-80th pct"),
                          (0.8, 0.95, "80-95th pct"), (0.95, 1.01, "largest 5%")):
        mask = (size_rank >= lo) & (size_rank < hi)
        # Reversion = next bar moves AGAINST the prior one.
        signed = -np.sign(prev[mask]) * h1_ret_bp[mask]
        signed = signed.dropna()
        if len(signed) < 100:
            continue
        t = stats.ttest_1samp(signed, 0.0).statistic
        print(f"    {label:<22} {len(signed):>7,} {signed.mean():>+12.3f} {t:>+8.2f} "
              f"{abs(signed.mean()) / ROUND_TRIP_BP:>8.2f}x")

    print("\n    A reversion strategy only trades the large bucket, so only that row has to")
    print("    clear the cost. If it does not, the effect is real and unreachable.")

    # --- The strategies, through the identical gauntlet ---
    n_trials = log.trial_count()
    print("\n" + "=" * 96)
    print(f"  THE GAUNTLET — deflating by {n_trials} trials")
    print("=" * 96)
    print(f"  {'hypothesis':<26} {'params':<20} {'Sharpe':>8} {'ret%':>7} {'ctrl z':>7} "
          f"{'DSR':>7} {'turn/yr':>8} {'verdict':>8}")
    print("  " + "-" * 94)

    specs = []
    d1 = hist.load(ROOT, "XAUUSD", "D1")["close"]
    for lb in (20, 60, 120):
        for z in (1.5, 2.5):
            specs.append(("P9a-d1-mean-reversion", f"lb={lb},z={z}", d1, 260.0,
                          zscore_reversion(d1, lb, z)))
    h1c = h1["close"]
    for lb in (24, 120):
        for z in (2.0, 3.0):
            specs.append(("P9b-h1-extreme-reversion", f"lb={lb},z={z}", h1c, 24 * 260.0,
                          zscore_reversion(h1c, lb, z)))

    best: dict[str, tuple] = {}
    by_group: dict[str, list[float]] = {}
    sized_specs = []
    for name, label, px, bpy, raw in specs:
        pos = vol_target(raw, px, 0.10, 60 if bpy == 260.0 else 240, bpy)
        sized_specs.append((name, label, px, bpy, raw, pos))
        by_group.setdefault(name, []).append(
            summarise(strategy_returns(pos, px, costs(bpy)), bpy).sharpe
        )

    for name, label, px, bpy, raw, pos in sized_specs:
        var = annualised_to_per_bar_sharpe_variance(
            max(float(np.var(by_group[name], ddof=1)), 1e-6), bpy
        )
        folds = purged_walk_forward(
            px.index, n_folds=4, lookback_bars=120,
            holding_bars=int(bpy / 26), min_train_bars=int(len(px) * 0.25),
        )
        out = run_gauntlet(
            name=f"{name} [{label}]", position=pos, close=px, costs=costs(bpy),
            bars_per_year=bpy, n_trials=n_trials, sharpe_variance_across_trials=var,
            folds=folds, baseline_sharpe=0.502, n_controls=100, seed=20260810,
        )
        rot = next(c for c in out.controls if c.method == "rotation")
        p = out.performance
        print(f"  {name:<26} {label:<20} {p.sharpe:>+8.3f} {p.ann_return_pct:>+7.2f} "
              f"{rot.z_score:>+7.2f} {out.dsr:>7.4f} {p.turnover_per_year:>8.0f} "
              f"{'PASS' if out.verdict.passed else 'FAIL':>8}")
        cur = best.get(name)
        if cur is None or p.sharpe > cur[1].performance.sharpe:
            best[name] = (label, out, px, bpy, raw)

    print("\n" + "=" * 96)
    print("  BEST OF EACH, AT A COMPLIANT SIZE")
    print("=" * 96)
    for name, (label, out, px, bpy, raw) in best.items():
        sized = largest_compliant_size(raw, px, costs(bpy), bpy, n_paths=250)
        if sized:
            print(f"  {name:<26} [{label}] {sized.vol_target:.0%} vol -> "
                  f"{sized.performance.ann_return_pct:+.2f}%/yr = "
                  f"${sized.dollars(CAPITAL):+,.0f}  (p95 DD {sized.p95_drawdown_pct:.1f}%)")
        else:
            print(f"  {name:<26} [{label}] no compliant size")

        rot = next(c for c in out.controls if c.method == "rotation")
        failed = [lbl for lbl, ok, _ in out.verdict.checks if not ok]
        log.record_result(Result(
            hypothesis_name=name,
            verdict="PASS" if out.verdict.passed else "FAIL",
            metrics={
                "best_params": label,
                "sharpe": round(out.performance.sharpe, 4),
                "control_rotation_z": round(rot.z_score, 3),
                "deflated_sharpe": round(out.dsr, 4),
                "compliant_usd_on_10k": round(sized.dollars(CAPITAL)) if sized else None,
            },
            notes=("passed every gate" if out.verdict.passed else "failed: " + "; ".join(failed)),
        ))

    ok, message = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
