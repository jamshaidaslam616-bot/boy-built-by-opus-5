"""Sizing is the one place a bug costs money directly, so it gets hostile tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from goldlab.research.returns import CostModel
from goldlab.research.sizing import (
    LIVE_HALT_PCT,
    bootstrap_max_drawdowns,
    largest_compliant_size,
)

BARS_PER_YEAR = 260.0


def _series(n: int, seed: int, drift: float = 0.0003, sigma: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B", tz="UTC")
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(drift, sigma, n))), index=idx)


def _costs() -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0, bars_per_year=BARS_PER_YEAR,
    )


def test_bootstrap_p95_exceeds_the_single_observed_path():
    """The measured 1.58x understatement must reproduce, not be a one-off."""
    from goldlab.research.metrics import max_drawdown_pct

    close = _series(3000, seed=11)
    returns = close.pct_change().dropna()
    observed = max_drawdown_pct(returns)
    p95 = float(np.percentile(bootstrap_max_drawdowns(returns, n_paths=400), 95))

    assert p95 > observed, (
        "the 95th-percentile resampled drawdown must exceed the single observed path; "
        "if it does not, the bootstrap is not preserving the structure that creates drawdowns"
    )


def test_a_bigger_target_is_never_returned_than_the_halt_allows():
    close = _series(3000, seed=12)
    raw = np.sign(close.pct_change()).fillna(0.0).clip(lower=0.0)

    result = largest_compliant_size(raw, close, _costs(), BARS_PER_YEAR, n_paths=200)
    if result is not None:
        assert result.p95_drawdown_pct <= LIVE_HALT_PCT


def test_none_when_nothing_complies_rather_than_a_silent_fallback():
    """A wildly volatile series must yield None, not the smallest candidate."""
    close = _series(3000, seed=13, sigma=0.12)
    raw = pd.Series(1.0, index=close.index)

    result = largest_compliant_size(
        raw, close, _costs(), BARS_PER_YEAR, live_halt_pct=1.0, n_paths=120
    )
    assert result is None, "must report 'no compliant size' rather than quietly returning one"


def test_a_tighter_halt_never_permits_a_bigger_position():
    """Monotonicity — the property a stale hardcoded limit would violate."""
    close = _series(2500, seed=14)
    raw = np.sign(close.pct_change()).fillna(0.0).clip(lower=0.0)

    loose = largest_compliant_size(raw, close, _costs(), BARS_PER_YEAR,
                                   live_halt_pct=30.0, n_paths=200)
    tight = largest_compliant_size(raw, close, _costs(), BARS_PER_YEAR,
                                   live_halt_pct=10.0, n_paths=200)
    if loose is not None and tight is not None:
        assert tight.vol_target <= loose.vol_target


def test_live_halt_is_the_owner_authorised_figure():
    """Guards against the limit being edited without the owner deciding to."""
    assert LIVE_HALT_PCT == 25.0, (
        "the live halt is owner-set. It was raised to 25% on 2026-08-17 with "
        "explicit authorisation. Changing it again requires the owner, not a code edit."
    )
