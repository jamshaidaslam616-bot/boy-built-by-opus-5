"""What can this account actually trade, and at what cost?

The arithmetic in F15 says the route to a provable, payable edge is more markets,
not a better gold rule. So the first question is what this broker offers, what each
one costs to hold, and — critically — whether the minimum position is small enough
to be a sensible slice of a $10,000 book.

That last check killed futures in F11 and it will kill instruments here too. A
market that cannot be sized down to its share of the risk budget is not in the
universe, however attractive it looks.

Read-only.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import MetaTrader5 as mt5  # noqa: E402

from goldlab.broker import mt5_read as br  # noqa: E402

CAPITAL = 10_000.0
# With N markets the risk budget splits N ways, so each slice is small. 20 markets
# at a 10% book volatility target means each carries roughly 10%/sqrt(20) of it.
ASSUMED_MARKETS = 20
BOOK_VOL_TARGET = 0.10
ASSUMED_ANNUAL_VOL = 0.15  # per-instrument, refined later from real data


def main() -> int:
    br.connect()
    try:
        acct = br.account()
        print("=" * 104)
        print(f"UNIVERSE DISCOVERY — account {acct.login} ({acct.trade_mode}), "
              f"{acct.currency}, leverage 1:{acct.leverage}")
        print("=" * 104)

        symbols = mt5.symbols_get()
        if symbols is None:
            raise br.BrokerReadError("symbols_get() returned None")
        print(f"  broker exposes {len(symbols):,} symbols")

        by_group: dict[str, list] = {}
        for s in symbols:
            root = s.path.split("\\")[1] if "\\" in s.path else "other"
            by_group.setdefault(root, []).append(s)

        print("\n  by group:")
        for group, members in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
            print(f"    {group:<22} {len(members):>5}")

        # Per-slice risk budget: what dollar volatility each market is allowed.
        slice_vol_usd = CAPITAL * BOOK_VOL_TARGET / (ASSUMED_MARKETS ** 0.5)
        print(f"\n  Sizing check: {ASSUMED_MARKETS} markets, {BOOK_VOL_TARGET:.0%} book vol")
        print(f"    -> each market may carry about ${slice_vol_usd:,.0f} of annual volatility")

        # Selecting a symbol only queues it; the terminal needs a moment to deliver a
        # first tick. Reading immediately after selecting silently skipped 293 of 314
        # symbols on the first attempt, which would have hidden most of the universe.
        print("\n  selecting all symbols into Market Watch ...", flush=True)
        for s in symbols:
            mt5.symbol_select(s.name, True)
        time.sleep(8.0)

        rows, unreadable, no_cross = [], 0, 0
        for s in symbols:
            name = s.name
            try:
                info = mt5.symbol_info(name)
                tick = mt5.symbol_info_tick(name)
                if info is None or tick is None or tick.bid <= 0 or info.trade_mode != 4:
                    unreadable += 1
                    continue

                mid = (tick.bid + tick.ask) / 2.0

                # Contract size is denominated in the BASE currency, so the conversion
                # to USD notional depends on which side of the pair the dollar is on.
                # Getting this wrong reported USDJPY as 106x oversized when it is in
                # fact one of the smallest positions available.
                if info.currency_profit == "USD":          # e.g. EURUSD, XAUUSD
                    min_notional = info.volume_min * info.trade_contract_size * mid
                elif info.currency_base == "USD":          # e.g. USDJPY, USDCHF
                    min_notional = info.volume_min * info.trade_contract_size
                else:                                       # e.g. EURGBP — needs a cross rate
                    no_cross += 1
                    continue

                point_value_usd = (min_notional / info.volume_min) * info.point / mid \
                    if info.currency_base == "USD" else info.point * info.trade_contract_size
                spread_bp = (info.spread * point_value_usd) / \
                            (min_notional / info.volume_min) * 10_000

                min_vol_usd = min_notional * ASSUMED_ANNUAL_VOL
                rows.append({
                    "symbol": name,
                    "group": s.path.split("\\")[1] if "\\" in s.path else "other",
                    "min_lot": info.volume_min,
                    "min_notional": min_notional,
                    "min_vol_usd": min_vol_usd,
                    "slices_needed": min_vol_usd / slice_vol_usd,
                    "spread_bp": spread_bp,
                    "swap_long_pts": info.swap_long,
                    "swap_short_pts": info.swap_short,
                    # Needed to turn swap POINTS into a percentage of notional. Omitting
                    # it understated every carry figure by orders of magnitude.
                    "point_value_usd_per_lot": point_value_usd,
                })
            except Exception:
                unreadable += 1
                continue

        print(f"  readable {len(rows):,} · unreadable {unreadable:,} · "
              f"skipped for needing a cross rate {no_cross:,}")

        df = pd.DataFrame(rows)
        if df.empty:
            print("\n  no tradeable symbols could be read")
            return 1

        sizeable = df[df["slices_needed"] <= 1.0]
        print(f"\n  {len(df):,} symbols readable · "
              f"**{len(sizeable):,} can be sized small enough** for a "
              f"{ASSUMED_MARKETS}-market book on ${CAPITAL:,.0f}")

        print("\n  Sizeable universe by group:")
        for group, grp in sizeable.groupby("group"):
            print(f"    {group:<22} {len(grp):>4}   "
                  f"median spread {grp['spread_bp'].median():>6.2f} bp")

        print("\n  Cheapest 25 sizeable markets by spread:")
        print(f"    {'symbol':<16} {'group':<16} {'min lot':>8} {'min notional':>13} "
              f"{'spread bp':>10} {'slices':>8}")
        cheap = sizeable.nsmallest(25, "spread_bp")
        for _, r in cheap.iterrows():
            print(f"    {r['symbol']:<16} {r['group']:<16} {r['min_lot']:>8.2f} "
                  f"{r['min_notional']:>13,.0f} {r['spread_bp']:>10.2f} "
                  f"{r['slices_needed']:>8.2f}")

        out = Path(__file__).resolve().parents[1] / "data" / "universe.parquet"
        df.to_parquet(out)
        print(f"\n  full table -> {out.name}  ({len(df):,} rows)")

        too_big = df[df["slices_needed"] > 1.0].nlargest(5, "slices_needed")
        if not too_big.empty:
            print("\n  Excluded for being unsizeable (same failure mode as futures in F11):")
            for _, r in too_big.iterrows():
                print(f"    {r['symbol']:<16} minimum position is "
                      f"{r['slices_needed']:.1f}x its risk slice")
        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
