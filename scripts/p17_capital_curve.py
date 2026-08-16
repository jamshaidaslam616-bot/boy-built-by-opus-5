"""How much capital does the bot actually need, and what does each level buy?

The owner has said capital is available and that quality must not be compromised.
So the question is no longer "what fits in $10,000" but "what is the right size for
this design" — and that has a measurable answer.

Two separate things scale with capital, and only one of them is worth paying for:

  * **Implementability.** F18 measured that the high-volatility markets — which is
    to say most of the ones carrying any signal — cannot be held at all on $10,000,
    because the broker's minimum position is larger than the leg's entire risk
    budget. More capital fixes this outright.

  * **Universe breadth.** As capital rises, more instruments clear their minimum,
    the book can hold more legs, and a wider cross-section makes the ranking less
    noisy. This is the one lever that raises Sharpe without new data.

What capital does NOT buy is an edge. P15's control z was +0.56 against a +2.00
bar; multiplying the account multiplies both sides of that. This script quantifies
the first two and says nothing about the third.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.strategy import production as prod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
BARS_PER_YEAR = 260.0
BOOK_VOL_TARGET = 0.07

CAPITALS = (10_000, 20_000, 30_000, 50_000, 75_000, 100_000, 150_000, 250_000)


def annual_vol(symbol: str) -> float | None:
    try:
        close = hist.load(ROOT, symbol, "D1")["close"]
    except FileNotFoundError:
        return None
    v = close.pct_change().rolling(prod.VOL_LOOKBACK_BARS).std().dropna()
    return float(v.iloc[-1] * np.sqrt(BARS_PER_YEAR)) if len(v) else None


def main() -> int:
    spec = pd.read_parquet(ROOT / "universe.parquet").set_index("symbol")

    print("=" * 96)
    print("P17 — THE CAPITAL CURVE: what each account size actually unlocks")
    print("=" * 96)
    print(f"  Book volatility target {BOOK_VOL_TARGET:.0%}. A leg in an N-leg book carries")
    print("  roughly 1/sqrt(N) of the book's volatility, so the required notional per leg")
    print("  falls as the book widens — which is why breadth and capital interact.")

    # Volatility for everything we have history for.
    vols = {}
    for s in prod.UNIVERSE:
        v = annual_vol(s)
        if v and v > 0:
            vols[s] = v

    print(f"\n  {'capital':>10} {'legs':>6} {'$vol/leg':>10} {'tradeable':>11}  blocked")
    print("  " + "-" * 88)

    curve = []
    for capital in CAPITALS:
        # Solve for the widest book this capital supports: try each leg count and
        # keep the largest that still has enough tradeable markets to fill it.
        best = None
        for n_legs in range(4, len(vols) + 1, 2):
            leg_vol_usd = capital * BOOK_VOL_TARGET / np.sqrt(n_legs)
            ok = []
            for s, v in vols.items():
                needed = leg_vol_usd / v
                row = spec.loc[s]
                per_lot = float(row["min_notional"]) / float(row["min_lot"])
                if needed / per_lot >= float(row["min_lot"]):
                    ok.append(s)
            if len(ok) >= n_legs:
                best = (n_legs, leg_vol_usd, ok)
        if best is None:
            print(f"  {capital:>10,} {'--':>6}   no book of any width is possible")
            continue

        n_legs, leg_vol_usd, ok = best
        blocked = [s for s in vols if s not in ok]
        curve.append({"capital": capital, "legs": n_legs, "tradeable": len(ok)})
        blocked_str = ", ".join(blocked[:5]) + (f" +{len(blocked) - 5}" if len(blocked) > 5 else "")
        print(f"  {capital:>10,} {n_legs:>6} {leg_vol_usd:>10,.0f} "
              f"{len(ok):>4}/{len(vols):<6} {blocked_str if blocked else 'none'}")

    print("\n" + "=" * 96)
    print("  THE THRESHOLDS THAT MATTER")
    print("=" * 96)

    full = next((c for c in curve if c["tradeable"] == len(vols)), None)
    if full:
        print(f"    Every one of the {len(vols)} instruments becomes tradeable at "
              f"**${full['capital']:,}**.")
    for s in ("XAUUSD", "XAGUSD", "BTCUSD", "USOIL"):
        if s not in vols:
            continue
        row = spec.loc[s]
        per_lot = float(row["min_notional"]) / float(row["min_lot"])
        min_notional = float(row["min_lot"]) * per_lot
        # capital such that leg_vol_usd / vol >= min_notional, at the 14-leg width
        needed_capital = min_notional * vols[s] * np.sqrt(14) / BOOK_VOL_TARGET
        print(f"    {s:<8} needs about ${needed_capital:>9,.0f} before it can be one leg "
              f"of a 14-leg book")

    print()
    print("    These are hard arithmetic, not preference. Below them the position simply")
    print("    cannot be expressed, which is what made the $10,000 backtest fictional.")

    print("\n" + "=" * 96)
    print("  WHAT CAPITAL DOES NOT BUY")
    print("=" * 96)
    print(f"    The strategy's control z is +{prod.MEASURED['control_z']:.2f} against a "
          f"+{prod.MEASURED['control_bar']:.2f} bar. That is a statement about whether the")
    print("    signal is distinguishable from luck, and it does not improve with account")
    print("    size — a larger account simply makes both outcomes larger.")
    print()
    print("    The one thing capital genuinely buys beyond implementability is BREADTH,")
    print("    and breadth is the only lever left that raises Sharpe without new data.")
    print("    That is worth pursuing and is the next piece of work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
