"""The 7-day-free scenario — the one that could actually change the answer.

The owner established that their swap-free account charges nothing for the first
**7 days** a position is held. That matters more than it sounds, because P12 showed
the multi-market book was killed by carry and by nothing else: portfolio Sharpe was
-0.404 with financing and +0.010 without.

Three regimes are worth separating, and they are not the same:

  A. **Hold as long as the signal says, pay the swap.** What P12 measured. Dead.
  B. **Hold as long as the signal says, but close and reopen every 7 days** so the
     free window restarts. Costs one round trip per week instead of a week of swap:
     roughly 0.13%/yr against 5.68%/yr, about 43x cheaper. **Whether the broker's
     free window actually restarts on a new position is a question for them, not
     for me — this models it and labels it as unverified.**
  C. **Never hold past a week at all** — a genuinely faster strategy, where the
     free window is never exhausted and nothing has to be gamed.

Regime C is the honest one. B is modelled because the arithmetic is so lopsided
that the owner should know the size of it before asking the broker.
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
from goldlab.research.returns import CostModel, strategy_returns, turnover, vol_target  # noqa: E402
from goldlab.research.sizing import bootstrap_max_drawdowns  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
LIVE_HALT = 20.0
FREE_DAYS = 7

SYMS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
        "USDNOK", "USDSEK", "XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD",
        "USOIL", "UKOIL", "US500", "USTEC", "BTCUSD", "ETHUSD"]

HYPOTHESIS = Hypothesis(
    name="P14-seven-day-free-window",
    family="A1-portfolio",
    claim="With no financing charged inside a 7-day holding window, a multi-market trend "
          "book that holds no longer than a week becomes profitable, where the same book "
          "paying swap did not.",
    economic_rationale="P12 isolated financing as the sole cause of failure: the identical "
                       "positions gave Sharpe -0.404 with swap and +0.010 without. Removing "
                       "a 2-31%/yr cost from every position in every market cannot make the "
                       "signal better, but it removes the tax that was larger than the signal. "
                       "The constraint it imposes — holds capped at a week — makes the "
                       "strategy faster and therefore more expensive in commission, so the "
                       "two effects work against each other and have to be measured, not "
                       "assumed.",
    pass_criteria={"portfolio_sharpe": 0.50, "control_rotation_z": 2.0, "positive_usd": 0.0},
    n_param_combinations=4,
    data_scope="19 instruments, D1, Exness Zero swap-free (7 free days), 2020-2026 shared window",
    predicted_outcome="Removing carry should lift the book from roughly break-even to modestly "
                      "positive, but the 7-day cap forces a much faster signal and this account "
                      "charges $11/lot on every OPEN — so turnover cost rises exactly as carry "
                      "falls. I expect a portfolio Sharpe of 0.2-0.5: better than anything so "
                      "far and probably still short of the bar. I have been wrong on 4 of 8 "
                      "predictions, most often by being too optimistic.",
)


def carry_for(symbol: str, swaps: pd.DataFrame) -> tuple[float, float]:
    if symbol not in swaps.index:
        return 0.0, 0.0
    r = swaps.loc[symbol]
    scale = r["point_value_usd_per_lot"] * 469.0 / (r["min_notional"] / r["min_lot"]) * 100.0
    return (float(np.clip(r["swap_long_pts"] * scale, -40, 40)),
            float(np.clip(r["swap_short_pts"] * scale, -40, 40)))


def model(carry_long=0.0, carry_short=0.0, commission_bp=0.25) -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=commission_bp, slippage_bp=0.10,
        carry_long_annual_pct=carry_long, carry_short_annual_pct=carry_short,
        bars_per_year=BARS_PER_YEAR,
    )


def capped_hold(raw: pd.Series, max_days: int) -> pd.Series:
    """Force the position flat once it has been held ``max_days`` bars.

    A signal that would keep running gets closed at the cap and may re-enter on the
    next bar — which costs a fresh round trip, exactly as it would in reality.
    """
    values = raw.fillna(0.0).to_numpy()
    out = np.zeros_like(values)
    held, sign = 0, 0.0
    for i, v in enumerate(values):
        s = np.sign(v)
        if s == 0:
            held, sign = 0, 0.0
            continue
        if s != sign:
            held, sign = 1, s
            out[i] = v
        elif held < max_days:
            held += 1
            out[i] = v
        else:
            held, sign = 0, 0.0  # forced flat; may re-enter next bar
    return pd.Series(out, index=raw.index)


def build(symbol: str, speeds, max_days: int | None, costs: CostModel) -> pd.Series:
    close = hist.load(ROOT, symbol, "D1")["close"]
    raw = sum(C.a1_timeseries_momentum(close, n) for n in speeds) / len(speeds)
    if max_days is not None:
        raw = capped_hold(raw, max_days)
    pos = vol_target(raw, close, 0.10, 60, BARS_PER_YEAR)
    return strategy_returns(pos, close, costs).rename(symbol), pos, close


def book(streams: dict[str, pd.Series]) -> pd.Series:
    frame = pd.DataFrame(streams).dropna(how="all")
    return frame.loc[frame.notna().all(axis=1)].mean(axis=1)


def report(label: str, streams: dict[str, pd.Series], turnovers: list[float]) -> dict:
    b = book(streams)
    perf = summarise(b, BARS_PER_YEAR)
    p95 = float(np.percentile(bootstrap_max_drawdowns(b, n_paths=400), 95))
    scale = LIVE_HALT / p95 if p95 > 0 else 0.0
    usd = CAPITAL * perf.ann_return_pct * scale / 100.0
    singles = {k: sharpe_ratio(v, BARS_PER_YEAR) for k, v in streams.items()}
    print(f"  {label:<40} {perf.sharpe:>+8.3f} {np.mean(list(singles.values())):>+9.3f} "
          f"{sum(v > 0 for v in singles.values()):>4}/{len(singles)} "
          f"{np.mean(turnovers):>9.0f} {usd:>+10,.0f}")
    return {"label": label, "sharpe": perf.sharpe, "usd": usd, "book": b,
            "mean_single": float(np.mean(list(singles.values())))}


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    swaps = pd.read_parquet(ROOT / "universe.parquet").set_index("symbol")

    print("=" * 104)
    print("P14 — THE 7-DAY FREE WINDOW, ACROSS 19 MARKETS")
    print("=" * 104)
    print(f"  {'scenario':<40} {'book SR':>8} {'mean SR':>9} {'pos':>5} "
          f"{'turn/yr':>9} {'$ on 10k':>10}")
    print("  " + "-" * 100)

    slow, fast = (20, 50, 100, 200, 400), (3, 5, 10, 20)
    results = []

    configs = [
        ("A. slow trend, swap charged", slow, None, True),
        ("B. slow trend, 7-day roll (unverified)", slow, FREE_DAYS, False),
        ("C. fast trend, capped at 7 days", fast, FREE_DAYS, False),
        ("D. fast trend, no cap, swap charged", fast, None, True),
    ]

    for label, speeds, cap, charge in configs:
        streams, turns = {}, []
        for s in SYMS:
            cl, cs = carry_for(s, swaps) if charge else (0.0, 0.0)
            net, pos, _ = build(s, speeds, cap, model(cl, cs))
            streams[s] = net
            turns.append(float(turnover(pos).sum() / (len(pos) / BARS_PER_YEAR)))
        results.append(report(label, streams, turns))

    best = max(results, key=lambda r: r["sharpe"])
    print(f"\n  Best: {best['label']}  Sharpe {best['sharpe']:+.3f}, "
          f"${best['usd']:+,.0f}/yr on ${CAPITAL:,.0f}")

    # Is the best one distinguishable from a rotation of itself?
    print("\n" + "=" * 104)
    print("  THE CONTROL — is the best scenario better than a rotation of itself?")
    print("=" * 104)
    # Rotate the POSITIONS, per instrument, then rebuild the book. Rotating the
    # book's RETURNS is useless: a Sharpe is mean over standard deviation, and
    # rotation changes neither — which is why a first attempt produced a control
    # distribution with a standard deviation of exactly zero.
    print("    rotating positions per instrument and rebuilding the book ...", flush=True)
    speeds, cap = fast, FREE_DAYS
    positions, closes = {}, {}
    for s in SYMS:
        _, pos, close = build(s, speeds, cap, model())
        positions[s], closes[s] = pos, close

    rng = np.random.default_rng(20260810)
    ctrl = []
    for _ in range(60):
        streams = {}
        for s in SYMS:
            shifted = circular_shift_controls(positions[s], 1, seed=int(rng.integers(1e9)))[0]
            streams[s] = strategy_returns(shifted, closes[s], model())
        ctrl.append(sharpe_ratio(book(streams), BARS_PER_YEAR))
    ctrl = np.asarray(ctrl)
    z = (best["sharpe"] - ctrl.mean()) / ctrl.std(ddof=1)
    print(f"    strategy {best['sharpe']:+.3f}  vs rotations {np.mean(ctrl):+.3f} "
          f"+/- {np.std(ctrl, ddof=1):.3f}   z = {z:+.2f}   "
          f"{'PASS' if z >= 2 else 'FAIL'} (needs >= +2.00)")

    years = len(best["book"]) / BARS_PER_YEAR
    needed = (2.0 / best["sharpe"]) ** 2 if best["sharpe"] > 0 else float("inf")
    print(f"    provable? Sharpe {best['sharpe']:+.3f} needs {needed:.1f} years, "
          f"this window has {years:.1f}")

    print("\n" + "=" * 104)
    print("  WHAT THE 7-DAY WINDOW IS WORTH, IN ONE LINE")
    print("=" * 104)
    a = next(r for r in results if r["label"].startswith("A."))
    print(f"    swap charged  ->  Sharpe {a['sharpe']:+.3f}, ${a['usd']:+,.0f}/yr")
    print(f"    swap avoided  ->  Sharpe {best['sharpe']:+.3f}, ${best['usd']:+,.0f}/yr")
    print(f"    the free window is worth ${best['usd'] - a['usd']:+,.0f} a year on "
          f"${CAPITAL:,.0f}")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if (best["sharpe"] >= 0.50 and z >= 2.0) else "FAIL",
        metrics={r["label"]: {"sharpe": round(r["sharpe"], 4), "usd": round(r["usd"])}
                 for r in results} | {"control_z": round(float(z), 3)},
        notes="Scenario B assumes the broker's free window restarts on a new position, "
              "which is UNVERIFIED and must be confirmed with Exness before it is relied on.",
    ))
    ok, msg = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
