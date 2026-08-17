"""The two factors this project never tested, and the combination of all three.

An honest gap. Everything so far has been MOMENTUM — twenty hypotheses, four
timeframes, twenty-five markets, all of it one factor. The standard cross-sectional
factor set in managed futures and FX is three:

  * **Momentum** — buy what has risen. Tested to exhaustion.
  * **Carry** — buy what pays you to hold it. NEVER TESTED, and the data has been
    sitting in universe.parquet since P10. The broker's swap rates are the interest
    rate differential made explicit: USDCHF pays to hold long, gold pays to hold
    short. That is the FX carry trade, the most documented anomaly in currencies.
  * **Low volatility** — buy the calm, sell the wild. NEVER TESTED, and the
    volatility panel has been computed on every run since P12.

Both missing factors are classic, both are free, and both are genuinely different
from momentum: carry is a rate differential and low-vol is a risk measure, neither
of which is a price trend.

The reason to expect anything from combining them is not that any one is strong. It
is that three weakly-correlated factors combine better than one strong one — which
is the same arithmetic that made the 25-market book beat gold alone, applied to
factors rather than to instruments.
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
from goldlab.strategy import production as prod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
LEGS = 7
REBAL = 5
VOL_LB = 60

HYPOTHESIS = Hypothesis(
    name="P22-carry-lowvol-multifactor",
    family="cross-sectional",
    claim="Cross-sectional carry and low-volatility each carry information momentum does "
          "not, and a book combining all three beats the momentum-only book.",
    economic_rationale="Carry is compensation for holding a currency or commodity whose "
                       "financing favours you — an interest rate differential, not a price "
                       "pattern, and the most documented anomaly in FX. Low volatility is the "
                       "observation that risk is not rewarded proportionally: calm assets have "
                       "historically returned more per unit of risk than wild ones, across "
                       "equities, bonds and commodities. Neither is a trend, so neither should "
                       "correlate strongly with momentum, and three weakly-correlated factors "
                       "combine better than one — the same arithmetic that made 25 markets beat "
                       "gold alone, applied to factors instead of instruments.",
    pass_criteria={"control_rotation_z": 2.0, "beats_momentum_only": 0.0},
    n_param_combinations=4,
    data_scope="25 instruments, D1, shared window, weekly rebalance, measured swaps",
    predicted_outcome="Carry is the one I would bet on — it is the strongest documented "
                      "cross-sectional effect available here and this broker's swap table "
                      "makes it directly observable. Low-vol I expect to be weak on 25 mostly-FX "
                      "markets, since the anomaly is best evidenced in equities. For the "
                      "combination I expect a modest improvement over momentum alone, perhaps "
                      "0.6-0.9 against the current 0.625, and I do NOT expect it to clear the "
                      "+2.00 control. I have been wrong on 5 of 13 predictions, mostly by "
                      "being optimistic.",
)


def costs() -> CostModel:
    return CostModel(spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
                     carry_long_annual_pct=0.0, carry_short_annual_pct=0.0,
                     bars_per_year=BARS_PER_YEAR)


def ranks_to_book(score: pd.DataFrame) -> pd.DataFrame:
    """Long the top LEGS, short the bottom, equal risk, rebalanced weekly."""
    r = score.rank(axis=1, ascending=False)
    n = score.shape[1]
    raw = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    raw[r <= LEGS] = 1.0
    raw[r > n - LEGS] = -1.0
    return raw.where(score.notna(), 0.0)


def size_and_hold(raw: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    sized = raw / vol.replace(0.0, np.nan)
    sized = sized.div(sized.abs().sum(axis=1), axis=0).fillna(0.0)
    grid = pd.Series(np.arange(len(sized)) % REBAL == 0, index=sized.index)
    return sized.where(grid, np.nan).ffill().fillna(0.0)


def book(pos: pd.DataFrame, panel: pd.DataFrame) -> pd.Series:
    total = None
    for c in panel.columns:
        leg = strategy_returns(pos[c], panel[c], costs())
        total = leg if total is None else total + leg
    return total


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    spec = pd.read_parquet(ROOT / "universe.parquet").set_index("symbol")
    panel = pd.DataFrame({s: hist.load(ROOT, s, "D1")["close"] for s in prod.UNIVERSE})
    panel = panel.loc[panel.notna().all(axis=1)]
    vol = panel.pct_change().rolling(VOL_LB).std()

    print("=" * 94)
    print(f"P22 — CARRY AND LOW-VOL, THE TWO FACTORS NEVER TESTED "
          f"({panel.shape[1]} markets, {len(panel):,} bars)")
    print("=" * 94)

    # --- CARRY, straight from the measured swap table ---
    # swap_long - swap_short is the rate differential: positive means being long is
    # financed better than being short. Constant per instrument, so this is a
    # cross-sectional tilt rather than a timing signal.
    carry = {}
    for s in panel.columns:
        if s not in spec.index:
            continue
        row = spec.loc[s]
        scale = row["point_value_usd_per_lot"] * 469.0 / (row["min_notional"] / row["min_lot"]) * 100
        carry[s] = float(np.clip((row["swap_long_pts"] - row["swap_short_pts"]) * scale, -40, 40))

    print("\n  carry (annual % advantage of being LONG versus SHORT), measured:")
    for s, c in sorted(carry.items(), key=lambda kv: -kv[1])[:6]:
        print(f"    {s:<9} {c:+7.2f}%")
    print("    ...")
    for s, c in sorted(carry.items(), key=lambda kv: -kv[1])[-4:]:
        print(f"    {s:<9} {c:+7.2f}%")

    carry_score = pd.DataFrame(
        {s: pd.Series(carry.get(s, np.nan), index=panel.index) for s in panel.columns}
    )
    momentum_score = panel / panel.shift(prod.LOOKBACK_BARS) - 1.0
    lowvol_score = -(vol * np.sqrt(BARS_PER_YEAR))       # low vol ranks HIGH

    factors = {
        "momentum (tested to death)": momentum_score,
        "CARRY (never tested)": carry_score,
        "LOW-VOL (never tested)": lowvol_score,
    }

    print("\n" + "=" * 94)
    print(f"  {'factor':<30} {'Sharpe':>8} {'return':>9} {'maxDD':>8} {'ctrl z':>8}")
    print("  " + "-" * 70)

    streams, results = {}, {}
    rng = np.random.default_rng(20260817)
    for name, score in factors.items():
        pos = size_and_hold(ranks_to_book(score), vol)
        rets = book(pos, panel)
        perf = summarise(rets, BARS_PER_YEAR)
        ctrl = [sharpe_ratio(book(pd.DataFrame(
            {c: circular_shift_controls(pos[c], 1, seed=int(rng.integers(1e9)))[0]
             for c in pos.columns}, index=pos.index), panel), BARS_PER_YEAR)
            for _ in range(40)]
        z = (perf.sharpe - np.mean(ctrl)) / np.std(ctrl, ddof=1)
        streams[name], results[name] = rets, (perf, z)
        print(f"  {name:<30} {perf.sharpe:>+8.3f} {perf.ann_return_pct:>+8.2f}% "
              f"{perf.max_drawdown_pct:>7.2f}% {z:>+8.2f}")

    # --- how different are they, really? ---
    corr = pd.DataFrame(streams).corr()
    off = corr.to_numpy()[np.triu_indices(len(corr), k=1)]
    print(f"\n  mean pairwise correlation between factor returns: {off.mean():+.3f}")
    print("  (low is what makes combining them worth anything)")

    # --- the combination: average the RANKS, not the returns ---
    zs = {n: s.rank(axis=1, pct=True) - 0.5 for n, s in factors.items()}
    combined = sum(zs.values()) / len(zs)
    pos = size_and_hold(ranks_to_book(combined), vol)
    rets = book(pos, panel)
    perf = summarise(rets, BARS_PER_YEAR)
    ctrl = [sharpe_ratio(book(pd.DataFrame(
        {c: circular_shift_controls(pos[c], 1, seed=int(rng.integers(1e9)))[0]
         for c in pos.columns}, index=pos.index), panel), BARS_PER_YEAR) for _ in range(60)]
    z = (perf.sharpe - np.mean(ctrl)) / np.std(ctrl, ddof=1)

    print("\n" + "=" * 94)
    print("  ALL THREE COMBINED")
    print("=" * 94)
    print(f"    Sharpe {perf.sharpe:+.3f}   return {perf.ann_return_pct:+.2f}%   "
          f"maxDD {perf.max_drawdown_pct:.2f}%")
    print(f"    control  strategy {perf.sharpe:+.3f} vs rotations {np.mean(ctrl):+.3f} "
          f"+/- {np.std(ctrl, ddof=1):.3f}   z = {z:+.2f}   "
          f"{'PASS' if z >= 2 else 'FAIL'}")
    mom = results["momentum (tested to death)"][0].sharpe
    print(f"    versus momentum alone: {mom:+.3f} -> {perf.sharpe:+.3f} "
          f"({(perf.sharpe / mom - 1) * 100:+.1f}%)" if mom else "")
    if perf.sharpe > 0:
        print(f"    years to prove {(2.0 / perf.sharpe) ** 2:.1f} "
              f"(this window has {len(rets) / BARS_PER_YEAR:.1f})")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if z >= 2.0 else "FAIL",
        metrics={n: {"sharpe": round(p.sharpe, 4), "z": round(float(zz), 3)}
                 for n, (p, zz) in results.items()}
        | {"combined": {"sharpe": round(perf.sharpe, 4), "z": round(float(z), 3)},
           "factor_correlation": round(float(off.mean()), 3)},
        notes="Carry read from measured swap differentials; low-vol from the volatility panel.",
    ))
    ok, msg = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
