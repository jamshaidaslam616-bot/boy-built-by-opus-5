"""Demonstrate that the lab can tell a real edge from luck — before trusting it.

Runs the identical pipeline over two synthetic worlds:

  * a series with a KNOWN edge deliberately planted in it
  * a pure random walk with no structure at all

Same strategy code, same costs, same controls, same thresholds. The only
difference is the world. If the verdicts do not come out opposite, nothing this
project measures afterwards is worth reading.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.research.gauntlet import run_gauntlet  # noqa: E402
from goldlab.research.metrics import annualised_to_per_bar_sharpe_variance  # noqa: E402
from goldlab.research.returns import CostModel, vol_target  # noqa: E402
from goldlab.research.splits import purged_walk_forward  # noqa: E402

BARS_PER_YEAR = 252.0
N_BARS = 5000
SEED = 20260808


def index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2012-01-02", periods=n, freq="B", tz="UTC")


def random_walk(n: int, seed: int, sigma: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0, sigma, n))), index=index(n))


def planted_momentum(n: int, seed: int, strength: float = 0.20, sigma: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, sigma, n)
    r = np.zeros(n)
    r[0] = noise[0]
    for t in range(1, n):
        r[t] = strength * sigma * np.sign(r[t - 1]) + noise[t]
    return pd.Series(100.0 * np.exp(np.cumsum(r)), index=index(n))


def momentum_position(close: pd.Series) -> pd.Series:
    """Decided at bar t's close; the framework applies the one-bar lag."""
    return np.sign(close.pct_change()).fillna(0.0)


def gold_like_costs() -> CostModel:
    """Costs in the shape COSTS.md measured on the live account.

    Spread is the one figure still unmeasured (the market was closed), so the
    conservative placeholder from the previous project is used and labelled as
    such. Nothing here is presented as a measurement.
    """
    return CostModel(
        spread_bp=0.12,             # ~50 points on $434k notional; PROVISIONAL
        commission_bp=0.25,         # $11.00/lot round turn; owner-supplied, unverified
        slippage_bp=0.10,           # assumption, no tick data yet
        carry_long_annual_pct=-5.66,   # MEASURED 2026-08-08
        carry_short_annual_pct=0.0,    # MEASURED 2026-08-08
        bars_per_year=BARS_PER_YEAR,
    )


def evaluate(world: str, close: pd.Series) -> tuple[bool, bool]:
    """Returns (full_gauntlet_passed, edge_was_detected).

    The two are reported separately on purpose. The control and deflation tests ask
    *is there an edge*; the drawdown and cost gates ask *is this sized and priced to
    be worth trading*. A strategy can have a genuine edge and still be too
    aggressive — that is a sizing verdict, not evidence about the signal.
    """
    raw = momentum_position(close)

    # Volatility targeting is mandatory for every candidate, so that nothing wins
    # the bake-off merely by having been sized more aggressively than its rivals.
    # Omitting it here is what made the planted edge fail on drawdown alone.
    pos = vol_target(
        raw,
        close,
        target_annual_vol=0.10,
        lookback=60,
        bars_per_year=BARS_PER_YEAR,
    )

    folds = purged_walk_forward(
        close.index, n_folds=4, lookback_bars=1, holding_bars=5, min_train_bars=1000
    )
    out = run_gauntlet(
        name=world,
        position=pos,
        close=close,
        costs=gold_like_costs(),
        bars_per_year=BARS_PER_YEAR,
        n_trials=50,
        sharpe_variance_across_trials=annualised_to_per_bar_sharpe_variance(0.09, BARS_PER_YEAR),
        folds=folds,
        n_controls=200,
        seed=SEED,
    )

    print(f"\n{out.verdict.report()}")
    print("\n  controls:")
    for c in out.controls:
        print(c.report())
    p = out.performance
    print(f"\n  annualised return {p.ann_return_pct:+.2f}%   vol {p.ann_vol_pct:.2f}%   "
          f"Sharpe {p.sharpe:+.3f}   maxDD {p.max_drawdown_pct:.2f}%")
    print(f"  profit factor {p.profit_factor:.3f}   hit rate {p.hit_rate_pct:.1f}%   "
          f"turnover {p.turnover_per_year:.0f}/yr")

    rotation = next(c for c in out.controls if c.method == "rotation")
    edge_detected = rotation.passes and out.dsr >= 0.95
    return out.verdict.passed, edge_detected


def main() -> int:
    print("=" * 78)
    print("PROVING THE LAB — identical pipeline, two worlds")
    print("=" * 78)
    print("Strategy under test: long after an up bar, short after a down bar.")
    print("It is a REAL edge in world 1 and pure noise in world 2. Same code both times.")

    real_pass, real_edge = evaluate(
        "WORLD 1 — edge deliberately planted", planted_momentum(N_BARS, SEED)
    )
    fake_pass, fake_edge = evaluate("WORLD 2 — pure random walk", random_walk(N_BARS, SEED))

    print("\n" + "=" * 78)
    print("SELF-TEST RESULT")
    print("=" * 78)
    print("  Edge detection — the controls and deflation only:")
    print(f"    saw the planted edge         : {'YES' if real_edge else 'NO'}   (must be YES)")
    print(f"    saw an edge in noise         : {'YES' if fake_edge else 'NO'}   (must be NO)")
    print("  Full gauntlet — edge detection plus the risk and cost gates:")
    print(f"    planted world ships          : {'YES' if real_pass else 'NO'}   (must be YES)")
    print(f"    random world ships           : {'YES' if fake_pass else 'NO'}   (must be NO)")

    ok = real_edge and not fake_edge and real_pass and not fake_pass
    print()
    if ok:
        print("  LAB IS TRUSTWORTHY. It finds what is there and refuses what is not.")
    else:
        print("  *** LAB IS BROKEN. Do not trust any result it produces. ***")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
