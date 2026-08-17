"""The order path's safeguards, tested without ever sending an order.

This is the one module in the project that can act on the account, so its refusals
are tested rather than trusted. Every test here asserts that something is REFUSED —
none of them place anything, and none of them need a terminal.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from goldlab.execution import mt5_demo


class _FakeAccount:
    """Minimal stand-in for mt5.account_info()."""

    def __init__(self, trade_mode: int, login: int = 472250693):
        self.trade_mode = trade_mode
        self.login = login


@pytest.fixture(autouse=True)
def _locked_by_default(monkeypatch):
    monkeypatch.delenv(mt5_demo.UNLOCK_ENV, raising=False)


def test_locked_unless_the_environment_says_otherwise(monkeypatch):
    """A script name or an import must never be enough to unlock the order path."""
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: _FakeAccount(0))
    with pytest.raises(mt5_demo.ExecutionRefusal, match="demo trading is locked"):
        mt5_demo.assert_unlocked()


def test_a_wrong_unlock_value_does_not_unlock(monkeypatch):
    monkeypatch.setenv(mt5_demo.UNLOCK_ENV, "true")     # not the required word
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: _FakeAccount(0))
    with pytest.raises(mt5_demo.ExecutionRefusal, match="locked"):
        mt5_demo.assert_unlocked()


def test_refuses_a_live_account_even_when_unlocked(monkeypatch):
    """The single most important refusal in the file."""
    monkeypatch.setenv(mt5_demo.UNLOCK_ENV, mt5_demo.UNLOCK_VALUE)
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: _FakeAccount(2))  # REAL
    with pytest.raises(mt5_demo.ExecutionRefusal, match="not DEMO"):
        mt5_demo.assert_unlocked()


def test_refuses_a_contest_account_too(monkeypatch):
    monkeypatch.setenv(mt5_demo.UNLOCK_ENV, mt5_demo.UNLOCK_VALUE)
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: _FakeAccount(1))  # CONTEST
    with pytest.raises(mt5_demo.ExecutionRefusal, match="not DEMO"):
        mt5_demo.assert_unlocked()


def test_a_demo_account_with_the_unlock_passes(monkeypatch):
    monkeypatch.setenv(mt5_demo.UNLOCK_ENV, mt5_demo.UNLOCK_VALUE)
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: _FakeAccount(0))
    mt5_demo.assert_unlocked()          # must not raise


def test_refuses_to_send_blind_when_the_account_cannot_be_read(monkeypatch):
    monkeypatch.setenv(mt5_demo.UNLOCK_ENV, mt5_demo.UNLOCK_VALUE)
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: None)
    with pytest.raises(mt5_demo.ExecutionRefusal, match="refusing to send blind"):
        mt5_demo.assert_unlocked()


def test_only_our_own_positions_are_visible(monkeypatch):
    """A human trading the same account by hand must be invisible and untouchable."""
    monkeypatch.setattr(mt5_demo.mt5, "positions_get", lambda: [
        SimpleNamespace(symbol="EURUSD", magic=mt5_demo.MAGIC, ticket=1, volume=0.5,
                        type=0, price_open=1.1, profit=1.0, swap=0.0, time=1_700_000_000),
        SimpleNamespace(symbol="XAUUSD", magic=999, ticket=2, volume=1.0,
                        type=0, price_open=4000.0, profit=0.0, swap=0.0, time=1_700_000_000),
    ])
    held = mt5_demo.our_positions()
    assert set(held) == {"EURUSD"}, "a position without our magic number must be invisible"


def test_a_short_position_comes_back_negative(monkeypatch):
    monkeypatch.setattr(mt5_demo.mt5, "positions_get", lambda: [
        SimpleNamespace(symbol="EURUSD", magic=mt5_demo.MAGIC, ticket=1, volume=0.5,
                        type=1, price_open=1.1, profit=0.0, swap=0.0, time=1_700_000_000),
    ])
    assert mt5_demo.our_positions()["EURUSD"]["lots"] == -0.5


def test_reconcile_reports_every_kind_of_disagreement(monkeypatch):
    """Local state drifting from broker state is how a small bug becomes a big position."""
    monkeypatch.setattr(mt5_demo.mt5, "positions_get", lambda: [
        SimpleNamespace(symbol="EURUSD", magic=mt5_demo.MAGIC, ticket=1, volume=0.5,
                        type=0, price_open=1.1, profit=0.0, swap=0.0, time=1_700_000_000),
        SimpleNamespace(symbol="US500", magic=mt5_demo.MAGIC, ticket=3, volume=2.0,
                        type=0, price_open=5000.0, profit=0.0, swap=0.0, time=1_700_000_000),
    ])
    _, problems = mt5_demo.reconcile({"EURUSD": 0.9, "XAUUSD": -0.1})

    joined = " | ".join(problems)
    assert "EURUSD" in joined and "0.90" in joined, "size mismatch must be reported"
    assert "XAUUSD" in joined and "broker holds nothing" in joined
    assert "US500" in joined and "we do not expect" in joined


def test_reconcile_is_silent_when_everything_agrees(monkeypatch):
    monkeypatch.setattr(mt5_demo.mt5, "positions_get", lambda: [
        SimpleNamespace(symbol="EURUSD", magic=mt5_demo.MAGIC, ticket=1, volume=0.5,
                        type=0, price_open=1.1, profit=0.0, swap=0.0, time=1_700_000_000),
    ])
    _, problems = mt5_demo.reconcile({"EURUSD": 0.5})
    assert problems == []


def test_slippage_is_signed_against_us(monkeypatch):
    """Positive slippage must always mean we paid worse, whichever way we traded."""
    bought_worse = mt5_demo.Fill("EURUSD", "BUY", 1.0, 1.1005, 1,
                                 mt5_demo.datetime.now(mt5_demo.timezone.utc), 1.1000)
    sold_worse = mt5_demo.Fill("EURUSD", "SELL", 1.0, 1.0995, 2,
                               mt5_demo.datetime.now(mt5_demo.timezone.utc), 1.1000)
    assert bought_worse.slippage_points > 0
    assert sold_worse.slippage_points > 0


def test_zero_lots_is_refused(monkeypatch):
    monkeypatch.setenv(mt5_demo.UNLOCK_ENV, mt5_demo.UNLOCK_VALUE)
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: _FakeAccount(0))
    with pytest.raises(mt5_demo.ExecutionRefusal, match="zero lots"):
        mt5_demo.open_position("EURUSD", 0.0)


def test_a_duplicate_open_is_refused(monkeypatch):
    monkeypatch.setenv(mt5_demo.UNLOCK_ENV, mt5_demo.UNLOCK_VALUE)
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: _FakeAccount(0))
    monkeypatch.setattr(mt5_demo.mt5, "positions_get", lambda: [
        SimpleNamespace(symbol="EURUSD", magic=mt5_demo.MAGIC, ticket=1, volume=0.5,
                        type=0, price_open=1.1, profit=0.0, swap=0.0, time=1_700_000_000),
    ])
    with pytest.raises(mt5_demo.ExecutionRefusal, match="already exists"):
        mt5_demo.open_position("EURUSD", 0.3)


def test_closing_something_we_do_not_own_is_refused(monkeypatch):
    monkeypatch.setenv(mt5_demo.UNLOCK_ENV, mt5_demo.UNLOCK_VALUE)
    monkeypatch.setattr(mt5_demo.mt5, "account_info", lambda: _FakeAccount(0))
    monkeypatch.setattr(mt5_demo.mt5, "positions_get", lambda: [])
    with pytest.raises(mt5_demo.ExecutionRefusal, match="no position of ours"):
        mt5_demo.close_position("XAUUSD")
