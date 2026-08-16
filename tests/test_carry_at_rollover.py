"""Financing must be charged at the rollover, not smeared over every bar.

The first version spread the annual rate evenly across bars. On daily data that is
right. On intraday data it charges a position that is flat overnight for financing
it never owed — which penalises precisely the strategy designed to avoid the charge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from goldlab.research.returns import CostModel, strategy_returns

DAILY_BPY = 260.0
HOURLY_BPY = 24 * 260.0


def _costs(bars_per_year: float, carry_long: float = -5.66) -> CostModel:
    return CostModel(
        spread_bp=0.0, commission_bp=0.0, slippage_bp=0.0,
        carry_long_annual_pct=carry_long, carry_short_annual_pct=0.0,
        bars_per_year=bars_per_year,
    )


def test_flat_overnight_pays_no_financing():
    """The whole point: a position closed before the rollover owes nothing."""
    idx = pd.date_range("2026-03-02 00:00", periods=24 * 10, freq="h", tz="UTC")
    close = pd.Series(100.0, index=idx)

    always_open = pd.Series(1.0, index=idx)
    flat_at_night = always_open.copy()
    flat_at_night[(idx.hour >= 20) | (idx.hour < 2)] = 0.0

    held = strategy_returns(always_open, close, _costs(HOURLY_BPY)).sum()
    intraday = strategy_returns(flat_at_night, close, _costs(HOURLY_BPY)).sum()

    assert held < 0, "an always-open long must pay financing"
    assert intraday == pytest.approx(0.0, abs=1e-12), (
        "a position flat across every rollover must owe exactly zero financing; "
        f"got {intraday:.8f}"
    )


def test_daily_bars_are_unchanged_by_the_fix():
    """On daily data each bar spans one night, so the old behaviour must survive."""
    idx = pd.date_range("2026-03-02", periods=469, freq="D", tz="UTC")
    close = pd.Series(100.0, index=idx)
    total = strategy_returns(pd.Series(1.0, index=idx), close, _costs(DAILY_BPY)).sum()

    # 469 days containing 67 Wednesdays, each charged triple: 469 + 2*67 = 603 nights.
    wednesdays = int((idx.weekday == 2).sum())
    expected = -(5.66 / 100.0) * (469 + 2 * wednesdays) / 469.0
    assert total == pytest.approx(expected, rel=0.02)


def test_the_triple_night_costs_three_times_a_normal_one():
    idx = pd.date_range("2026-03-02", periods=7, freq="D", tz="UTC")  # Mon..Sun
    close = pd.Series(100.0, index=idx)
    charges = strategy_returns(pd.Series(1.0, index=idx), close, _costs(DAILY_BPY))

    wed = charges[charges.index.weekday == 2].iloc[0]
    tue = charges[charges.index.weekday == 1].iloc[0]
    assert wed == pytest.approx(3.0 * tue, rel=1e-9), "Wednesday must cost three nights"


def test_a_weekend_gap_does_not_make_hourly_bars_look_daily():
    """Bar length must come from the median gap, not the first one.

    Real hourly series start with, or contain, weekend gaps. Inferring the bar
    length from the first two timestamps read a 24-hour gap as the bar size, sent
    hourly data down the daily branch, and charged one night per BAR — 24x too much.
    """
    weekday = pd.date_range("2026-03-06 20:00", periods=4, freq="h", tz="UTC")
    after_gap = pd.date_range("2026-03-08 22:00", periods=24 * 5, freq="h", tz="UTC")
    idx = weekday.append(after_gap)  # first gap is 2 hours, but a 50-hour gap follows

    close = pd.Series(100.0, index=idx)
    total = strategy_returns(pd.Series(1.0, index=idx), close, _costs(HOURLY_BPY)).sum()

    nights = int((idx.hour == 0).sum()) + 2 * int(((idx.hour == 0) & (idx.weekday == 2)).sum())
    expected = -(5.66 / 100.0) * nights / 469.0
    assert total == pytest.approx(expected, rel=1e-6), (
        "hourly bars must be charged once per rollover, not once per bar"
    )


def test_a_short_pays_the_short_rate_not_the_long_one():
    idx = pd.date_range("2026-03-02", periods=30, freq="D", tz="UTC")
    close = pd.Series(100.0, index=idx)
    costs = CostModel(
        spread_bp=0.0, commission_bp=0.0, slippage_bp=0.0,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0, bars_per_year=DAILY_BPY,
    )
    short = strategy_returns(pd.Series(-1.0, index=idx), close, costs).sum()
    assert short == pytest.approx(0.0, abs=1e-12), (
        "this broker pays 0.00% on shorts, so a short must owe nothing"
    )
