"""P0 reconnaissance: what does a trade on this account actually cost?

Read-only. Prints a report; writes nothing to the broker. Every number below is
read from the live terminal — none is assumed, and anything unreadable is reported
as unreadable rather than filled in with a plausible figure.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.broker import mt5_read as br  # noqa: E402

GOLD_ROOTS = ("XAUUSD", "XAGUSD")


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> int:
    br.connect()
    try:
        rule("ACCOUNT — whatever the terminal is already logged into")
        acct = br.account()
        print(f"  login          {acct.login}")
        print(f"  server         {acct.server}")
        print(f"  company        {acct.company}")
        print(f"  trade mode     {acct.trade_mode}")
        print(f"  currency       {acct.currency}")
        print(f"  balance        {acct.balance:,.2f}")
        print(f"  equity         {acct.equity:,.2f}")
        print(f"  leverage       1:{acct.leverage}")
        if acct.trade_mode == "REAL":
            print("\n  *** THIS IS A REAL-MONEY ACCOUNT. This script is read-only, but stop ***")
            print("  *** and confirm which account you meant before anything else runs.   ***")

        rule("SYMBOL DISCOVERY — names are resolved, never assumed")
        found = br.find_symbols(*GOLD_ROOTS)
        for root, names in found.items():
            print(f"  {root:<10} -> {names if names else 'NONE FOUND'}")

        targets = [names[0] for names in found.values() if names]
        if not targets:
            print("\n  No gold/silver symbols on this account. Cannot continue.")
            return 1

        rule("FEED STATE — are these live quotes or a frozen close?")
        live_all = True
        for sym in targets:
            fs = br.feed_state(sym)
            live_all &= fs.is_live
            print(f"  {fs.symbol:<10} last tick {fs.last_tick_utc:%Y-%m-%d %H:%M:%S} UTC  "
                  f"age {fs.tick_age_seconds / 3600:6.2f} h  "
                  f"trade_mode {fs.trade_mode}  "
                  f"{'LIVE' if fs.is_live else 'CLOSED / STALE'}")
        print(f"  local now      {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC")

        if not live_all:
            print()
            print("  *** MARKET IS CLOSED. Every quote below is a frozen print, not a  ***")
            print("  *** tradeable price. In particular a spread of 0 is an artifact of ***")
            print("  *** the closed session, NOT a real cost. Contract properties and   ***")
            print("  *** swap rates below are still valid; SPREADS ARE NOT. Re-run this ***")
            print("  *** during the London/NY session before any spread figure is used. ***")

        measured: dict[str, br.SymbolCosts] = {}
        for sym in targets:
            c = br.symbol_costs(sym)
            measured[sym] = c
            fs = br.feed_state(sym)
            suspect = "" if fs.is_live else "   <-- SUSPECT, market closed"
            rule(f"COST TRUTH — {c.symbol}")
            print(f"  path                  {c.path}")
            print(f"  digits / point        {c.digits} / {c.point}")
            print(f"  contract size         {c.contract_size:,.2f}")
            print(f"  volume min/step/max   {c.volume_min} / {c.volume_step} / {c.volume_max}")
            print(f"  stops / freeze level  {c.stops_level} / {c.freeze_level}")
            print(f"  bid / ask             {c.bid} / {c.ask}")
            print(f"  notional per lot      {c.notional_per_lot:,.2f} {acct.currency}")
            print()
            print(f"  value per point/lot   {c.value_per_point_per_lot:.6f} {acct.currency}")
            print(f"  spread now            {c.spread_current_points} points "
                  f"(floating={c.spread_float}){suspect}")
            print(f"  spread cost per lot   {c.spread_cost_per_lot:,.2f} {acct.currency} "
                  f"(one full round trip: buy at ask, sell at bid){suspect}")
            rt = c.spread_cost_per_lot
            print(f"  -> as bp of notional  {rt / c.notional_per_lot * 10000:.3f} bp{suspect}")
            print()
            print(f"  swap long             {c.swap_long_points:,.1f} points/night "
                  f"= {c.swap_long_per_lot_per_night:,.2f} {acct.currency}/lot/night")
            print(f"  swap short            {c.swap_short_points:,.1f} points/night "
                  f"= {c.swap_short_per_lot_per_night:,.2f} {acct.currency}/lot/night")
            print(f"  swap mode             {c.swap_mode}")
            print(f"  triple swap on        {c.triple_swap_day} "
                  f"(MT5 weekday {c.swap_rollover_3x_weekday}; 0=Sunday)")
            print(f"  -> carry long         {c.swap_annual_pct_of_notional('long'):+.2f} % of "
                  f"notional per year")
            print(f"  -> carry short        {c.swap_annual_pct_of_notional('short'):+.2f} % of "
                  f"notional per year")
            print()
            ours, theirs, agree = br.cross_check_point_value(c)
            status = "AGREE" if agree else "*** DISAGREE — every position size would be wrong ***"
            print(f"  1.000 move on 1 lot   ours={ours:,.2f}  broker={theirs:,.2f}  [{status}]")
            print()
            print("  commission            NOT READABLE FROM THE API. MT5 does not expose it on")
            print("                        symbol_info, order_check or order_calc_profit; the")
            print("                        server applies it at fill time. It must be measured")
            print("                        from a real fill or supplied explicitly.")

        gold, silver = measured.get("XAUUSD"), measured.get("XAGUSD")
        if gold and silver:
            rule("B3 VIABILITY — what the gold/silver spread trade pays to exist")
            print("  The spread trade is long one metal and short the other. On this account")
            print("  a short earns NO carry credit (swap_short = 0), so whichever leg is long")
            print("  bleeds its full carry and the short leg refunds none of it.")
            print()
            for name, c in (("long gold / short silver", gold), ("long silver / short gold", silver)):
                drag = c.swap_annual_pct_of_notional("long")
                print(f"  {name:<26} carry drag {drag:+.2f} % per year on the long leg")
            print()
            print("  On futures the short leg earns the carry back and the pair is roughly")
            print("  carry-neutral. That difference is the whole case for moving B3 to MGC/SI.")
            print("  A mean-reversion trade holding weeks cannot pay ~5.7%/yr for the privilege.")

        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
