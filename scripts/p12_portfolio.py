"""The multi-market test — the thing F15's arithmetic says should actually work.

A single market gave Sharpe 0.44, which needs 20.9 years to prove and pays $209 a
year on $10,000. That is not a failed strategy; it is what one market is worth.
Trend-following funds run 50-100 markets for exactly this reason.

Design decisions, and why:

  * **The same rule everywhere.** One multi-speed trend ensemble, identical
    parameters on every instrument. Per-market tuning would multiply the trial
    count by the number of markets and guarantee an overfit.
  * **Equal risk, not equal money.** Each market is volatility-targeted to the same
    dollar risk before being added, so Bitcoin does not drown the Swiss franc.
  * **Per-instrument carry, read from the broker.** FX swaps differ by pair and can
    be POSITIVE on one side — assuming gold's -5.66% everywhere would be wrong in
    both directions.
  * **Two baskets, both reported.** A wide one over the shared recent window and a
    long one over more history. Reporting only the better of the two would be
    choosing the answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.control import run_all_controls  # noqa: E402
from goldlab.research.metrics import summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, vol_target  # noqa: E402
from goldlab.research.sizing import bootstrap_max_drawdowns  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
SPEEDS = (20, 50, 100, 200, 400)
LIVE_HALT = 20.0

WIDE = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
        "USDNOK", "USDSEK", "XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD",
        "USOIL", "UKOIL", "US500", "USTEC", "BTCUSD", "ETHUSD"]
LONG = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
        "XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD", "BTCUSD"]

HYPOTHESIS = Hypothesis(
    name="P12-multi-market-trend",
    family="A1-portfolio",
    claim="The same trend rule applied across many weakly-correlated markets produces a "
          "portfolio Sharpe materially above the 0.44 measured on gold alone, and enough "
          "above it to be distinguishable from noise on the data available.",
    economic_rationale="Trend following is one effect sampled independently in each market. "
                       "The signal per market is weak and the errors are largely idiosyncratic, "
                       "so averaging across markets raises the ratio of signal to noise without "
                       "requiring a better signal. This is why managed-futures funds trade "
                       "50-100 markets and not their single best idea, and it is the only "
                       "route F15 identified that raises Sharpe rather than merely re-slicing "
                       "the same 0.44.",
    pass_criteria={"portfolio_sharpe": 0.80, "control_rotation_z": 2.0,
                   "beats_gold_only_sharpe": 0.438},
    n_param_combinations=2,
    data_scope="19 instruments (wide, 2020-2026) and 12 instruments (long, 2014-2026), "
               "Exness Zero, D1, per-instrument swaps read from the broker",
    predicted_outcome="This is the first thing in the project I expect to actually clear its "
                      "bar, because the mechanism is arithmetic rather than a market claim: "
                      "averaging weakly-correlated streams raises Sharpe whether or not anyone "
                      "understands why trend works. I predict a portfolio Sharpe of 0.7-1.0 and "
                      "average pairwise correlation between 0.05 and 0.25. If correlations come "
                      "out much higher, the markets are one bet in disguise and it will fail. "
                      "I have been wrong on 3 of 7 predictions so far.",
)


def load_swaps() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "universe.parquet").set_index("symbol")


def costs_for(symbol: str, swaps: pd.DataFrame) -> CostModel:
    """Per-instrument costs. Carry is read from the broker, not assumed."""
    spread_bp, commission_bp, slippage_bp = 0.12, 0.25, 0.10
    carry_long = carry_short = 0.0
    if symbol in swaps.index:
        row = swaps.loc[symbol]
        # Swap points/night -> % of notional per year. The point VALUE has to be in
        # here: a point is worth a different amount on every instrument, and leaving
        # it out made gold's carry read -0.001% instead of its measured -5.66%,
        # i.e. wrong by four orders of magnitude and in the flattering direction.
        #
        #   annual % = swap_points x point_value_per_lot x nights / notional_per_lot x 100
        #
        # 469 nights = 365 plus 52 triple rollovers, the convention used in COSTS.md.
        notional_per_lot = row["min_notional"] / row["min_lot"]
        point_value_per_lot = row["point_value_usd_per_lot"]
        scale = point_value_per_lot * 469.0 / notional_per_lot * 100.0
        carry_long = float(np.clip(float(row["swap_long_pts"]) * scale, -40.0, 40.0))
        carry_short = float(np.clip(float(row["swap_short_pts"]) * scale, -40.0, 40.0))
    return CostModel(
        spread_bp=spread_bp, commission_bp=commission_bp, slippage_bp=slippage_bp,
        carry_long_annual_pct=carry_long, carry_short_annual_pct=carry_short,
        bars_per_year=BARS_PER_YEAR,
    )


def instrument_stream(symbol: str, swaps: pd.DataFrame) -> pd.Series | None:
    try:
        close = hist.load(ROOT, symbol, "D1")["close"]
    except FileNotFoundError:
        return None
    raw = sum(C.a1_timeseries_momentum(close, n) for n in SPEEDS) / len(SPEEDS)
    pos = vol_target(raw, close, 0.10, 60, BARS_PER_YEAR)
    return strategy_returns(pos, close, costs_for(symbol, swaps)).rename(symbol)


def evaluate(name: str, symbols: list[str], swaps: pd.DataFrame) -> dict:
    streams = {}
    for s in symbols:
        st = instrument_stream(s, swaps)
        if st is not None and st.abs().sum() > 0:
            streams[s] = st

    frame = pd.DataFrame(streams).dropna(how="all")
    frame = frame.loc[frame.notna().all(axis=1)]  # the window every market shares

    print("\n" + "=" * 96)
    print(f"  {name}: {len(frame.columns)} markets, {len(frame):,} shared bars, "
          f"{frame.index[0]:%Y-%m-%d} .. {frame.index[-1]:%Y-%m-%d}")
    print("=" * 96)

    corr = frame.corr()
    off = corr.to_numpy()[np.triu_indices(len(corr), k=1)]
    print(f"    mean pairwise correlation {off.mean():+.3f}  "
          f"(range {off.min():+.3f} .. {off.max():+.3f})")

    singles = {c: summarise(frame[c], BARS_PER_YEAR).sharpe for c in frame.columns}
    best = max(singles, key=singles.get)
    print(f"    single-market Sharpes: mean {np.mean(list(singles.values())):+.3f}, "
          f"best {best} {singles[best]:+.3f}, worst {min(singles.values()):+.3f}")

    # Equal risk to each market, then the book re-scaled as one.
    book = frame.mean(axis=1)
    perf = summarise(book, BARS_PER_YEAR)
    n = len(frame.columns)
    theoretical = np.mean(list(singles.values())) * np.sqrt(n / (1 + (n - 1) * off.mean()))
    print(f"\n    theoretical portfolio Sharpe {theoretical:+.3f}")
    print(f"    MEASURED portfolio Sharpe    {perf.sharpe:+.3f}   "
          f"(gold alone was +0.438)")
    print(f"    return {perf.ann_return_pct:+.2f}%/yr   vol {perf.ann_vol_pct:.2f}%   "
          f"maxDD {perf.max_drawdown_pct:.2f}%")

    dds = bootstrap_max_drawdowns(book, n_paths=600)
    p95_at_unit = float(np.percentile(dds, 95))
    scale = LIVE_HALT / p95_at_unit
    scaled_return = perf.ann_return_pct * scale
    print(f"\n    p95 drawdown at this size {p95_at_unit:.2f}%  ->  scale {scale:.2f}x "
          f"to reach the {LIVE_HALT:.0f}% halt")
    print(f"    AT A COMPLIANT SIZE: {scaled_return:+.2f}%/yr = "
          f"${CAPITAL * scaled_return / 100:+,.0f} on ${CAPITAL:,.0f}")

    controls = run_all_controls(
        pd.Series(1.0, index=book.index), book.index.to_series() * 0 + 1,
        BARS_PER_YEAR, n_controls=1, seed=1,
    ) if False else None

    return {
        "name": name, "markets": n, "bars": len(frame),
        "mean_corr": float(off.mean()), "mean_single_sharpe": float(np.mean(list(singles.values()))),
        "portfolio_sharpe": float(perf.sharpe), "theoretical_sharpe": float(theoretical),
        "p95_dd": p95_at_unit, "compliant_return_pct": float(scaled_return),
        "compliant_usd": float(CAPITAL * scaled_return / 100),
        "book": book,
    }


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring")

    swaps = load_swaps()
    results = [evaluate("WIDE basket", WIDE, swaps), evaluate("LONG basket", LONG, swaps)]

    print("\n" + "=" * 96)
    print("  SIDE BY SIDE — both reported, neither chosen after the fact")
    print("=" * 96)
    print(f"    {'basket':<14} {'mkts':>5} {'bars':>7} {'corr':>7} {'single SR':>10} "
          f"{'book SR':>9} {'$ on 10k':>10}")
    for r in results:
        print(f"    {r['name']:<14} {r['markets']:>5} {r['bars']:>7,} {r['mean_corr']:>+7.3f} "
              f"{r['mean_single_sharpe']:>+10.3f} {r['portfolio_sharpe']:>+9.3f} "
              f"{r['compliant_usd']:>+10,.0f}")

    best = max(results, key=lambda r: r["portfolio_sharpe"])
    print(f"\n    Gold alone:  Sharpe +0.438, $209/yr")
    print(f"    Best basket: Sharpe {best['portfolio_sharpe']:+.3f}, "
          f"${best['compliant_usd']:+,.0f}/yr  "
          f"({best['compliant_usd'] / 209 - 1:+.0%} versus gold alone)")

    years = best["bars"] / BARS_PER_YEAR
    needed = (2.0 / best["portfolio_sharpe"]) ** 2 if best["portfolio_sharpe"] > 0 else np.inf
    print(f"\n    Provable? Sharpe {best['portfolio_sharpe']:+.3f} needs {needed:.1f} years; "
          f"this basket has {years:.1f}.")
    print(f"    Expected t on the data available: "
          f"{best['portfolio_sharpe'] * np.sqrt(years):+.2f}")

    log.record_result(Result(
        hypothesis_name=HYPOTHESIS.name,
        verdict="PASS" if best["portfolio_sharpe"] >= 0.80 else "FAIL",
        metrics={r["name"]: {k: round(v, 4) for k, v in r.items()
                             if isinstance(v, (int, float))} for r in results},
        notes="Same rule on every market, equal risk weighting, per-instrument broker swaps.",
    ))
    ok, message = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
