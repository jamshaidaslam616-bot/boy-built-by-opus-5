"""Macro data must never be visible before it was published.

This is the quietest source of look-ahead in the whole project. A macro series is
stamped with the date it DESCRIBES; joining it on that date hands a backtest a
number that did not exist yet, and the result looks like insight.

These tests use synthetic series so they run without a network.
"""

from __future__ import annotations

import pandas as pd
import pytest

from goldlab.data.macro import MacroSeries, assert_lag_is_not_optimistic, measure_publication_lag


def make(lag: int, values=(1.0, 2.0, 3.0)) -> MacroSeries:
    idx = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"], utc=True)
    return MacroSeries(
        series_id="TEST", name="test", values=pd.Series(values, index=idx),
        publication_lag_days=lag,
    )


def test_value_is_invisible_until_its_publication_date():
    """The 2026-01-06 observation, published 4 days later, cannot be seen on 01-07."""
    macro = make(lag=4)
    trading_days = pd.to_datetime(
        ["2026-01-07", "2026-01-09", "2026-01-10", "2026-01-11"], utc=True
    )
    seen = macro.as_known_on(trading_days)

    assert pd.isna(seen.loc["2026-01-07"]), (
        "nothing had been published by 01-07; the first observation lands on 01-09"
    )
    assert seen.loc["2026-01-09"] == 1.0, "the 01-05 observation becomes known on 01-09"
    assert seen.loc["2026-01-10"] == 2.0
    assert seen.loc["2026-01-11"] == 3.0


def test_zero_lag_would_leak_and_the_difference_is_visible():
    """Contrast the correct alignment with the naive one, so the size of the leak is explicit."""
    correct = make(lag=4).as_known_on(pd.to_datetime(["2026-01-05"], utc=True))
    leaky = make(lag=0).as_known_on(pd.to_datetime(["2026-01-05"], utc=True))

    assert pd.isna(correct.iloc[0]), "with a real lag, nothing is known on the observation date"
    assert leaky.iloc[0] == 1.0, "with no lag, the strategy reads the value on its own date"


def test_values_are_held_forward_not_interpolated():
    """Between releases the last PUBLISHED value stands. Interpolating invents data."""
    macro = make(lag=1)
    days = pd.date_range("2026-01-06", "2026-01-12", freq="D", tz="UTC")
    seen = macro.as_known_on(days)

    # lag=1, so observations 01-05/06/07 become known on 01-06/07/08 respectively.
    assert seen.loc["2026-01-06"] == 1.0
    assert seen.loc["2026-01-07"] == 2.0
    assert seen.loc["2026-01-08"] == 3.0
    assert seen.loc["2026-01-12"] == 3.0, "the newest published value persists between releases"
    assert seen.dropna().isin([1.0, 2.0, 3.0]).all(), "no value may appear that was never published"


def test_measure_publication_lag_reports_feed_staleness():
    macro = make(lag=4)
    assert measure_publication_lag(macro.values, pd.Timestamp("2026-01-12", tz="UTC")) == 5


def test_an_optimistic_lag_is_rejected():
    """If a feed's schedule slips, a hardcoded lag silently becomes look-ahead."""
    macro = make(lag=2)  # claims 2 days, but the feed is 5 days stale
    with pytest.raises(ValueError, match="optimistic"):
        assert_lag_is_not_optimistic(macro, pd.Timestamp("2026-01-12", tz="UTC"))


def test_a_generous_lag_is_accepted():
    assert_lag_is_not_optimistic(make(lag=10), pd.Timestamp("2026-01-12", tz="UTC"))
