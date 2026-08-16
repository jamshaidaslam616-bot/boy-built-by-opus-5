"""Recover the real commission from deals the account has ALREADY done.

MT5 does not expose commission on ``symbol_info``, ``order_check`` or
``order_calc_profit`` — but it does record the exact figure the server charged on
every historical deal. If this account has ever traded gold, the number we need is
already sitting in its history and no new order has to be sent to find it.

Read-only. Sends nothing.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import MetaTrader5 as mt5  # noqa: E402

from goldlab.broker import mt5_read as br  # noqa: E402

LOOKBACK_DAYS = 3650

# DEAL_ENTRY_IN = 0 (opening), OUT = 1 (closing), INOUT = 2 (reversal)
ENTRY_NAMES = {0: "open", 1: "close", 2: "reverse", 3: "out_by"}


def main() -> int:
    br.connect()
    try:
        acct = br.account()
        print("=" * 90)
        print(f"COMMISSION FROM DEAL HISTORY — account {acct.login} ({acct.trade_mode})")
        print("=" * 90)

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=LOOKBACK_DAYS)
        deals = mt5.history_deals_get(start, end)

        if deals is None or len(deals) == 0:
            code, desc = mt5.last_error()
            print(f"  No deals in the last {LOOKBACK_DAYS} days ({code}: {desc}).")
            print("  Nothing to measure from. The commission must come from you, or from")
            print("  an authorised 0.01-lot demo fill.")
            return 1

        print(f"  {len(deals):,} deals found in the last {LOOKBACK_DAYS} days\n")

        # Group by symbol so we never apply one instrument's rate card to another —
        # commission on this account type differs per instrument.
        by_symbol: dict[str, list] = defaultdict(list)
        for d in deals:
            if d.symbol and d.volume > 0:
                by_symbol[d.symbol].append(d)

        found_gold = False
        for symbol in sorted(by_symbol):
            rows = by_symbol[symbol]
            charged = [d for d in rows if d.commission != 0.0]
            print(f"  {symbol:<12} {len(rows):>4} deals, {len(charged):>4} with a commission line")

            if not charged:
                print(f"               -> commission recorded as 0.00 on every deal")
                continue

            per_lot = defaultdict(list)
            for d in charged:
                per_lot[ENTRY_NAMES.get(d.entry, str(d.entry))].append(
                    abs(d.commission) / d.volume
                )

            for side, values in sorted(per_lot.items()):
                lo, hi = min(values), max(values)
                spread_note = "" if abs(hi - lo) < 1e-6 else f"  (range {lo:.4f}..{hi:.4f})"
                print(f"               -> on {side:<8} ${sum(values)/len(values):.4f} per lot"
                      f"   n={len(values)}{spread_note}")

            if symbol.upper().startswith("XAU"):
                found_gold = True
                opens = per_lot.get("open", [])
                closes = per_lot.get("close", [])
                print()
                print(f"  *** {symbol} COMMISSION, MEASURED FROM REAL FILLS ***")
                if opens:
                    print(f"      open  : ${sum(opens)/len(opens):.4f} per lot")
                if closes:
                    print(f"      close : ${sum(closes)/len(closes):.4f} per lot")
                rt = (sum(opens) / len(opens) if opens else 0.0) + (
                    sum(closes) / len(closes) if closes else 0.0
                )
                print(f"      ROUND TURN: ${rt:.4f} per lot")
                if closes and sum(closes) == 0:
                    print("      Charged wholly on OPEN — nothing on close. Do NOT assume a")
                    print("      per-side shape without checking; it differs by instrument.")
                print()

        if not found_gold:
            print()
            print("  No gold deals in this history, so the gold commission is still unmeasured.")
            print("  It cannot be inferred from another instrument — on this account type the")
            print("  rate differs per symbol (a previous measurement found BTCUSD charged")
            print("  wholly on open, unlike gold's assumed per-side shape).")
            return 1

        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
