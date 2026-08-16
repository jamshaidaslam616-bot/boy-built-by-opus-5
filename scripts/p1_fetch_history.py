"""Fetch gold and silver history into the local cache, and report what is usable.

Read-only against the broker. Prints the quality gate's verdict for every series,
including the distinction between how much history the archive *claims* and how
much is actually at full resolution.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.broker import mt5_read as br  # noqa: E402
from goldlab.data import history as hist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
START = datetime(2010, 1, 1, tzinfo=timezone.utc)
SERIES = [("XAUUSD", tf) for tf in ("D1", "H4", "H1", "M15")] + [("XAGUSD", "D1")]


def main() -> int:
    br.connect()
    try:
        for symbol, timeframe in SERIES:
            print(f"\nfetching {symbol} {timeframe} ...", flush=True)
            try:
                df = hist.fetch(symbol, timeframe, START)
            except RuntimeError as exc:
                print(f"  SKIPPED — {exc}")
                continue

            rep = hist.quality_gate(df, symbol, timeframe)
            path = hist.save(df, ROOT, symbol, timeframe)

            print()
            print(rep.report())
            window = hist.usable_window(rep)
            if window:
                span = window[1] - window[0] + 1
                print(f"  USABLE WINDOW: {window[0]}..{window[1]}  ({span} full years)")
                if window[0] > rep.first.year:
                    print(f"    note: archive claims data from {rep.first.year}, but the years")
                    print(f"    before {window[0]} are too thin to be a real {timeframe} series.")
            else:
                print("  USABLE WINDOW: none — no year meets the coverage bar")
            print(f"  cached -> {path}")
        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
