"""Paper state must survive between runs, or the experiment measures nothing.

The runner's first version built a fresh broker every invocation. Positions were
opened and never closed, equity reset to the starting capital each day, and the
equity curve recorded only that day's opening costs. It produced a filling journal
and plausible numbers while tracking absolutely nothing.

That is the failure mode worth guarding hardest: output that is present and
meaningless. These tests make it impossible to reintroduce silently.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from goldlab.execution import state as paper_state
from goldlab.execution.paper import PaperBroker


def _now() -> datetime:
    return datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def test_positions_and_equity_survive_a_round_trip(tmp_path):
    path = tmp_path / "state.json"
    broker = PaperBroker(equity=100_000.0)
    broker.open("EURUSD", 1.5, 1.155, 100_000.0, _now())
    broker.open("XAUUSD", -0.02, 4342.0, 100.0, _now())
    equity_after_costs = broker.equity

    paper_state.save(path, broker, peak_equity=100_000.0)
    restored = paper_state.load(path, initial_equity=100_000.0)

    assert restored.equity == pytest.approx(equity_after_costs)
    assert set(restored.positions) == {"EURUSD", "XAUUSD"}
    assert restored.positions["EURUSD"].lots == pytest.approx(1.5)
    assert restored.positions["XAUUSD"].lots == pytest.approx(-0.02)
    assert restored.positions["EURUSD"].entry_price == pytest.approx(1.155)
    assert restored.costs_paid == pytest.approx(broker.costs_paid)


def test_a_first_run_starts_clean_rather_than_failing(tmp_path):
    broker = paper_state.load(tmp_path / "absent.json", initial_equity=50_000.0)
    assert broker.equity == 50_000.0
    assert broker.positions == {}


def test_the_open_date_survives_so_the_free_window_is_tracked(tmp_path):
    """The 7-day financing-free window is measured from the open.

    If the open date reset on every restart the window would never expire, and the
    book would silently start paying swap it was designed to avoid.
    """
    path = tmp_path / "state.json"
    opened = _now() - timedelta(days=6)
    broker = PaperBroker(equity=100_000.0)
    broker.open("EURUSD", 1.0, 1.155, 100_000.0, opened)

    paper_state.save(path, broker, peak_equity=100_000.0)
    restored = paper_state.load(path, initial_equity=100_000.0)

    assert restored.positions["EURUSD"].opened_utc == opened
    assert restored.positions["EURUSD"].days_held(_now()) == 6
    assert "EURUSD" in restored.stale_positions(_now()), (
        "a position six days old must be flagged before the seven-day window closes"
    )


def test_peak_equity_survives_so_the_drawdown_halt_can_fire(tmp_path):
    """A peak that resets on restart is a drawdown limit that can never trip."""
    path = tmp_path / "state.json"
    broker = PaperBroker(equity=90_000.0)
    paper_state.save(path, broker, peak_equity=120_000.0)

    assert paper_state.peak_equity(path, current=90_000.0) == 120_000.0
    # A new high replaces it; a lower reading never does.
    assert paper_state.peak_equity(path, current=130_000.0) == 130_000.0


def test_saving_is_atomic(tmp_path):
    """A half-written state file would lose the entire book."""
    path = tmp_path / "state.json"
    broker = PaperBroker(equity=100_000.0)
    broker.open("EURUSD", 1.0, 1.155, 100_000.0, _now())
    paper_state.save(path, broker, peak_equity=100_000.0)

    assert path.exists()
    assert not path.with_suffix(".tmp").exists(), "temp file was left behind"
    paper_state.load(path, 100_000.0)  # must parse cleanly


def test_realised_pnl_accumulates_across_saves(tmp_path):
    path = tmp_path / "state.json"
    broker = PaperBroker(equity=100_000.0)
    broker.open("EURUSD", 1.0, 1.155, 100_000.0, _now())
    broker.close("EURUSD", 1.165)          # +$1,000 gross on one lot
    assert broker.realised > 0

    paper_state.save(path, broker, peak_equity=101_000.0)
    assert paper_state.load(path, 100_000.0).realised == pytest.approx(broker.realised)
