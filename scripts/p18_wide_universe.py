"""Widen the cross-section — the one lever capital genuinely buys.

P17 established what each account size unlocks. The part worth paying for is not
that gold becomes holdable; it is that the book can get WIDER, and breadth is the
only remaining way to raise Sharpe without new data.

The 19-market universe was chosen by what fit in $10,000. With capital available,
the constraint moves and the broker offers instruments this project has never
touched:

  * **Industrial metals** — copper, aluminium, nickel, zinc, lead. Driven by
    construction and manufacturing demand, which is a different factor from the
    real-yield and dollar story that moves precious metals and FX.
  * **Emerging-market currencies** — MXN, ZAR, PLN, CNH, SGD. Different rate cycles
    and different risk-appetite betas from the majors.
  * **US30** — a third index with a different sector mix.

Pegged pairs (HKD, DKK) are excluded deliberately: a currency that does not move
contributes no diversification and only noise to a ranking.

This is a genuine widening of the cross-section, not another parameter.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.broker import mt5_read as br  # noqa: E402
from goldlab.data import history as hist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
START = datetime(2010, 1, 1, tzinfo=timezone.utc)

NEW = {
    "Industrial metals": ["XCUUSD", "XALUSD", "XNIUSD", "XZNUSD", "XPBUSD"],
    "EM currencies": ["USDMXN", "USDZAR", "USDPLN", "USDCNH", "USDSGD"],
    "Index": ["US30"],
}

# Excluded on purpose, with the reason recorded so it is not revisited by accident.
EXCLUDED = {
    "USDHKD": "pegged to USD — no volatility, contributes only noise to a ranking",
    "USDDKK": "pegged to EUR — duplicates EURUSD with worse costs",
    "USDTHB": "thin and heavily managed; minimum position is 22x its risk slice (P10)",
    "DXY": "a basket of pairs already in the universe — double counts the dollar factor",
    "US30_x10": "leveraged wrapper of US30; same exposure, coarser minimum",
    "US500_x100": "leveraged wrapper of US500",
    "USTEC_x100": "leveraged wrapper of USTEC",
}


def main() -> int:
    br.connect()
    try:
        print("=" * 92)
        print("P18 — WIDENING THE CROSS-SECTION")
        print("=" * 92)
        print("\n  Excluded before fetching, with reasons:")
        for symbol, why in EXCLUDED.items():
            print(f"    {symbol:<12} {why}")

        added, failed = [], []
        for group, symbols in NEW.items():
            print(f"\n  {group}")
            for symbol in symbols:
                try:
                    df = hist.fetch(symbol, "D1", START)
                except Exception as exc:
                    print(f"    {symbol:<10} FAILED ({type(exc).__name__})")
                    failed.append(symbol)
                    continue

                rep = hist.quality_gate(df, symbol, "D1")
                hist.save(df, ROOT, symbol, "D1")
                years = (df.index[-1] - df.index[0]).days / 365.25
                vol = float(df["close"].pct_change().std() * np.sqrt(260))

                # A market that barely moves cannot diversify anything.
                verdict = "OK"
                if years < 4:
                    verdict = "SHORT HISTORY"
                elif vol < 0.02:
                    verdict = f"TOO QUIET ({vol:.1%}) — likely pegged"
                else:
                    added.append(symbol)

                print(f"    {symbol:<10} {len(df):>6,} bars  {years:>5.1f}y  "
                      f"vol {vol:>6.1%}  {verdict}")

        print("\n" + "=" * 92)
        print(f"  added {len(added)} · failed {len(failed)}")
        if failed:
            print(f"  failed: {failed}")
        print(f"\n  universe grows from 19 to {19 + len(added)} instruments")
        print("  Run scripts/p19_wide_book.py to test whether the wider cross-section")
        print("  actually ranks better, or merely ranks more things.")

        (ROOT / "universe_added.txt").write_text("\n".join(added), encoding="utf-8")
        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
