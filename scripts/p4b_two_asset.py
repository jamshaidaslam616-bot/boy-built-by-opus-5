"""Does adding silver to the same trend system buy real diversification?

The arithmetic that governs this whole project: return at a fixed drawdown limit is
roughly proportional to Sharpe. P3 and P4 established that gold trend-following
tops out near Sharpe 0.5, which at a 10% drawdown limit pays about $150/yr on
$10,000. Raising that means raising Sharpe, and there are only two honest ways:
new information, or more genuinely uncorrelated bets.

P4 tried the second inside gold alone — five speeds, mean correlation 0.484,
Calmar +11.5%. This tries it across a second asset. Silver is the obvious
candidate: already cached, same broker, same code path, and it carries an
industrial demand component gold does not, so its trend should not be gold's trend.

**Scope note.** The brief was a gold bot. Adding silver is a change of scope, so
this measures the option and reports it rather than adopting it. Whether the
mandate widens is the owner's call.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.metrics import summarise  # noqa: E402
from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, vol_target  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
LOG = Path(__file__).resolve().parents[1] / "reports" / "prereg.jsonl"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
SPEEDS = (20, 50, 100, 200, 400)

# Silver's financing, MEASURED 2026-08-08: -39.00/lot/night on 317,785 notional.
CARRY = {"XAUUSD": -5.66, "XAGUSD": -5.76}

HYPOTHESIS = Hypothesis(
    name="P4b-gold-plus-silver-trend",
    family="A1-portfolio",
    claim="Running the same multi-speed trend system on silver as well as gold raises "
          "return per unit of drawdown, because the two metals' trends are imperfectly "
          "correlated.",
    economic_rationale="Gold and silver share macro drivers (real yields, the dollar, risk "
                       "appetite) but silver carries a large industrial demand component gold "
                       "does not, and trades with roughly twice the volatility. Their trends "
                       "should therefore diverge often enough to diversify, without requiring "
                       "any new signal or new data.",
    pass_criteria={"calmar_improvement_pct": 15.0, "correlation_below": 0.70},
    n_param_combinations=2,
    data_scope="XAUUSD and XAGUSD D1, 2014-01-14..2026-08-07, speeds 20/50/100/200/400",
    predicted_outcome="I expect the two return streams to correlate around 0.55-0.75 — lower "
                      "than gold's own speeds correlate with each other, but not low enough to "
                      "transform the result. My guess is a Calmar improvement in the 10-25% "
                      "range, which would take the compliant return from about $151 to under "
                      "$200. Useful, not decisive. I was wrong about correlations in P4 "
                      "(guessed 0.6-0.85, measured 0.484), so this guess may also be high.",
)


def costs(symbol: str) -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=CARRY[symbol], carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR,
    )


def ensemble(close: pd.Series, long_only: bool) -> pd.Series:
    raw = sum(C.a1_timeseries_momentum(close, n) for n in SPEEDS) / len(SPEEDS)
    return raw.clip(lower=0.0) if long_only else raw


def compliant(returns_fn, label: str) -> tuple[float, float, float] | None:
    for target in (0.10, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02):
        net = returns_fn(target)
        perf = summarise(net, BARS_PER_YEAR)
        if perf.max_drawdown_pct <= 10.0:
            return target, perf.ann_return_pct, perf.max_drawdown_pct
    return None


def main() -> int:
    log = PreRegistrationLog(LOG)
    if not log.is_registered(HYPOTHESIS.name):
        log.register(HYPOTHESIS)
        print(f"registered {HYPOTHESIS.name} before any scoring\n")

    gold = hist.load(ROOT, "XAUUSD", "D1")["close"]
    silver = hist.load(ROOT, "XAGUSD", "D1")["close"].reindex(gold.index).ffill().dropna()
    gold = gold.reindex(silver.index)

    print("=" * 94)
    print("P4b — DOES SILVER DIVERSIFY THE GOLD TREND SYSTEM?")
    print("=" * 94)
    print(f"  {len(gold):,} shared bars, {gold.index[0]:%Y-%m-%d} .. {gold.index[-1]:%Y-%m-%d}")
    g_vol = gold.pct_change().std() * np.sqrt(BARS_PER_YEAR)
    s_vol = silver.pct_change().std() * np.sqrt(BARS_PER_YEAR)
    print(f"  gold annual vol {g_vol:.1%}   silver annual vol {s_vol:.1%}   "
          f"price correlation {gold.pct_change().corr(silver.pct_change()):.3f}")

    for long_only in (True, False):
        shape = "long-only" if long_only else "long/short"
        print("\n" + "-" * 94)
        print(f"  {shape.upper()} multi-speed trend on each metal")
        print("-" * 94)

        legs = {}
        for symbol, px in (("XAUUSD", gold), ("XAGUSD", silver)):
            pos = vol_target(ensemble(px, long_only), px, 0.10, 60, BARS_PER_YEAR)
            legs[symbol] = strategy_returns(pos, px, costs(symbol))
            perf = summarise(legs[symbol], BARS_PER_YEAR)
            print(f"    {symbol}  Sharpe {perf.sharpe:+.3f}  return {perf.ann_return_pct:+6.2f}%  "
                  f"maxDD {perf.max_drawdown_pct:5.2f}%")

        stream_corr = legs["XAUUSD"].corr(legs["XAGUSD"])
        print(f"\n    RETURN-STREAM correlation: {stream_corr:.3f}  "
              f"(the number that decides whether this helps)")

        n = 2
        multiplier = np.sqrt(n / (1 + (n - 1) * stream_corr))
        best_leg = max(summarise(s, BARS_PER_YEAR).sharpe for s in legs.values())
        print(f"    theoretical Sharpe multiplier {multiplier:.3f}x -> ceiling "
              f"{best_leg * multiplier:+.3f} from best leg {best_leg:+.3f}")

        # Equal risk to each metal, then the pair re-targeted as one book.
        def combined(target: float) -> pd.Series:
            parts = []
            for symbol, px in (("XAUUSD", gold), ("XAGUSD", silver)):
                pos = vol_target(ensemble(px, long_only), px, target / np.sqrt(2), 60, BARS_PER_YEAR)
                parts.append(strategy_returns(pos, px, costs(symbol)))
            return sum(parts)

        pair = summarise(combined(0.10), BARS_PER_YEAR)
        gold_only = summarise(legs["XAUUSD"], BARS_PER_YEAR)
        print(f"\n    {'book':<18} {'Sharpe':>8} {'return':>9} {'maxDD':>8} {'Calmar':>8}")
        for label, perf in (("gold only", gold_only), ("gold + silver", pair)):
            calmar = perf.ann_return_pct / perf.max_drawdown_pct if perf.max_drawdown_pct else 0
            print(f"    {label:<18} {perf.sharpe:>+8.3f} {perf.ann_return_pct:>+8.2f}% "
                  f"{perf.max_drawdown_pct:>7.2f}% {calmar:>8.3f}")

        c_gold = gold_only.ann_return_pct / gold_only.max_drawdown_pct
        c_pair = pair.ann_return_pct / pair.max_drawdown_pct
        print(f"    Calmar change: {(c_pair / c_gold - 1) * 100:+.1f}%")

        print("\n    At a size that respects the 10% live drawdown limit:")
        only = compliant(lambda t: strategy_returns(
            vol_target(ensemble(gold, long_only), gold, t, 60, BARS_PER_YEAR), gold, costs("XAUUSD")
        ), "gold")
        both = compliant(combined, "pair")
        for label, res in (("gold only", only), ("gold + silver", both)):
            if res:
                target, ret, dd = res
                print(f"      {label:<16} {target:.0%} vol -> {ret:+.2f}%/yr = "
                      f"${CAPITAL * ret / 100:+,.0f} on ${CAPITAL:,.0f}  (maxDD {dd:.2f}%)")
            else:
                print(f"      {label:<16} no tested size respects the limit")

        if long_only:
            log.record_result(Result(
                hypothesis_name=HYPOTHESIS.name,
                verdict="PASS" if (c_pair / c_gold - 1) * 100 >= 15.0 and stream_corr < 0.70
                        else "FAIL",
                metrics={
                    "shape": shape,
                    "return_stream_correlation": round(float(stream_corr), 3),
                    "calmar_gold_only": round(c_gold, 4),
                    "calmar_pair": round(c_pair, 4),
                    "calmar_improvement_pct": round((c_pair / c_gold - 1) * 100, 1),
                    "compliant_gold_only_usd": round(CAPITAL * only[1] / 100) if only else None,
                    "compliant_pair_usd": round(CAPITAL * both[1] / 100) if both else None,
                },
                notes="Scope change: adding silver widens the brief beyond a gold bot. "
                      "Measured and reported; adoption is the owner's decision.",
            ))

    ok, message = log.verify()
    print(f"\n  pre-registration chain: {'INTACT' if ok else 'BROKEN'} — {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
