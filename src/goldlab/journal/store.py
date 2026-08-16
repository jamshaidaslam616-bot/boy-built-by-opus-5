"""Append-only decision journal.

Its purpose is to make "why did it hold that in March" a question with an answer,
months later, without anyone having to remember. Three rules make that work:

  * **Nothing is ever updated or deleted.** Corrections are new rows. A journal that
    can be edited is a story, not a record.
  * **Every input to a decision is stored, not just the outcome.** A size can be
    recomputed by hand from its row years later; if it cannot, the row is incomplete.
  * **Refusals are recorded as carefully as trades.** The times this system declined
    to act are evidence about it, and they are the first thing that disappears from a
    log that only records fills.

SQLite because it is ACID, single-writer — exactly this access pattern — survives a
crash mid-write, and is still queryable with plain SQL long after this code is gone.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    written_utc   TEXT    NOT NULL,
    bar_utc       TEXT    NOT NULL,
    run_id        TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    action        TEXT    NOT NULL,   -- TARGET | REFUSED | HALTED | HOLD
    rank          INTEGER,
    weight        REAL,
    trailing_ret  REAL,
    price         REAL,
    lots          REAL,
    equity        REAL,
    reason        TEXT    NOT NULL,
    inputs_json   TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    written_utc   TEXT    NOT NULL,
    bar_utc       TEXT    NOT NULL,
    run_id        TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    side          TEXT    NOT NULL,
    lots          REAL    NOT NULL,
    price         REAL    NOT NULL,
    cost_usd      REAL    NOT NULL,
    mode          TEXT    NOT NULL   -- PAPER | DEMO | LIVE
);
CREATE TABLE IF NOT EXISTS equity_curve (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    bar_utc       TEXT    NOT NULL UNIQUE,
    run_id        TEXT    NOT NULL,
    equity        REAL    NOT NULL,
    peak_equity   REAL    NOT NULL,
    drawdown_pct  REAL    NOT NULL,
    open_legs     INTEGER NOT NULL,
    halted        INTEGER NOT NULL,
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_bar ON decisions(bar_utc);
CREATE INDEX IF NOT EXISTS idx_fills_bar ON fills(bar_utc);
"""


@dataclass(frozen=True)
class Decision:
    bar_utc: datetime
    symbol: str
    action: str
    reason: str
    inputs: dict[str, Any]
    rank: int | None = None
    weight: float | None = None
    trailing_ret: float | None = None
    price: float | None = None
    lots: float | None = None
    equity: float | None = None


class Journal:
    def __init__(self, path: Path | str, run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def record_decision(self, decision: Decision) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO decisions (written_utc, bar_utc, run_id, symbol, action, rank, "
                "weight, trailing_ret, price, lots, equity, reason, inputs_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    decision.bar_utc.isoformat(),
                    self.run_id, decision.symbol, decision.action, decision.rank,
                    decision.weight, decision.trailing_ret, decision.price, decision.lots,
                    decision.equity, decision.reason,
                    json.dumps(decision.inputs, sort_keys=True, default=str),
                ),
            )

    def record_fill(self, bar_utc: datetime, symbol: str, side: str, lots: float,
                    price: float, cost_usd: float, mode: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO fills (written_utc, bar_utc, run_id, symbol, side, lots, price, "
                "cost_usd, mode) VALUES (?,?,?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 bar_utc.isoformat(), self.run_id, symbol, side, lots, price, cost_usd, mode),
            )

    def record_equity(self, bar_utc: datetime, equity: float, peak_equity: float,
                      drawdown_pct: float, open_legs: int, halted: bool,
                      note: str = "") -> None:
        """One row per bar. ``INSERT OR IGNORE`` so a re-run cannot double-count a day."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO equity_curve (bar_utc, run_id, equity, peak_equity, "
                "drawdown_pct, open_legs, halted, note) VALUES (?,?,?,?,?,?,?,?)",
                (bar_utc.isoformat(), self.run_id, equity, peak_equity, drawdown_pct,
                 open_legs, int(halted), note),
            )

    # ------------------------------------------------------------------ reading

    def equity_series(self):
        import pandas as pd
        with self._connect() as conn:
            df = pd.read_sql_query(
                "SELECT bar_utc, equity, drawdown_pct, open_legs, halted "
                "FROM equity_curve ORDER BY bar_utc", conn
            )
        if df.empty:
            return df
        df["bar_utc"] = pd.to_datetime(df["bar_utc"], utc=True)
        return df.set_index("bar_utc")

    def refusals(self, limit: int = 50):
        import pandas as pd
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT bar_utc, symbol, action, reason FROM decisions "
                "WHERE action IN ('REFUSED','HALTED') ORDER BY id DESC LIMIT ?",
                conn, params=(limit,),
            )

    def observation_count(self) -> int:
        """Out-of-sample bars accumulated so far.

        This is the number that actually matters: establishing the measured Sharpe
        needs roughly 16 years of them, and this counter is the only honest record
        of how far along that is.
        """
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM equity_curve").fetchone()[0])
