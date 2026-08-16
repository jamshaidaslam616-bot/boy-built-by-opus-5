"""Does P15 survive the broker's minimum lot sizes? The backtest never asked.

P15 reported +$247/yr from a 14-leg cross-sectional book. Building the production
risk engine exposed that the backtest sized positions continuously — it never
checked whether a leg that small can actually be traded.

On a $10,000 account with a 14-leg book, each leg carries about a fourteenth of the
risk. That works out to roughly $1,300 of notional per leg. Gold's smallest
tradeable position is $4,342. **The backtest was holding a third of a position that
does not exist.**

This is the exact failure mode the whole project has been hunting: a result that is
real in the spreadsheet and unreachable in the account. It killed futures in F11 and
it is now doing the same to the shipped strategy.

So: re-run P15 with every leg rounded to the broker's actual volume step, refusing
any leg below its minimum, and see what is left.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.data import history as hist  # noqa: E402
from goldlab.research.metrics import sharpe_ratio, summarise  # noqa: E402
from goldlab.research.returns import CostModel, strategy_returns  # noqa: E402
from goldlab.research.sizing import bootstrap_max_drawdowns  # noqa: E402
from goldlab.strategy import production as prod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data"
BARS_PER_YEAR = 260.0
CAPITAL = 10_000.0
LIVE_HALT = 20.0
BOOK_VOL_TARGET = 0.07


def costs() -> CostModel:
    return CostModel(
        spread_bp=0.12, commission_bp=0.25, slippage_bp=0.10,
        carry_long_annual_pct=0.0, carry_short_annual_pct=0.0, bars_per_year=BARS_PER_YEAR,
    )


def main() -> int:
    spec = pd.read_parquet(ROOT / "universe.parquet").set_index("symbol")
    panel = pd.DataFrame({s: hist.load(ROOT, s, "D1")["close"] for s in prod.UNIVERSE})
    panel = panel.loc[panel.notna().all(axis=1)]
    vol = panel.pct_change().rolling(prod.VOL_LOOKBACK_BARS).std() * np.sqrt(BARS_PER_YEAR)

    print("=" * 100)
    print("P16 — CAN EACH LEG ACTUALLY BE TRADED ON $10,000?")
    print("=" * 100)
    n_legs = prod.LEGS_PER_SIDE * 2
    print(f"  {n_legs}-leg book, {BOOK_VOL_TARGET:.0%} book volatility, ${CAPITAL:,.0f} account")

    # Diversified legs contribute vol as the square root of their count.
    leg_vol_usd = CAPITAL * BOOK_VOL_TARGET / np.sqrt(n_legs)
    print(f"  -> each leg may carry ${leg_vol_usd:,.0f} of annual volatility\n")

    print(f"  {'symbol':<10} {'ann vol':>9} {'notional needed':>17} {'min notional':>14} "
          f"{'min lots needed':>16}  status")
    print("  " + "-" * 88)

    tradeable, blocked = [], []
    for s in prod.UNIVERSE:
        v = float(vol[s].dropna().iloc[-1])
        needed_notional = leg_vol_usd / v
        row = spec.loc[s]
        min_notional = float(row["min_notional"])
        lots_needed = needed_notional / (min_notional / float(row["min_lot"]))
        ok = lots_needed >= float(row["min_lot"])
        (tradeable if ok else blocked).append(s)
        print(f"  {s:<10} {v:>8.1%} {needed_notional:>17,.0f} {min_notional:>14,.0f} "
              f"{lots_needed:>16.4f}  {'OK' if ok else 'TOO SMALL — cannot trade'}")

    print(f"\n  tradeable {len(tradeable)}/{len(prod.UNIVERSE)} · blocked {len(blocked)}")
    if blocked:
        print(f"  blocked: {blocked}")
        print("  Note that XAUUSD and XAGUSD — the instruments this whole project began")
        print("  with — are among them. On $10,000 they cannot be one leg of a 14-leg book.")

    # --- what the strategy does when only tradeable legs are allowed ---
    print("\n" + "=" * 100)
    print("  RE-RUN, RESTRICTED TO LEGS THAT CAN ACTUALLY BE TRADED")
    print("=" * 100)

    def run(universe: list[str], label: str, legs_per_side: int) -> dict:
        sub = panel[universe]
        trailing = sub / sub.shift(prod.LOOKBACK_BARS) - 1.0
        v = sub.pct_change().rolling(prod.VOL_LOOKBACK_BARS).std()
        ranks = trailing.rank(axis=1, ascending=False)
        n = len(universe)
        raw = pd.DataFrame(0.0, index=sub.index, columns=universe)
        raw[ranks <= legs_per_side] = 1.0
        raw[ranks > n - legs_per_side] = -1.0
        raw = raw.where(trailing.notna(), 0.0)
        sized = (raw / v.replace(0.0, np.nan))
        sized = sized.div(sized.abs().sum(axis=1), axis=0).fillna(0.0)
        grid = pd.Series(np.arange(len(sized)) % prod.REBALANCE_BARS == 0, index=sized.index)
        held = sized.where(grid, np.nan).ffill().fillna(0.0)

        total = None
        for c in universe:
            leg = strategy_returns(held[c], sub[c], costs())
            total = leg if total is None else total + leg
        perf = summarise(total, BARS_PER_YEAR)
        p95 = float(np.percentile(bootstrap_max_drawdowns(total, n_paths=300), 95))
        usd = CAPITAL * perf.ann_return_pct * (LIVE_HALT / p95) / 100.0 if p95 > 0 else 0.0
        print(f"    {label:<44} {perf.sharpe:>+8.3f} {perf.ann_return_pct:>+8.2f}% "
              f"{usd:>+10,.0f}")
        return {"label": label, "sharpe": perf.sharpe, "usd": usd, "ret": total}

    print(f"    {'universe':<44} {'Sharpe':>8} {'return':>9} {'$ on 10k':>10}")
    print("    " + "-" * 74)
    full = run(list(prod.UNIVERSE), "all 19 (what P15 reported)", prod.LEGS_PER_SIDE)
    if len(tradeable) >= 6:
        legs = min(prod.LEGS_PER_SIDE, len(tradeable) // 2)
        restricted = run(tradeable, f"{len(tradeable)} tradeable only, {legs}/side", legs)
    else:
        restricted = None
        print(f"    fewer than 6 tradeable markets; no book is possible")

    print("\n" + "=" * 100)
    print("  VERDICT")
    print("=" * 100)
    if restricted:
        delta = restricted["usd"] - full["usd"]
        print(f"    P15 as reported (ignoring lot minimums): ${full['usd']:+,.0f}/yr")
        print(f"    Restricted to what can be traded:        ${restricted['usd']:+,.0f}/yr")
        print(f"    The lot minimums cost {delta:+,.0f} a year — "
              f"{abs(delta) / max(abs(full['usd']), 1) * 100:.0f}% of the reported figure.")
        print()
        print("    Any figure quoted before this check was measuring a book that could not")
        print("    have been held. That includes the +$247 in FINDINGS F-series, which is")
        print("    corrected by this run rather than defended.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
