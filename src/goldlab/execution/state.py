"""Persist the paper book between runs.

The first version of the runner built a fresh ``PaperBroker`` on every invocation.
Positions were opened and never closed, equity reset to the starting capital each
day, and the recorded equity curve showed nothing but that day's opening costs. It
looked like it was working — a journal filled up, numbers appeared — and it was
tracking nothing at all.

That is worth stating plainly because it is the same failure this whole project
keeps finding: output that is present, plausible, and meaningless. A paper run whose
state does not survive to the next run is not an experiment, it is a screensaver.

JSON rather than the SQLite journal because these are two different things. The
journal is an append-only *record* of what happened and must never be rewritten;
this is *current state* and is replaced every run. Mixing them would make the record
mutable.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .paper import PaperBroker, Position


def load(path: Path | str, initial_equity: float) -> PaperBroker:
    """Restore the book, or start a new one if this is the first run."""
    path = Path(path)
    if not path.exists():
        return PaperBroker(equity=initial_equity)

    raw = json.loads(path.read_text(encoding="utf-8"))
    positions = {
        symbol: Position(
            symbol=p["symbol"], lots=p["lots"], entry_price=p["entry_price"],
            opened_utc=datetime.fromisoformat(p["opened_utc"]),
            contract_size=p["contract_size"],
        )
        for symbol, p in raw.get("positions", {}).items()
    }
    return PaperBroker(
        equity=raw["equity"], positions=positions,
        realised=raw.get("realised", 0.0), costs_paid=raw.get("costs_paid", 0.0),
    )


def save(path: Path | str, broker: PaperBroker, peak_equity: float) -> None:
    """Write atomically — a half-written state file would lose the whole book."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equity": broker.equity,
        "realised": broker.realised,
        "costs_paid": broker.costs_paid,
        "peak_equity": peak_equity,
        "positions": {
            symbol: {**asdict(p), "opened_utc": p.opened_utc.isoformat()}
            for symbol, p in broker.positions.items()
        },
    }
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def peak_equity(path: Path | str, current: float) -> float:
    """Highest equity ever seen. Drives the drawdown halt, so it must survive restarts.

    A peak that resets on restart is a drawdown limit that can never fire.
    """
    path = Path(path)
    stored = 0.0
    if path.exists():
        stored = float(json.loads(path.read_text(encoding="utf-8")).get("peak_equity", 0.0))
    return max(stored, current)
