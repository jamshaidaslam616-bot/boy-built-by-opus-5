"""Fetch CFTC COT positioning for gold and silver, and measure it honestly.

Same two-column treatment as the macro series (FINDINGS F5): what the relationship
looks like on the report date, and what it looks like using only what had actually
been released. If a signal only exists in the first column it is not a signal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import cot  # noqa: E402
from goldlab.data import history as hist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
YEARS = range(2011, 2027)  # 2011 start gives a full 3-year window before 2014 gold data


def main() -> int:
    gold_px = hist.load(ROOT, "XAUUSD", "D1")["close"]
    weekly_fwd = gold_px.resample("W-TUE").last().pct_change().shift(-1)  # next week's return

    print("=" * 96)
    print("P2 — CFTC COMMITMENTS OF TRADERS")
    print("=" * 96)

    for label, code in (("GOLD", cot.GOLD_CONTRACT_CODE), ("SILVER", cot.SILVER_CONTRACT_CODE)):
        print(f"\nfetching {label} ({code}) ...")
        series = cot.fetch(code, YEARS)
        df = series.frame

        print(f"\n  {label}: {len(df):,} weekly reports, "
              f"{df.index[0]:%Y-%m-%d} .. {df.index[-1]:%Y-%m-%d}")
        print(f"    open interest      {df['open_interest'].iloc[-1]:,.0f} contracts")
        print(f"    managed money net  {df['managed_money_net'].iloc[-1]:+,.0f} "
              f"({df['managed_money_net_pct_oi'].iloc[-1]:+.1f}% of OI)")
        print(f"    producer net       {df['producer_net'].iloc[-1]:+,.0f} "
              f"({df['producer_net_pct_oi'].iloc[-1]:+.1f}% of OI)")

        mm_index = cot.cot_index(df["managed_money_net_pct_oi"])
        latest = mm_index.dropna()
        if len(latest):
            print(f"    managed money COT index (3y) {latest.iloc[-1]:.3f}  "
                  f"[0 = most short in 3y, 1 = most long]")

        path = ROOT / f"cot_{label.lower()}.parquet"
        df.assign(managed_money_cot_index=mm_index).to_parquet(path)
        print(f"    cached -> {path.name}")

        if label != "GOLD":
            continue

        # Does positioning predict the FOLLOWING week's gold return?
        print("\n  Does gold positioning predict next week's gold return?")
        print(f"    {'measure':<34} {'ON REPORT DATE':>16} {'AS PUBLISHED':>16}")
        print("    " + "-" * 68)

        for name, raw in (
            ("managed money net (% of OI)", df["managed_money_net_pct_oi"]),
            ("managed money COT index (3y)", mm_index),
            ("producer net (% of OI)", df["producer_net_pct_oi"]),
        ):
            on_report = pd.concat(
                [raw.rename("x"), weekly_fwd.rename("y")], axis=1, join="inner"
            ).dropna()
            r_report = on_report["x"].corr(on_report["y"])

            published = series.as_known_on(weekly_fwd.index, columns=list(df.columns))
            pub_x = (
                cot.cot_index(published["managed_money_net_pct_oi"])
                if "COT index" in name
                else published[
                    "managed_money_net_pct_oi" if "managed money" in name else "producer_net_pct_oi"
                ]
            )
            as_pub = pd.concat(
                [pub_x.rename("x"), weekly_fwd.rename("y")], axis=1
            ).dropna()
            r_pub = as_pub["x"].corr(as_pub["y"])

            print(f"    {name:<34} {r_report:>+15.4f} {r_pub:>+15.4f}   "
                  f"(n={len(on_report):,}/{len(as_pub):,})")

        print("\n  Both columns forecast a FUTURE week, so unlike F5 neither is contemporaneous.")
        print("  A gap between them would mean the 3-day reporting delay carries the signal,")
        print("  which would make it untradeable. Similar values mean the measure is real")
        print("  either way — and small values mean it is weak either way.")
        print("  Contrarian theory expects a NEGATIVE sign: crowded longs precede weakness.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
