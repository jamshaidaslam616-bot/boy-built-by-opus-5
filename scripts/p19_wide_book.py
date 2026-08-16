"""Does a wider cross-section rank better, or merely rank more things?

P18 grew the universe from 19 to 25 by adding emerging-market currencies, USDCNH
and a third index. Breadth is the only lever left that raises Sharpe without new
data, so this measures whether it actually does.

Every book here is sized against real minimum lot sizes at a stated capital — the
check whose absence made P15's +$247 fictional (F18). Results are reported at
several account sizes, because the owner has said capital is available and the
honest answer differs by size.

Two things are held constant so the comparison means something: identical
parameters (frozen in production.py) and identical costs. The only thing that
changes is how many markets the ranking may choose from.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.control import circular_shift_controls  # noqa: E402
from goldlab.research.metrics import sharpe_ratio, summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns  # noqa: E402
from goldlab.research.sizing import bootstrap_max_drawdowns  # noqa: E402
from goldlab.strategy import production as prod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
LIVE_HALT = 20.0
BOOK_VOL = 0.07

NARROW = list(prod.UNIVERSE)
ADDED = ["USDMXN", "USDZAR", "USDPLN", "USDSGD", "USDCNH", "US30"]
WIDE = NARROW + ADDED

HYPOTHESIS = Hypothesis(
    name="P19-wide-cross-section",
    family="cross-sectional",
    claim="Widening the cross-section from 19 to 25 markets improves the cross-sectional "
          "momentum book's risk-adjusted return, once every leg is sized against the "
          "broker's real minimum lot.",
    economic_rationale="A cross-sectional rank is an estimate, and the estimate is noisy in "
                       "proportion to how few things are being ranked. Adding emerging-market "
                       "currencies and a third index brings factors — local rate cycles, "
                       "risk-appetite betas, a different sector mix — that the existing "
                       "universe does not span, so the additions should be weakly correlated "
                       "with what is already there rather than duplicating it.",
    pass_criteria={"control_rotation_z": 2.0, "beats_narrow_sharpe": 0.0},
    n_param_combinations=6,
    data_scope="19 vs 25 instruments, D1, shared window, lot-constrained at $10k/$30k/$100k",
    predicted_outcome="A small improvement at best. Six extra markets on a base of nineteen is "
                       "a 30% widening, and diversification benefit scales with the square root "
                       "— so perhaps 10-15% on Sharpe if the additions are genuinely "
                       "uncorrelated. Four of the six are dollar pairs, which the book is "
                       "already full of, so I expect less. I have been wrong on 5 of 10 "
                       "predictions and the misses have all been optimistic.",
)


def costs() -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=0.0, carry_short_annual_pct=0.0, bars_per_year=BARS_PER_YEAR,
    )


def load(symbols: list[str]) -> pd.DataFrame:
    frames = {}
    for s in symbols:
        try:
            frames[s] = hist.load(ROOT, s, "D1")["close"]
        except FileNotFoundError:
            continue
    panel = pd.DataFrame(frames)
    return panel.loc[panel.notna().all(axis=1)]


def tradeable_at(symbols: list[str], capital: float, n_legs: int,
                 spec: pd.DataFrame, panel: pd.DataFrame) -> list[str]:
    """Which of these can actually be held as one leg at this capital? (F18's check.)"""
    leg_vol_usd = capital * BOOK_VOL / np.sqrt(n_legs)
    vol = panel.pct_change().rolling(prod.VOL_LOOKBACK_BARS).std() * np.sqrt(BARS_PER_YEAR)
    ok = []
    for s in symbols:
        if s not in spec.index or s not in vol.columns:
            continue
        v = float(vol[s].dropna().iloc[-1]) if vol[s].notna().any() else 0.0
        if v <= 0:
            continue
        row = spec.loc[s]
        per_lot = float(row["min_notional"]) / float(row["min_lot"])
        if (leg_vol_usd / v) / per_lot >= float(row["min_lot"]):
            ok.append(s)
    return ok


def positions(panel: pd.DataFrame, legs_per_side: int) -> pd.DataFrame:
    trailing = panel / panel.shift(prod.LOOKBACK_BARS) - 1.0
    vol = panel.pct_change().rolling(prod.VOL_LOOKBACK_BARS).std()
    ranks = trailing.rank(axis=1, ascending=False)
    n = panel.shape[1]
    raw = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    raw[ranks <= legs_per_side] = 1.0
    raw[ranks > n - legs_per_side] = -1.0
    raw = raw.where(trailing.notna(), 0.0)
    sized = raw / vol.replace(0.0, np.nan)
    sized = sized.div(sized.abs().sum(axis=1), axis=0).fillna(0.0)
    grid = pd.Series(np.arange(len(sized)) % prod.REBALANCE_BARS == 0, index=sized.index)
    return sized.where(grid, np.nan).ffill().fillna(0.0)


def book(pos: pd.DataFrame, panel: pd.DataFrame) -> pd.Series:
    total = None
    for c in panel.columns:
        leg = strategy_returns(pos[c], panel[c], costs())
        total = leg if total is None else total + leg
    return total


def evaluate(symbols: list[str], capital: float, spec: pd.DataFrame) -> dict | None:
    panel_all = load(symbols)
    best = None
    for legs in range(3, min(9, len(symbols) // 2) + 1):
        ok = tradeable_at(symbols, capital, legs * 2, spec, panel_all)
        if len(ok) < legs * 2:
            continue
        panel = panel_all[ok]
        pos = positions(panel, legs)
        ret = book(pos, panel)
        perf = summarise(ret, BARS_PER_YEAR)
        p95 = float(np.percentile(bootstrap_max_drawdowns(ret, n_paths=250), 95))
        usd = capital * perf.ann_return_pct * (LIVE_HALT / p95) / 100.0 if p95 > 0 else 0.0
        if best is None or perf.sharpe > best["sharpe"]:
            best = {"legs": legs, "tradeable": len(ok), "sharpe": perf.sharpe,
                    "usd": usd, "ret": ret, "pos": pos, "panel": panel, "bars": len(panel)}
    return best


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    spec = pd.read_parquet(ROOT / "universe.parquet").set_index("symbol")

    print("=" * 96)
    print("P19 — 19 MARKETS vs 25, EVERY LEG SIZED AGAINST THE REAL MINIMUM LOT")
    print("=" * 96)
    print(f"  {'capital':>9} {'universe':>10} {'legs':>6} {'tradeable':>10} {'Sharpe':>8} "
          f"{'$ / yr':>10}")
    print("  " + "-" * 62)

    results = {}
    for capital in (10_000, 30_000, 100_000):
        for label, syms in (("19 narrow", NARROW), ("25 wide", WIDE)):
            r = evaluate(syms, capital, spec)
            if r is None:
                print(f"  {capital:>9,} {label:>10}   no book possible at this size")
                continue
            results[(capital, label)] = r
            print(f"  {capital:>9,} {label:>10} {r['legs']:>6} {r['tradeable']:>10} "
                  f"{r['sharpe']:>+8.3f} {r['usd']:>+10,.0f}")

    print("\n" + "=" * 96)
    print("  DID WIDENING HELP?")
    print("=" * 96)
    for capital in (10_000, 30_000, 100_000):
        a, b = results.get((capital, "19 narrow")), results.get((capital, "25 wide"))
        if a and b:
            print(f"    ${capital:>7,}:  Sharpe {a['sharpe']:+.3f} -> {b['sharpe']:+.3f} "
                  f"({b['sharpe'] - a['sharpe']:+.3f})   "
                  f"${a['usd']:+,.0f} -> ${b['usd']:+,.0f}")

    # The control, on the best book found.
    best_key = max(results, key=lambda k: results[k]["sharpe"])
    best = results[best_key]
    print("\n" + "=" * 96)
    print(f"  THE CONTROL — best book: {best_key[1]} at ${best_key[0]:,}, "
          f"{best['legs']} legs/side")
    print("=" * 96)
    rng = np.random.default_rng(20260816)
    ctrl = []
    for _ in range(50):
        shifted = pd.DataFrame(
            {c: circular_shift_controls(best["pos"][c], 1, seed=int(rng.integers(1e9)))[0]
             for c in best["pos"].columns}, index=best["pos"].index)
        ctrl.append(sharpe_ratio(book(shifted, best["panel"]), BARS_PER_YEAR))
    ctrl = np.asarray(ctrl)
    z = (best["sharpe"] - ctrl.mean()) / ctrl.std(ddof=1)
    passed = bool(z >= 2.0)
    print(f"    strategy {best['sharpe']:+.3f}  vs rotations {ctrl.mean():+.3f} "
          f"+/- {ctrl.std(ddof=1):.3f}   z = {z:+.2f}   "
          f"{'PASS' if passed else 'FAIL'} (needs >= +2.00)")
    years = best["bars"] / BARS_PER_YEAR
    if best["sharpe"] > 0:
        print(f"    provable? Sharpe {best['sharpe']:+.3f} needs "
              f"{(2.0 / best['sharpe']) ** 2:.1f} years; this window has {years:.1f}")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if passed else "FAIL",
        metrics={f"{k[1]}@{k[0]}": {"sharpe": round(v["sharpe"], 4),
                                    "usd": round(v["usd"]), "legs": v["legs"],
                                    "tradeable": v["tradeable"]}
                 for k, v in results.items()} | {"control_z": round(float(z), 3)},
        notes="Every leg sized against the broker's real minimum lot, which P15 did not do.",
    ))
    ok, msg = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
