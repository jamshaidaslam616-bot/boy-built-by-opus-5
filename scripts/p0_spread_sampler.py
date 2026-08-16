"""Sample the live spread over time, so P0 gets a DISTRIBUTION, not one reading.

A single spread reading is nearly worthless. What a cost model needs is how the
spread behaves by hour: what it is during the London/NY overlap, what it does at
the 21:00 rollover, and how fat the tail is. That decides whether a session filter
is worth having and what the honest cost assumption should be.

Two rules this obeys:

  * **Never record a closed-market quote.** The archive already contains 32% of D1
    bars with a spread of zero, which would make those trades free. A frozen
    Friday print is the same lie in real time, so stale ticks are skipped and
    counted, not stored.
  * **Flush incrementally.** A long run that dies at hour 19 must still leave 19
    hours of usable data behind.

Read-only. Sends no orders.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.broker import mt5_read as br  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "spread_samples.parquet"
SYMBOLS = ("XAUUSD", "XAGUSD")


def flush(rows: list[dict], path: Path) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    if path.exists():
        df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
    df = df.drop_duplicates(subset=["symbol", "tick_utc"]).sort_values("tick_utc")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return len(df)


def summarise(path: Path) -> None:
    if not path.exists():
        print("  no samples collected")
        return
    df = pd.read_parquet(path)
    print(f"\n  {len(df):,} live samples, "
          f"{df['tick_utc'].min():%Y-%m-%d %H:%M} .. {df['tick_utc'].max():%Y-%m-%d %H:%M} UTC")

    for symbol, grp in df.groupby("symbol"):
        print(f"\n  {symbol}  ({len(grp):,} samples)")
        pts = grp["spread_points"]
        print(f"    points  median {pts.median():6.1f}   mean {pts.mean():6.1f}   "
              f"p95 {pts.quantile(0.95):6.1f}   p99 {pts.quantile(0.99):6.1f}   max {pts.max():6.1f}")
        print(f"    bp      median {grp['spread_bp'].median():6.3f}   "
              f"p95 {grp['spread_bp'].quantile(0.95):6.3f}")
        zeros = int((pts == 0).sum())
        if zeros:
            print(f"    *** {zeros} LIVE samples recorded a spread of zero — investigate ***")

        by_hour = grp.groupby(grp["tick_utc"].dt.hour)["spread_points"].agg(["median", "count"])
        print("    by hour UTC (median points / samples):")
        line = "      "
        for hour, row in by_hour.iterrows():
            line += f"{hour:02d}h:{row['median']:.0f}({int(row['count'])})  "
            if len(line) > 100:
                print(line)
                line = "      "
        if line.strip():
            print(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=20.0, help="how long to sample for")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    ap.add_argument("--flush-every", type=int, default=60, help="samples between disk flushes")
    args = ap.parse_args()

    deadline = datetime.now(timezone.utc) + timedelta(hours=args.hours)
    br.connect()

    pending: list[dict] = []
    live = stale = 0
    try:
        print(f"sampling until {deadline:%Y-%m-%d %H:%M} UTC, every {args.interval:.0f}s",
              flush=True)
        while datetime.now(timezone.utc) < deadline:
            for symbol in SYMBOLS:
                try:
                    fs = br.feed_state(symbol)
                    if not fs.is_live:
                        stale += 1
                        continue
                    c = br.symbol_costs(symbol)
                    pending.append({
                        "symbol": c.symbol,
                        "tick_utc": fs.last_tick_utc,
                        "bid": c.bid,
                        "ask": c.ask,
                        "spread_points": c.spread_current_points,
                        "spread_cost_per_lot": c.spread_cost_per_lot,
                        "spread_bp": c.spread_cost_per_lot / c.notional_per_lot * 10_000.0,
                        "notional_per_lot": c.notional_per_lot,
                    })
                    live += 1
                except br.BrokerReadError:
                    stale += 1

            if len(pending) >= args.flush_every:
                total = flush(pending, OUT)
                print(f"  {datetime.now(timezone.utc):%H:%M:%S} flushed, {total:,} stored "
                      f"(live {live}, skipped-stale {stale})", flush=True)
                pending = []

            time.sleep(args.interval)

        flush(pending, OUT)
        print(f"\ndone. live samples {live}, skipped as stale/closed {stale}")
        summarise(OUT)
        return 0
    except KeyboardInterrupt:
        flush(pending, OUT)
        print(f"\ninterrupted; partial data kept. live {live}, stale {stale}")
        summarise(OUT)
        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
