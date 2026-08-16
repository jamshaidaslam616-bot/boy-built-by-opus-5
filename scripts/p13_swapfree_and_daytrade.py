"""Two owner-proposed fixes, both tested properly: swap-free, and day trading.

The owner correctly identified that financing is the blocker and proposed the two
obvious ways round it:

  1. **A swap-free (Islamic) account** — no overnight charge at all.
  2. **Day trading** — flat before the rollover, so no overnight charge applies.

Both deserve a real test rather than an opinion. They are not the same thing:
swap-free keeps the strategy exactly as it is and removes a cost; day trading
changes the strategy and adds a different cost (many more round trips, and this
account charges $11/lot on every open).

The honest question for each is not "is it cheaper" but "does what remains have an
edge". Test 1 answers that for free, because it is the same positions with the
carry switched off.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.metrics import summarise  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns, turnover, vol_target  # noqa: E402
from goldlab.research.sizing import bootstrap_max_drawdowns  # noqa: E402
from goldlab.strategy import candidates as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
LIVE_HALT = 20.0
SPEEDS = (20, 50, 100, 200, 400)

SYMS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
        "USDNOK", "USDSEK", "XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD",
        "USOIL", "UKOIL", "US500", "USTEC", "BTCUSD", "ETHUSD"]


def carry_for(symbol: str, swaps: pd.DataFrame) -> tuple[float, float]:
    if symbol not in swaps.index:
        return 0.0, 0.0
    r = swaps.loc[symbol]
    scale = r["point_value_usd_per_lot"] * 469.0 / (r["min_notional"] / r["min_lot"]) * 100.0
    return (float(np.clip(r["swap_long_pts"] * scale, -40, 40)),
            float(np.clip(r["swap_short_pts"] * scale, -40, 40)))


def model(carry_long: float, carry_short: float, commission_bp: float = 0.25) -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=commission_bp, slippage_bp=0.10,
        carry_long_annual_pct=carry_long, carry_short_annual_pct=carry_short,
        bars_per_year=BARS_PER_YEAR,
    )


def book_stats(streams: dict[str, pd.Series]) -> tuple[float, float, float]:
    frame = pd.DataFrame(streams).dropna(how="all")
    frame = frame.loc[frame.notna().all(axis=1)]
    book = frame.mean(axis=1)
    perf = summarise(book, BARS_PER_YEAR)
    p95 = float(np.percentile(bootstrap_max_drawdowns(book, n_paths=400), 95))
    scaled = perf.ann_return_pct * (LIVE_HALT / p95) if p95 > 0 else 0.0
    return perf.sharpe, scaled, CAPITAL * scaled / 100.0


def main() -> int:
    swaps = pd.read_parquet(ROOT / "universe.parquet").set_index("symbol")

    print("=" * 96)
    print("TEST 1 — SWAP-FREE: the same positions, carry switched off")
    print("=" * 96)

    scenarios = {}
    for label, zero_carry in (("as measured (swap charged)", False), ("SWAP-FREE", True)):
        streams, singles = {}, {}
        for s in SYMS:
            close = hist.load(ROOT, s, "D1")["close"]
            raw = sum(C.a1_timeseries_momentum(close, n) for n in SPEEDS) / len(SPEEDS)
            pos = vol_target(raw, close, 0.10, 60, BARS_PER_YEAR)
            cl, cs = (0.0, 0.0) if zero_carry else carry_for(s, swaps)
            net = strategy_returns(pos, close, model(cl, cs))
            streams[s] = net
            singles[s] = summarise(net, BARS_PER_YEAR).sharpe
        sharpe, ret, usd = book_stats(streams)
        scenarios[label] = (np.mean(list(singles.values())), sharpe, ret, usd, singles)
        print(f"\n  {label}")
        print(f"    mean single-market Sharpe {np.mean(list(singles.values())):+.3f}   "
              f"positive on {sum(v > 0 for v in singles.values())}/{len(singles)} markets")
        print(f"    portfolio Sharpe          {sharpe:+.3f}")
        print(f"    at a compliant size       {ret:+.2f}%/yr = ${usd:+,.0f} on ${CAPITAL:,.0f}")

    a, b = scenarios["as measured (swap charged)"], scenarios["SWAP-FREE"]
    print(f"\n  Removing the swap moves the portfolio Sharpe {a[1]:+.3f} -> {b[1]:+.3f}")
    print(f"  and the yearly figure ${a[3]:+,.0f} -> ${b[3]:+,.0f}.")

    print("\n  Per-market, swap-free:")
    ranked = sorted(b[4].items(), key=lambda kv: -kv[1])
    for i in range(0, len(ranked), 5):
        print("    " + "  ".join(f"{s}:{v:+.2f}" for s, v in ranked[i:i + 5]))

    # -------------------------------------------------------------- day trading
    print("\n" + "=" * 96)
    print("TEST 2 — DAY TRADING: flat every night, so no swap can apply")
    print("=" * 96)
    print("  Gold only, because it needs intraday bars and H1 is the deepest we hold.")

    h1 = hist.load(ROOT, "XAUUSD", "H1")
    h1 = h1.loc[h1.index >= "2017-01-01"]
    close_h1 = h1["close"]
    bpy_h1 = 24 * 260.0

    # How much of gold's move actually happens while a day trader is flat?
    daily = close_h1.resample("D").agg(["first", "last"]).dropna()
    intraday = (daily["last"] / daily["first"] - 1.0)
    overnight = (daily["first"] / daily["last"].shift(1) - 1.0).dropna()
    print(f"\n    total move, intraday only : {(1 + intraday).prod() ** (260 / len(intraday)) - 1:+.2%}/yr")
    print(f"    total move, overnight only: {(1 + overnight).prod() ** (260 / len(overnight)) - 1:+.2%}/yr")
    print("    A day trader keeps the first line and forfeits the second, whichever way")
    print("    the strategy is pointing.")

    # The same trend rule, forced flat before the 21:00 rollover.
    raw = sum(C.a1_timeseries_momentum(close_h1, n) for n in (6, 12, 24, 48)) / 4
    hour = close_h1.index.hour
    flat_overnight = raw.copy()
    flat_overnight[(hour >= 20) | (hour < 1)] = 0.0

    print(f"\n    {'variant':<28} {'Sharpe':>8} {'return':>9} {'turnover':>10} {'swap paid':>11}")
    print("    " + "-" * 70)
    cl, cs = carry_for("XAUUSD", swaps)
    for label, pos_raw, carry in (
        ("hold overnight (swap on)", raw, (cl, cs)),
        ("hold overnight (swap-free)", raw, (0.0, 0.0)),
        ("day trade, flat at night", flat_overnight, (cl, cs)),
    ):
        pos = vol_target(pos_raw, close_h1, 0.10, 240, bpy_h1)
        cm = CostModel(spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
                       carry_long_annual_pct=carry[0], carry_short_annual_pct=carry[1],
                       bars_per_year=bpy_h1)
        perf = summarise(strategy_returns(pos, close_h1, cm), bpy_h1, turnover(pos))
        exposure = float((pos != 0).mean())
        swap_cost = abs(carry[0]) * exposure
        print(f"    {label:<28} {perf.sharpe:>+8.3f} {perf.ann_return_pct:>+8.2f}% "
              f"{perf.turnover_per_year:>10.0f} {swap_cost:>10.2f}%")

    print("\n    Day trading removes the swap and pays for it in turnover: every night flat")
    print("    means a fresh open the next morning, and this account charges $11/lot on")
    print("    every open regardless of how long the trade lasts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
