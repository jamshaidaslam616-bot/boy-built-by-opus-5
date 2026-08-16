"""Download daily history for a diversified, sizeable basket.

Chosen from the universe P10 measured, on three rules:

  * **Sizeable** — the minimum position has to fit inside its slice of the risk
    budget. This is the check that excluded futures in F11 and it excludes plenty
    of instruments here too.
  * **Across asset classes** — the whole point is low pairwise correlation. Nine
    currency pairs are not nine markets; they are mostly one dollar bet.
  * **Liquid majors only** — no exotics, no single stocks. Single-name CFDs carry
    dividend adjustments and corporate actions that this cost model does not
    handle, and pretending otherwise would put a known error into every result.
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

BASKET = {
    "FX majors": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"],
    "FX scandies": ["USDNOK", "USDSEK"],
    "Metals": ["XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD"],
    "Energy": ["USOIL", "UKOIL", "XNGUSD"],
    "Indices": ["US500", "USTEC"],
    "Crypto": ["BTCUSD", "ETHUSD"],
}


def main() -> int:
    br.connect()
    try:
        ok, thin, missing = [], [], []
        for group, symbols in BASKET.items():
            print(f"\n{group}")
            for symbol in symbols:
                try:
                    df = hist.fetch(symbol, "D1", START)
                except Exception as exc:
                    print(f"  {symbol:<10} MISSING ({type(exc).__name__})")
                    missing.append(symbol)
                    continue

                rep = hist.quality_gate(df, symbol, "D1")
                window = hist.usable_window(rep)
                hist.save(df, ROOT, symbol, "D1")

                years = (df.index[-1] - df.index[0]).days / 365.25
                zeros = next(
                    (w for w in rep.warnings if "ZERO" in w), ""
                )
                zero_pct = float(zeros.split("(")[1].split("%")[0]) if zeros else 0.0

                flag = ""
                if years < 6:
                    flag = "  <-- short history"
                    thin.append(symbol)
                else:
                    ok.append(symbol)

                print(f"  {symbol:<10} {len(df):>6,} bars  {df.index[0]:%Y-%m}..{df.index[-1]:%Y-%m}"
                      f"  {years:>5.1f}y  zero-spread {zero_pct:>5.1f}%"
                      f"  usable {window[0] if window else '-'}{flag}")

        print("\n" + "=" * 78)
        print(f"  usable (>=6y): {len(ok)}   short: {len(thin)}   missing: {len(missing)}")
        if thin:
            print(f"  short history: {thin}")
        if missing:
            print(f"  missing:       {missing}")
        print()
        print("  A common start date matters more than a long one: a portfolio backtest")
        print("  where instruments enter at different times measures the entry schedule as")
        print("  much as the strategy. The test will use the window they all share.")
        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
