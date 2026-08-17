"""Fetch H4 bars for the whole universe, so cross-sectional can be tested intraday.

Everything cross-sectional so far has run on daily bars. P7 measured H4 as the only
timeframe whose variance ratio exceeds 1.0 and whose post-bar continuation is larger
than a round trip — the one place the data suggested looking. P8 then tested
TIME-SERIES trend there and it failed, but cross-sectional was never tried at that
frequency, and it is a different effect.

Only XAUUSD H4 was cached; the other twenty-four need pulling. H4 is six bars a day,
so this is roughly six times the daily history per instrument and the chunked
fetcher matters — a single oversized request returns `None (Invalid params)` rather
than truncating.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.broker import mt5_read as br  # noqa: E402
from goldlab.data import history as hist  # noqa: E402
from goldlab.strategy import production as prod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
START = datetime(2015, 1, 1, tzinfo=timezone.utc)


def main() -> int:
    br.connect()
    try:
        print("=" * 88)
        print(f"P24 — H4 HISTORY FOR {len(prod.UNIVERSE)} INSTRUMENTS")
        print("=" * 88)

        ok, thin, failed = [], [], []
        for symbol in prod.UNIVERSE:
            for attempt in range(3):
                try:
                    df = hist.fetch(symbol, "H4", START)
                    break
                except Exception as exc:
                    if attempt == 2:
                        print(f"  {symbol:<9} FAILED ({type(exc).__name__})")
                        failed.append(symbol)
                        df = None
            if df is None:
                continue

            rep = hist.quality_gate(df, symbol, "H4")
            window = hist.usable_window(rep)
            hist.save(df, ROOT, symbol, "H4")
            years = (df.index[-1] - df.index[0]).days / 365.25

            note = ""
            if window is None:
                note = "  <-- no year meets coverage"
                thin.append(symbol)
            elif window[1] - window[0] + 1 < 4:
                note = f"  <-- only {window[1] - window[0] + 1}y usable"
                thin.append(symbol)
            else:
                ok.append(symbol)

            print(f"  {symbol:<9} {len(df):>7,} bars  {df.index[0]:%Y-%m}..{df.index[-1]:%Y-%m}"
                  f"  {years:>5.1f}y  usable from {window[0] if window else '-'}{note}")

        print("\n" + "=" * 88)
        print(f"  usable {len(ok)} · thin {len(thin)} · failed {len(failed)}")
        if thin:
            print(f"  thin:   {thin}")
        if failed:
            print(f"  failed: {failed}")
        print("\n  A cross-section needs every leg present on the same bar, so the shared")
        print("  window across all of these is what the test actually gets — not the")
        print("  longest single history.")
        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
