"""Pre-registration: write the hypothesis down BEFORE the test runs.

Humans, and models, revise their expectations after seeing a result and then
sincerely believe they expected it all along. "We thought this would work" is the
cheapest sentence in quantitative finance and it is unfalsifiable after the fact.

So every hypothesis in this project is written to an append-only, hash-chained log
before it is tested: what is being claimed, why the market should behave that way,
what would count as a pass, and how many parameter combinations will be tried.
Results are written afterwards as a separate linked entry. Neither can be edited —
tampering breaks the chain and ``verify()`` reports exactly where.

This also feeds the trial counter. Deflated Sharpe needs an honest count of how
many things were tried, and the only honest count is one kept automatically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


@dataclass(frozen=True)
class Hypothesis:
    name: str
    family: str
    """Which strategy family from the plan (A1, B3, C2, ...)."""

    claim: str
    """One sentence: what is being asserted about the market."""

    economic_rationale: str
    """WHY the market should behave this way. A hypothesis without a mechanism is
    a pattern someone noticed, and patterns are free."""

    pass_criteria: dict[str, float]
    """Thresholds, fixed now. These are never relaxed after a result is seen."""

    n_param_combinations: int
    """How many parameter sets will be tried. Feeds the multiple-testing penalty."""

    data_scope: str
    """Exactly which symbol, timeframe and date range is in scope."""

    predicted_outcome: str
    """The author's honest expectation, on record so it can be proved wrong."""

    author: str = "goldlab"


@dataclass(frozen=True)
class Result:
    hypothesis_name: str
    verdict: str
    """PASS / FAIL / NOT-MEASURABLE"""

    metrics: dict[str, Any]
    notes: str


@dataclass
class Entry:
    seq: int
    kind: str
    timestamp_utc: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str = field(default="")

    def compute_hash(self) -> str:
        body = json.dumps(
            {
                "seq": self.seq,
                "kind": self.kind,
                "timestamp_utc": self.timestamp_utc,
                "payload": self.payload,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


class PreRegistrationLog:
    """Append-only JSONL with a hash chain. Never updates, never deletes."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # --- reading ---

    def entries(self) -> list[Entry]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(Entry(**json.loads(line)))
        return out

    def _tail_hash(self) -> tuple[int, str]:
        existing = self.entries()
        if not existing:
            return 0, GENESIS
        return existing[-1].seq + 1, existing[-1].hash

    # --- writing ---

    def _append(self, kind: str, payload: dict[str, Any]) -> Entry:
        seq, prev = self._tail_hash()
        entry = Entry(
            seq=seq,
            kind=kind,
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            payload=payload,
            prev_hash=prev,
        )
        entry.hash = entry.compute_hash()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(entry), sort_keys=True, separators=(",", ":")) + "\n")
        return entry

    def register(self, hypothesis: Hypothesis) -> Entry:
        """Record a hypothesis. Must happen before the test is run."""
        if self.is_registered(hypothesis.name):
            raise ValueError(
                f"'{hypothesis.name}' is already registered. Re-registering a hypothesis "
                "after seeing a result is exactly what this log exists to prevent — "
                "register a new, differently-named hypothesis instead."
            )
        return self._append("hypothesis", asdict(hypothesis))

    def record_result(self, result: Result) -> Entry:
        if not self.is_registered(result.hypothesis_name):
            raise ValueError(
                f"no pre-registration found for '{result.hypothesis_name}'. "
                "Results cannot be recorded for a hypothesis that was never registered."
            )
        return self._append("result", asdict(result))

    # --- queries ---

    def is_registered(self, name: str) -> bool:
        return any(
            e.kind == "hypothesis" and e.payload.get("name") == name for e in self.entries()
        )

    def trial_count(self) -> int:
        """Total parameter combinations tried across every registered hypothesis.

        This is the N that Deflated Sharpe deflates by. It counts everything ever
        registered, including failures — which is the point. Forgetting the
        failures is what makes the survivor look significant.
        """
        return sum(
            int(e.payload.get("n_param_combinations", 0))
            for e in self.entries()
            if e.kind == "hypothesis"
        )

    def verify(self) -> tuple[bool, str]:
        """Recompute the chain. Returns (ok, message) naming the first bad entry."""
        prev = GENESIS
        for i, entry in enumerate(self.entries()):
            if entry.seq != i:
                return False, f"entry {i}: sequence number is {entry.seq}, expected {i}"
            if entry.prev_hash != prev:
                return False, f"entry {i}: prev_hash does not match entry {i - 1}"
            recomputed = entry.compute_hash()
            if recomputed != entry.hash:
                return False, f"entry {i} ('{entry.kind}'): contents were modified after writing"
            prev = entry.hash
        return True, f"chain intact across {len(self.entries())} entries"
