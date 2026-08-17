"""The control on the balanced book — the number the last remeasurement left missing.

P20 remeasured the production path after the balance fix and found Sharpe +0.538 at
$250k. But the control z of +0.78 that every report has been carrying was measured
in P19, on the OLD tilted book. The balanced book has never been asked the only
question that matters: is it distinguishable from a rotation of itself?

Method, and why it is this one. The book's POSITIONS are rotated per instrument and
the P&L recomputed. Rotating returns would be worthless — a Sharpe is a mean over a
standard deviation and rotation changes neither, which is how an earlier attempt
produced a control distribution with a standard deviation of exactly zero. Rotating
positions preserves every property of the strategy — turnover, holding period, leg
count, long/short balance, which instruments it favours — and destroys only the
alignment between the signal and the returns it claims to predict.

If this clears +2.0 it is the first thing in this project to do so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.control import circular_shift_controls  # noqa: E402
from goldlab.research.metrics import sharpe_ratio  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.sizing import bootstrap_max_drawdowns  # noqa: E402
from goldlab.safety import risk  # noqa: E402
from goldlab.strategy import production as prod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
ROLL_BARS = 5
COST_OPEN_BP, COST_CLOSE_BP = 0.47, 0.22
N_CONTROLS = 120
CAPITAL = 250_000.0

HYPOTHESIS = Hypothesis(
    name="P21-balanced-book-control",
    family="production",
    claim="The balanced cross-sectional book is distinguishable from a rotation of itself.",
    economic_rationale="Not a market claim — a test of whether the previous one is real. Every "
                       "figure this project has reported rests on a control measured in P19 on "
                       "a book that was tilted 5-long against 3-short. The balance fix changed "
                       "which instruments are held and removed a directional component nobody "
                       "intended, so the old control does not describe the current strategy and "
                       "cannot be carried forward.",
    pass_criteria={"control_rotation_z": 2.0},
    n_param_combinations=1,
    data_scope=f"25 instruments, D1, production path at ${CAPITAL:,.0f}, {N_CONTROLS} rotations",
    predicted_outcome="I expect it to fail again, somewhere between +0.5 and +1.5. The balance "
                      "fix removed a directional tilt, which should make the result cleaner but "
                      "not create an edge that was not there. If it clears +2.0 it would be the "
                      "first thing in this project to do so, and I would want to re-run it on a "
                      "different seed before believing it. I have been wrong on 5 of 12 "
                      "predictions and the misses have been optimistic.",
)


def build_positions(panel: pd.DataFrame, spec: pd.DataFrame) -> pd.DataFrame:
    """Replay the production path, recording lots held per instrument per bar."""
    vol_panel = panel.pct_change().rolling(prod.VOL_LOOKBACK_BARS).std() * np.sqrt(BARS_PER_YEAR)
    start = max(prod.LOOKBACK_BARS, prod.VOL_LOOKBACK_BARS) + 1
    lots = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    held: dict[str, dict] = {}

    for i in range(start, len(panel)):
        prices, vols = panel.iloc[i], vol_panel.iloc[i]
        rebalance = (i - start) % prod.REBALANCE_BARS == 0
        aging = any(i - h["opened_i"] >= ROLL_BARS for h in held.values())

        if rebalance or aging:
            inv = {c: 1.0 / float(vols[c]) for c in panel.columns
                   if np.isfinite(vols[c]) and vols[c] > 0}
            gross = sum(sorted(inv.values(), reverse=True)[: prod.LEGS_PER_SIDE * 2]) or 1.0
            st = risk.RiskState(equity=CAPITAL, peak_equity=CAPITAL)

            def ok(sym, _i=inv, _g=gross, _s=st, _p=prices, _v=vols):
                if sym not in _i or sym not in spec.index:
                    return False
                r = spec.loc[sym]
                try:
                    risk.book_leg_size(
                        _s, symbol=sym, weight=min(_i[sym] / _g, prod.MAX_LEG_WEIGHT),
                        price=float(_p[sym]), annual_vol=float(_v[sym]),
                        contract_size=float(r["contract_size"]),
                        volume_min=float(r["min_lot"]), volume_step=float(r["min_lot"]),
                        volume_max=1e9, n_legs=prod.LEGS_PER_SIDE * 2)
                    return True
                except risk.RiskRefusal:
                    return False

            try:
                targets = prod.compute_targets(panel.iloc[: i + 1], tradeable=ok)
            except ValueError:
                targets = []
            wanted = {t.symbol: t for t in targets}

            for s in list(held):
                h = held[s]
                if (i - h["opened_i"] >= ROLL_BARS or s not in wanted
                        or (h["lots"] > 0) != (wanted[s].weight > 0)):
                    del held[s]

            for t in targets:
                if t.symbol in held:
                    continue
                r = spec.loc[t.symbol]
                try:
                    size = risk.book_leg_size(
                        st, symbol=t.symbol, weight=t.weight, price=float(prices[t.symbol]),
                        annual_vol=float(vols[t.symbol]), contract_size=float(r["contract_size"]),
                        volume_min=float(r["min_lot"]), volume_step=float(r["min_lot"]),
                        volume_max=1e9, n_legs=len(targets))
                except risk.RiskRefusal:
                    continue
                held[t.symbol] = {"lots": size, "opened_i": i}

        for s, h in held.items():
            lots.iloc[i, lots.columns.get_loc(s)] = h["lots"]

    return lots


def book_returns(lots: pd.DataFrame, panel: pd.DataFrame, spec: pd.DataFrame) -> pd.Series:
    """P&L of holding ``lots``, charged for every change in position."""
    contract = pd.Series({c: float(spec.loc[c, "contract_size"]) for c in panel.columns})
    notional = lots.shift(1).fillna(0.0) * contract * panel
    pnl = (lots.shift(1).fillna(0.0) * contract * panel.diff()).sum(axis=1)
    traded = (lots - lots.shift(1).fillna(0.0)).abs() * contract * panel
    cost = traded.sum(axis=1) * COST_OPEN_BP / 10_000.0
    equity = CAPITAL + (pnl - cost).cumsum()
    return equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    spec = pd.read_parquet(ROOT / "universe.parquet").set_index("symbol")
    panel = pd.DataFrame({s: hist.load(ROOT, s, "D1")["close"] for s in prod.UNIVERSE})
    panel = panel.loc[panel.notna().all(axis=1)]
    last = panel.iloc[-1]
    spec = spec.loc[[s for s in prod.UNIVERSE if s in spec.index]].copy()
    spec["contract_size"] = (spec["min_notional"] / spec["min_lot"]) / last[spec.index]

    print("=" * 90)
    print(f"P21 — CONTROL ON THE BALANCED BOOK  (${CAPITAL:,.0f}, {N_CONTROLS} rotations)")
    print("=" * 90)

    print("  replaying the production path ...", flush=True)
    lots = build_positions(panel, spec)
    real = book_returns(lots, panel, spec)
    real_sharpe = sharpe_ratio(real, BARS_PER_YEAR)
    active = int((lots != 0).any(axis=1).sum())
    print(f"  {active:,} bars with exposure · Sharpe {real_sharpe:+.4f}")

    print(f"  rotating positions {N_CONTROLS} times ...", flush=True)
    rng = np.random.default_rng(20260817)
    ctrl = []
    for k in range(N_CONTROLS):
        shifted = pd.DataFrame(
            {c: circular_shift_controls(lots[c], 1, seed=int(rng.integers(1e9)))[0]
             for c in lots.columns}, index=lots.index)
        ctrl.append(sharpe_ratio(book_returns(shifted, panel, spec), BARS_PER_YEAR))
        if (k + 1) % 40 == 0:
            print(f"    {k + 1}/{N_CONTROLS}", flush=True)

    ctrl = np.asarray(ctrl)
    z = (real_sharpe - ctrl.mean()) / ctrl.std(ddof=1)
    pct = float((ctrl < real_sharpe).mean() * 100)
    passed = bool(z >= 2.0)

    print("\n" + "=" * 90)
    print("  RESULT")
    print("=" * 90)
    print(f"    strategy          {real_sharpe:+.4f}")
    print(f"    rotations         {ctrl.mean():+.4f} +/- {ctrl.std(ddof=1):.4f}  "
          f"(range {ctrl.min():+.3f} .. {ctrl.max():+.3f})")
    print(f"    z-score           {z:+.2f}   percentile {pct:.1f}")
    print(f"    VERDICT           {'PASS' if passed else 'FAIL'}  (needs z >= +2.00)")
    if real_sharpe > 0:
        print(f"    years to prove    {(2.0 / real_sharpe) ** 2:.1f}  "
              f"(this window has {len(real) / BARS_PER_YEAR:.1f})")

    if passed:
        print("\n    This would be the FIRST thing in this project to clear its control.")
        print("    Before it is leaned on it must be re-run on a different seed, because a")
        print("    single passing result is exactly what ~80 combinations of searching")
        print("    would eventually produce by chance.")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if passed else "FAIL",
        metrics={"sharpe": round(real_sharpe, 4), "control_mean": round(float(ctrl.mean()), 4),
                 "control_sd": round(float(ctrl.std(ddof=1)), 4), "z": round(float(z), 3),
                 "percentile": round(pct, 1), "capital": CAPITAL},
        notes="Positions rotated, not returns. Measured on the balanced book, which the "
              "P19 control (z=+0.78) did not describe.",
    ))
    ok, msg = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
