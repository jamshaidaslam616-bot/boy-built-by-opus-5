"""Book-level sizing, and the property that matters most: it must match the backtest.

The owner approved moving from per-trade stop risk to book-level volatility targeting
on 2026-08-16, after the first paper run refused 11 of 14 legs. The danger in that
change is subtle: if live sizing and backtest sizing differ, then the thing being
measured and the thing being traded are two different strategies, and every result
becomes fiction.

P19's backtest sized each leg as ``weight / volatility``, normalised to unit gross,
then scaled the book. ``risk.book_leg_size`` must produce the same relative sizes.
That equivalence is what these tests pin.
"""

from __future__ import annotations

import numpy as np
import pytest

from goldlab.safety import risk


def _state(equity: float = 100_000.0) -> risk.RiskState:
    return risk.RiskState(equity=equity, peak_equity=equity)


def _size(**kw) -> float:
    args = dict(symbol="EURUSD", weight=0.10, price=1.155, annual_vol=0.046,
                contract_size=100_000.0, volume_min=0.01, volume_step=0.01,
                volume_max=200.0, n_legs=14)
    args.update(kw)
    return risk.book_leg_size(_state(), **args)


def test_relative_sizes_match_the_backtest_formula():
    """Two markets at equal weight must be sized inversely to their volatility.

    This is the whole content of "equal risk per leg", and it is exactly what the
    P19 backtest did. If this drifts, live and backtest are different strategies.
    """
    quiet = _size(symbol="A", annual_vol=0.05, price=100.0, contract_size=1_000.0,
                  volume_min=0.0001, volume_step=0.0001)
    wild = _size(symbol="B", annual_vol=0.20, price=100.0, contract_size=1_000.0,
                 volume_min=0.0001, volume_step=0.0001)

    # Four times the volatility must get a quarter of the notional.
    assert quiet / wild == pytest.approx(4.0, rel=0.02)


def test_weight_scales_the_leg_linearly():
    small = _size(weight=0.05, volume_min=0.0001, volume_step=0.0001)
    big = _size(weight=0.20, volume_min=0.0001, volume_step=0.0001)
    assert big / small == pytest.approx(4.0, rel=0.02)


def test_a_short_leg_comes_back_negative():
    assert _size(weight=-0.10) < 0
    assert _size(weight=+0.10) > 0


def test_the_per_leg_ceiling_binds_when_volatility_collapses():
    """A market whose volatility estimate collapses must not become the whole book."""
    normal = _size(annual_vol=0.10, volume_min=0.0001, volume_step=0.0001)
    collapsed = _size(annual_vol=0.001, volume_min=0.0001, volume_step=0.0001)

    # Without the cap this would be exactly 100x larger, since sizing divides by
    # volatility. The cap must break that proportionality.
    assert collapsed < normal * 100, "the per-leg ceiling is not binding"

    notional = abs(collapsed) * 1_000.0 * 100.0
    ceiling = 100_000.0 * risk.MAX_LEG_NOTIONAL_MULTIPLE
    assert notional <= ceiling + 1.0, (
        f"leg notional ${notional:,.0f} exceeded the ${ceiling:,.0f} hard ceiling"
    )


def test_refuses_rather_than_rounding_up_to_the_minimum():
    with pytest.raises(risk.RiskRefusal, match="Refusing rather than rounding up"):
        _size(volume_min=10.0, volume_step=10.0)


def test_refuses_a_zero_or_negative_volatility():
    for bad in (0.0, -0.1):
        with pytest.raises(risk.RiskRefusal, match="annual volatility"):
            _size(annual_vol=bad)


def test_a_halted_book_sizes_nothing():
    state = _state()
    state.halted = True
    state.halt_reason = "drawdown limit"
    with pytest.raises(risk.RiskRefusal, match="halted"):
        risk.book_leg_size(
            state, symbol="EURUSD", weight=0.1, price=1.155, annual_vol=0.046,
            contract_size=100_000.0, volume_min=0.01, volume_step=0.01,
            volume_max=200.0, n_legs=14,
        )


def test_book_volatility_lands_near_its_target():
    """Fourteen legs sized this way should produce roughly the intended book volatility.

    Legs are assumed to diversify, which is why the budget divides by sqrt(n) rather
    than n. This checks the arithmetic delivers what it claims rather than being off
    by the square root — an error that would silently run the book at 3.7x intended.
    """
    equity, n_legs = 100_000.0, 14
    total_var = 0.0
    for _ in range(n_legs):
        lots = _size(weight=1.0 / n_legs, annual_vol=0.15, price=100.0,
                     contract_size=1_000.0, volume_min=0.0001, volume_step=0.0001)
        leg_vol_usd = abs(lots) * 1_000.0 * 100.0 * 0.15
        total_var += leg_vol_usd ** 2          # independent legs add in quadrature

    book_vol_pct = np.sqrt(total_var) / equity
    assert book_vol_pct == pytest.approx(risk.BOOK_VOL_TARGET, rel=0.25), (
        f"book volatility came out at {book_vol_pct:.2%} against a "
        f"{risk.BOOK_VOL_TARGET:.2%} target"
    )
