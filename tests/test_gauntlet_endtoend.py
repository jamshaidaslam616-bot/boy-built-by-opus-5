"""End-to-end proof, kept in the suite so it can never silently regress.

``scripts/p1_prove_the_harness.py`` runs this at full size for the written record.
This is the fast version that CI-style runs will catch a regression with.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from goldlab.research.gauntlet import run_gauntlet
from goldlab.research.metrics import annualised_to_per_bar_sharpe_variance
from goldlab.research.returns import CostModel, vol_target
from goldlab.research.splits import purged_walk_forward

BARS_PER_YEAR = 252.0
N_BARS = 2500


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2015-01-02", periods=n, freq="B", tz="UTC")


def _random_walk(n: int, seed: int, sigma: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0, sigma, n))), index=_index(n))


def _planted(n: int, seed: int, strength: float = 0.20, sigma: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, sigma, n)
    r = np.zeros(n)
    r[0] = noise[0]
    for t in range(1, n):
        r[t] = strength * sigma * np.sign(r[t - 1]) + noise[t]
    return pd.Series(100.0 * np.exp(np.cumsum(r)), index=_index(n))


def _costs() -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR,
    )


def _run(close: pd.Series, name: str):
    raw = np.sign(close.pct_change()).fillna(0.0)
    pos = vol_target(raw, close, 0.10, 60, BARS_PER_YEAR)
    folds = purged_walk_forward(
        close.index, n_folds=3, lookback_bars=1, holding_bars=5, min_train_bars=600
    )
    return run_gauntlet(
        name=name, position=pos, close=close, costs=_costs(),
        bars_per_year=BARS_PER_YEAR, n_trials=50,
        sharpe_variance_across_trials=annualised_to_per_bar_sharpe_variance(0.09, BARS_PER_YEAR),
        folds=folds, n_controls=60, seed=20260808,
    )


def test_full_gauntlet_ships_a_real_edge():
    out = _run(_planted(N_BARS, 20260808), "planted")
    assert out.verdict.passed, (
        "the whole pipeline rejected a deliberately planted edge:\n" + out.verdict.report()
    )


def test_full_gauntlet_rejects_pure_noise():
    out = _run(_random_walk(N_BARS, 20260808), "noise")
    assert not out.verdict.passed, (
        "the whole pipeline approved a pure random walk:\n" + out.verdict.report()
    )
    rotation = next(c for c in out.controls if c.method == "rotation")
    assert not rotation.passes
    assert out.dsr < 0.95


def test_vol_targeting_is_what_brings_drawdown_inside_the_limit():
    """Documents why sizing is mandatory rather than optional.

    Unsized, the planted strategy has a genuine edge and still breaches the 15%
    drawdown gate. That is a sizing failure, not evidence against the signal — and
    it is exactly the mistake the first run of the proof script made.
    """
    close = _planted(N_BARS, 20260808)
    raw = np.sign(close.pct_change()).fillna(0.0)

    from goldlab.research.metrics import max_drawdown_pct
    from goldlab.research.returns import strategy_returns

    unsized_dd = max_drawdown_pct(strategy_returns(raw, close, _costs()))
    sized_dd = max_drawdown_pct(
        strategy_returns(vol_target(raw, close, 0.10, 60, BARS_PER_YEAR), close, _costs())
    )

    assert unsized_dd > sized_dd, "volatility targeting must reduce drawdown"
    assert sized_dd <= 15.0, "and must bring it inside the gate"
