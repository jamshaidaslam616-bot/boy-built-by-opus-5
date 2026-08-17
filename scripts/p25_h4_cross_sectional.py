"""Cross-sectional momentum on H4 — the one combination never tried.

Two separate things have been tested and neither is this:

  * cross-sectional momentum on DAILY bars (P15, P19) — the shipped strategy
  * time-series momentum on H4 bars (P8) — failed

P7 measured H4 as the only timeframe whose variance ratio exceeds 1.0 and whose
post-bar continuation (+1.079 bp) is larger than a round trip (0.47 bp). That is
where the data pointed, and the effect that was tried there was the wrong one:
time-series asks "is this going up", cross-sectional asks "is this going up more
than the others", and they are different effects with separate evidence.

The cost is the obvious risk. H4 rebalancing trades six times as often as daily,
and this account charges commission wholly on OPEN, so turnover is punished
directly. The test is therefore whether any edge survives paying for it.
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
from goldlab.strategy import production as prod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 6 * 260.0
LEGS = 7
VOL_LB = 120          # ~20 days of H4 bars

HYPOTHESIS = Hypothesis(
    name="P25-h4-cross-sectional",
    family="cross-sectional",
    claim="Cross-sectional momentum measured and rebalanced on H4 bars beats the same effect "
          "on daily bars, net of the extra turnover it costs.",
    economic_rationale="P7 found H4 to be the only timeframe on this data where the variance "
                       "ratio exceeds 1.0 and post-bar continuation exceeds a round trip. P8 "
                       "then tested TIME-SERIES momentum there and it failed — but that is a "
                       "different effect from ranking markets against each other, and the "
                       "cross-sectional version has only ever been run on daily bars. If the "
                       "H4 structure is real, a ranking that refreshes at that frequency should "
                       "capture more of it than one refreshing weekly.",
    pass_criteria={"control_rotation_z": 2.0, "beats_daily_sharpe": 0.625},
    n_param_combinations=6,
    data_scope="25 instruments, H4, shared window, lookbacks 30/120/240 bars, rebalance 6/30",
    predicted_outcome="Gross of costs I expect H4 to look better than daily, because a faster "
                      "ranking tracks a real effect more closely. Net of costs I expect it to "
                      "lose, because rebalancing six times as often against an $11/lot "
                      "open-only commission is a large bill and the daily version already only "
                      "reaches z=+1.43. The interesting outcome would be a gross improvement "
                      "that costs eat — that would say the H4 structure is real but "
                      "unreachable, which is a different answer from 'not there'. Wrong on 5 "
                      "of 15 predictions.",
)


def costs(mult: float = 1.0) -> CostModel:
    return CostModel(spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
                     carry_long_annual_pct=0.0, carry_short_annual_pct=0.0,
                     bars_per_year=BARS_PER_YEAR, multiplier=mult)


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    frames = {}
    for s in prod.UNIVERSE:
        try:
            frames[s] = hist.load(ROOT, s, "H4")["close"]
        except FileNotFoundError:
            continue
    panel = pd.DataFrame(frames)
    panel = panel.loc[panel.notna().all(axis=1)]
    vol = panel.pct_change().rolling(VOL_LB).std()

    print("=" * 96)
    print(f"P25 — CROSS-SECTIONAL ON H4  ({panel.shape[1]} markets, {len(panel):,} bars, "
          f"{panel.index[0]:%Y-%m-%d} .. {panel.index[-1]:%Y-%m-%d})")
    print("=" * 96)
    print(f"  {len(panel) / BARS_PER_YEAR:.1f} years of shared history\n")

    def run(lookback: int, rebal: int, mult: float = 1.0):
        score = panel / panel.shift(lookback) - 1.0
        r = score.rank(axis=1, ascending=False)
        n = panel.shape[1]
        raw = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
        raw[r <= LEGS] = 1.0
        raw[r > n - LEGS] = -1.0
        raw = raw.where(score.notna(), 0.0)
        sized = raw / vol.replace(0.0, np.nan)
        sized = sized.div(sized.abs().sum(axis=1), axis=0).fillna(0.0)
        grid = pd.Series(np.arange(len(sized)) % rebal == 0, index=sized.index)
        pos = sized.where(grid, np.nan).ffill().fillna(0.0)

        total = None
        for c in panel.columns:
            leg = strategy_returns(pos[c], panel[c], costs(mult))
            total = leg if total is None else total + leg
        turn = float(sum(turnover(pos[c]).sum() for c in pos.columns)
                     / (len(pos) / BARS_PER_YEAR))
        return pos, total, turn

    print(f"  {'lookback':>9} {'rebal':>7} {'Sharpe net':>11} {'Sharpe gross':>13} "
          f"{'return':>9} {'turn/yr':>9}")
    print("  " + "-" * 64)

    results = []
    for lookback in (30, 120, 240):          # ~1 week, ~1 month, ~2 months
        for rebal in (6, 30):                # daily, weekly
            pos, net, turn = run(lookback, rebal)
            _, gross, _ = run(lookback, rebal, mult=0.0)
            pn, pg = summarise(net, BARS_PER_YEAR), summarise(gross, BARS_PER_YEAR)
            results.append((lookback, rebal, pn, pg, pos, net, turn))
            print(f"  {lookback:>9} {rebal:>7} {pn.sharpe:>+11.3f} {pg.sharpe:>+13.3f} "
                  f"{pn.ann_return_pct:>+8.2f}% {turn:>9.0f}")

    best = max(results, key=lambda r: r[2].sharpe)
    lookback, rebal, pn, pg, pos, net, turn = best
    print(f"\n  best net: lookback={lookback}, rebalance every {rebal} bars  "
          f"Sharpe {pn.sharpe:+.3f}")
    print(f"  costs take {pg.sharpe:+.3f} gross down to {pn.sharpe:+.3f} net "
          f"({(1 - pn.sharpe / pg.sharpe) * 100:.0f}% of it)" if pg.sharpe > 0 else "")

    print("\n" + "=" * 96)
    print("  CONTROL on the best variant")
    print("=" * 96)
    rng = np.random.default_rng(20260817)
    ctrl = []
    for _ in range(50):
        shifted = pd.DataFrame(
            {c: circular_shift_controls(pos[c], 1, seed=int(rng.integers(1e9)))[0]
             for c in pos.columns}, index=pos.index)
        t = None
        for c in panel.columns:
            leg = strategy_returns(shifted[c], panel[c], costs())
            t = leg if t is None else t + leg
        ctrl.append(sharpe_ratio(t, BARS_PER_YEAR))
    ctrl = np.asarray(ctrl)
    z = (pn.sharpe - ctrl.mean()) / ctrl.std(ddof=1)

    print(f"    strategy {pn.sharpe:+.3f}  vs rotations {ctrl.mean():+.3f} "
          f"+/- {ctrl.std(ddof=1):.3f}   z = {z:+.2f}   "
          f"{'PASS' if z >= 2 else 'FAIL'}")
    print(f"    daily cross-sectional for comparison: Sharpe +0.625, z +1.43")

    if pg.sharpe > 0.625 and pn.sharpe < 0.625:
        print("\n    Note: GROSS beats the daily book while NET does not. That says the H4")
        print("    structure is real but unreachable at this cost base — a different answer")
        print("    from 'there is nothing there', and one worth recording as such.")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if (z >= 2.0 and pn.sharpe > 0.625) else "FAIL",
        metrics={"best_lookback": lookback, "best_rebalance": rebal,
                 "sharpe_net": round(pn.sharpe, 4), "sharpe_gross": round(pg.sharpe, 4),
                 "control_z": round(float(z), 3), "turnover_per_year": round(turn, 1),
                 "daily_benchmark_sharpe": 0.625},
        notes="Cross-sectional at H4. Distinct from P8 (time-series at H4) and P19 "
              "(cross-sectional at D1).",
    ))
    ok, msg = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
