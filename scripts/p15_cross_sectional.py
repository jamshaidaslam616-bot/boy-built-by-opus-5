"""Cross-sectional momentum — a different effect, and the one this project never tested.

Everything so far has been TIME-SERIES momentum: "is this market going up?" Applied
to gold, to 19 markets, at four timeframes, in both directions. It fails.

Cross-sectional momentum asks a different question: "is this market going up MORE
than the others?" It is a separate documented anomaly with its own literature, and
it was impossible to test until P11 built a 19-market universe. Three reasons it is
worth the effort here rather than being one more variation:

  * **It is market-neutral by construction.** Long the strongest, short the weakest,
    in equal risk. That strips out the common factor — the dollar, or global risk
    appetite — which is most of what makes 19 markets correlate at 0.17.
  * **It fits the cost structure.** A weekly rebalance sits inside the 7-day free
    window the owner confirmed with Exness, so financing is genuinely zero rather
    than merely reduced.
  * **The short side is free here.** This broker charges the long side on most
    instruments; a balanced book is short as often as it is long.

If this fails too, then every free idea has been tested and the remaining lever is
new data, not new rules.
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
from goldlab.research.returns import CostModel, strategy_returns, turnover  # noqa: E402
from goldlab.research.sizing import bootstrap_max_drawdowns  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
LIVE_HALT = 20.0
REBALANCE_DAYS = 5      # weekly, inside the confirmed 7-day free window
VOL_LOOKBACK = 60

SYMS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
        "USDNOK", "USDSEK", "XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD",
        "USOIL", "UKOIL", "US500", "USTEC", "BTCUSD", "ETHUSD"]

HYPOTHESIS = Hypothesis(
    name="P15-cross-sectional-momentum",
    family="cross-sectional",
    claim="Ranking markets by trailing return and holding the strongest against the weakest, "
          "in equal risk, produces a positive return that time-series momentum on the same "
          "markets does not.",
    economic_rationale="Cross-sectional and time-series momentum are distinct effects with "
                       "separate evidence. The cross-sectional version is close to market "
                       "neutral, which removes the common factor driving the 0.17 average "
                       "correlation measured in P12 — and that common factor is most of what "
                       "a diversified time-series book was actually exposed to. It also "
                       "rebalances weekly, which sits inside the 7-day financing-free window "
                       "the owner confirmed with the broker, so carry is zero rather than "
                       "merely smaller.",
    pass_criteria={"control_rotation_z": 2.0, "portfolio_sharpe": 0.50, "positive_usd": 0.0},
    n_param_combinations=9,
    data_scope="19 instruments, D1, shared window, weekly rebalance, zero financing",
    predicted_outcome="Genuinely uncertain, which is why it is worth running. The mechanism is "
                      "real and documented, and it is the first idea here that is not a "
                      "restatement of trend. Against that, 19 markets is a small cross-section "
                      "— the published evidence uses dozens to hundreds — and a small "
                      "cross-section makes the ranking noisy. I would put it at roughly even "
                      "odds of beating zero and clearly below even odds of clearing the "
                      "control. I have been wrong on 4 of 9 predictions, mostly optimistic.",
)


def costs() -> CostModel:
    """Zero financing: the weekly rebalance never exceeds the 7-day free window."""
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=0.0, carry_short_annual_pct=0.0, bars_per_year=BARS_PER_YEAR,
    )


def load_panel() -> pd.DataFrame:
    frames = {}
    for s in SYMS:
        try:
            frames[s] = hist.load(ROOT, s, "D1")["close"]
        except FileNotFoundError:
            continue
    panel = pd.DataFrame(frames)
    return panel.loc[panel.notna().all(axis=1)]


def cross_sectional_positions(panel: pd.DataFrame, lookback: int, n_side: int) -> pd.DataFrame:
    """Long the top ``n_side`` performers, short the bottom, rebalanced weekly.

    Ranks are computed on trailing return through bar t and held from t+1 — the
    framework applies the lag, so nothing here peeks. Positions are volatility-
    scaled per market so a Bitcoin leg and a franc leg carry the same risk.
    """
    trailing = panel / panel.shift(lookback) - 1.0
    vol = panel.pct_change().rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).std()

    ranks = trailing.rank(axis=1, ascending=False)
    n = panel.shape[1]
    raw = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    raw[ranks <= n_side] = 1.0
    raw[ranks > n - n_side] = -1.0
    raw = raw.where(trailing.notna(), 0.0)

    # Equal risk per leg, then rebalance only on the weekly grid.
    sized = raw / vol.replace(0.0, np.nan)
    sized = sized.div(sized.abs().sum(axis=1), axis=0).fillna(0.0)

    grid = np.arange(len(sized)) % REBALANCE_DAYS == 0
    held = sized.where(pd.Series(grid, index=sized.index), np.nan).ffill().fillna(0.0)
    return held


def book_returns(positions: pd.DataFrame, panel: pd.DataFrame) -> pd.Series:
    total = None
    for col in panel.columns:
        leg = strategy_returns(positions[col], panel[col], costs())
        total = leg if total is None else total + leg
    return total


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    panel = load_panel()
    print("=" * 100)
    print(f"P15 — CROSS-SECTIONAL MOMENTUM  ({panel.shape[1]} markets, {len(panel):,} shared "
          f"bars, {panel.index[0]:%Y-%m-%d} .. {panel.index[-1]:%Y-%m-%d})")
    print("=" * 100)
    print(f"  weekly rebalance ({REBALANCE_DAYS} bars), financing ZERO — inside the "
          f"broker-confirmed 7-day free window")

    print(f"\n  {'lookback':>9} {'legs/side':>10} {'Sharpe':>8} {'return':>9} {'maxDD':>8} "
          f"{'turn/yr':>9} {'$ on 10k':>10}")
    print("  " + "-" * 76)

    results = []
    for lookback in (20, 60, 120):
        for n_side in (3, 5, 7):
            pos = cross_sectional_positions(panel, lookback, n_side)
            ret = book_returns(pos, panel)
            perf = summarise(ret, BARS_PER_YEAR)
            turn = float(sum(turnover(pos[c]).sum() for c in pos.columns)
                         / (len(pos) / BARS_PER_YEAR))
            p95 = float(np.percentile(bootstrap_max_drawdowns(ret, n_paths=300), 95))
            usd = CAPITAL * perf.ann_return_pct * (LIVE_HALT / p95) / 100.0 if p95 > 0 else 0.0
            results.append({"lookback": lookback, "n_side": n_side, "sharpe": perf.sharpe,
                            "usd": usd, "pos": pos, "ret": ret})
            print(f"  {lookback:>9} {n_side:>10} {perf.sharpe:>+8.3f} "
                  f"{perf.ann_return_pct:>+8.2f}% {perf.max_drawdown_pct:>7.2f}% "
                  f"{turn:>9.0f} {usd:>+10,.0f}")

    best = max(results, key=lambda r: r["sharpe"])
    print(f"\n  Best: lookback={best['lookback']}, {best['n_side']} per side  "
          f"Sharpe {best['sharpe']:+.3f}, ${best['usd']:+,.0f}/yr")

    # The control: rotate each market's position column, rebuild the book.
    print("\n" + "=" * 100)
    print("  THE CONTROL — rotate the positions, keep everything else")
    print("=" * 100)
    rng = np.random.default_rng(20260814)
    ctrl = []
    for _ in range(60):
        shifted = pd.DataFrame(
            {c: circular_shift_controls(best["pos"][c], 1, seed=int(rng.integers(1e9)))[0]
             for c in best["pos"].columns},
            index=best["pos"].index,
        )
        ctrl.append(sharpe_ratio(book_returns(shifted, panel), BARS_PER_YEAR))
    ctrl = np.asarray(ctrl)
    z = (best["sharpe"] - ctrl.mean()) / ctrl.std(ddof=1)
    passed = z >= 2.0
    print(f"    strategy {best['sharpe']:+.3f}  vs rotations {ctrl.mean():+.3f} "
          f"+/- {ctrl.std(ddof=1):.3f}   z = {z:+.2f}   "
          f"{'PASS' if passed else 'FAIL'} (needs >= +2.00)")

    years = len(panel) / BARS_PER_YEAR
    if best["sharpe"] > 0:
        print(f"    provable? Sharpe {best['sharpe']:+.3f} needs "
              f"{(2.0 / best['sharpe']) ** 2:.1f} years, this window has {years:.1f}")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if (passed and best["sharpe"] >= 0.50) else "FAIL",
        metrics={"best_lookback": best["lookback"], "best_legs_per_side": best["n_side"],
                 "sharpe": round(best["sharpe"], 4), "usd_on_10k": round(best["usd"]),
                 "control_z": round(float(z), 3), "markets": panel.shape[1]},
        notes="Financing zero throughout: weekly rebalance sits inside the broker-confirmed "
              "7-day free window.",
    ))
    ok, msg = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
