"""The daily run, against a demo account, sending REAL orders.

Identical decision path to ``run_paper.py`` — same targets, same sizing, same risk
engine, same journal. Only the fill is real.

That sameness is the point. The reason to run this at all is to measure the gap
between what the paper simulation assumed and what the broker actually does:
slippage, rejections, and fills that land somewhere other than the quote. Those
numbers replace assumptions in the cost model, and a cost model built on
assumptions is how a backtest stays profitable while an account does not.

Requires ``GOLDLAB_DEMO_TRADING=enabled``. Refuses on any account that is not DEMO.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldlab.broker import mt5_read as br  # noqa: E402
from goldlab.execution import mt5_demo  # noqa: E402
from goldlab.journal.store import Decision, Journal  # noqa: E402
from goldlab.safety import risk  # noqa: E402
from goldlab.strategy import production as prod  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_paper import fetch_panel  # noqa: E402  (identical data path, deliberately shared)

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "reports" / "demo.sqlite"
FREE_DAYS = 7


def main() -> int:
    print("=" * 92)
    print("DEMO RUN — real orders on a demo account")
    print("=" * 92)
    print(f"  {prod.VALIDATION_STATUS}\n")

    journal = Journal(JOURNAL, uuid.uuid4().hex[:12])
    now = datetime.now(timezone.utc)

    br.connect()
    try:
        acct = br.account()
        print(f"  account {acct.login} ({acct.trade_mode}) · equity ${acct.equity:,.2f}")

        try:
            mt5_demo.assert_unlocked()
        except mt5_demo.ExecutionRefusal as exc:
            print(f"\n  REFUSED: {exc}")
            return 1
        print("  order path UNLOCKED — this run can send orders\n")

        panel, specs, prices = fetch_panel()
        missing = [s for s in prod.UNIVERSE if s not in panel.columns]
        if missing:
            print(f"  {len(missing)} symbols unavailable: {missing}")
            print("  Refusing to trade a partial universe.")
            return 1

        bar_utc = panel.index[-1]

        # Decide tradeability BEFORE ranking, so a leg that cannot be held is
        # substituted rather than leaving a hole. The first demo run skipped this and
        # produced a 5-long / 3-short book — a directional bet, not the strategy.
        equity_now = acct.equity

        # Weights are proportional to 1/volatility and then normalised, so a volatile
        # market gets a SMALL weight. Checking tradeability at a uniform 1/14 weight
        # therefore over-estimates what a volatile symbol would receive — it passes
        # the check and then fails at sizing, which is exactly what happened on the
        # second demo run. The predicate has to ask the same question the sizer will.
        vols = {
            s: float(panel[s].pct_change().rolling(prod.VOL_LOOKBACK_BARS).std().iloc[-1])
               * (252 ** 0.5)
            for s in prod.UNIVERSE if s in panel.columns
        }
        inverse = {s: 1.0 / v for s, v in vols.items() if v > 0}
        # Approximate the normalisation over a typical 14-leg book rather than the
        # whole universe: the book only ever holds 14 of the 25.
        typical = sorted(inverse.values(), reverse=True)[: prod.LEGS_PER_SIDE * 2]
        gross = sum(typical) if typical else 1.0

        def is_tradeable(symbol: str) -> bool:
            spec = specs.get(symbol)
            if spec is None or symbol not in prices or symbol not in inverse:
                return False
            weight = min(inverse[symbol] / gross, prod.MAX_LEG_WEIGHT)
            try:
                risk.book_leg_size(
                    risk.RiskState(equity=equity_now, peak_equity=equity_now),
                    symbol=symbol, weight=weight,
                    price=prices[symbol], annual_vol=vols[symbol],
                    contract_size=spec["contract_size"], volume_min=spec["volume_min"],
                    volume_step=spec["volume_step"], volume_max=spec["volume_max"],
                    n_legs=prod.LEGS_PER_SIDE * 2,
                )
                return True
            except risk.RiskRefusal:
                return False

        targets = prod.compute_targets(panel, tradeable=is_tradeable)
        n_side = sum(1 for t in targets if t.weight > 0)
        print(f"  book: {n_side} long / {len(targets) - n_side} short "
              f"(balanced by construction)")
        wanted = {t.symbol: t for t in targets}

        # The broker is the truth. Local files are not consulted for what we hold.
        held = mt5_demo.our_positions()
        print(f"  broker holds {len(held)} of our positions · decision bar "
              f"{bar_utc:%Y-%m-%d}\n")

        equity = acct.equity
        state = risk.RiskState(equity=equity, peak_equity=equity,
                               open_positions=len(held))
        state = risk.check_halts(state)
        if state.halted:
            print(f"  *** HALTED: {state.halt_reason} ***")

        # --- close what should no longer be held ---
        closed = 0
        for symbol, pos in list(held.items()):
            aged = (now - pos["opened_utc"]).days >= FREE_DAYS - 1
            leaving = symbol not in wanted
            flipping = not leaving and (pos["lots"] > 0) != (wanted[symbol].weight > 0)
            if not (aged or leaving or flipping or state.halted):
                continue
            reason = ("no longer in the book" if leaving else "side flipped" if flipping
                      else "halted" if state.halted else "approaching the free window")
            try:
                fill = mt5_demo.close_position(symbol)
                closed += 1
                print(f"  closed {symbol:<9} {pos['lots']:+7.2f} lots @ {fill.price:>12,.5f}  "
                      f"P&L {pos['profit']:>+9.2f}  swap {pos['swap']:>+7.2f}  ({reason})")
                journal.record_fill(bar_utc, symbol, fill.side, fill.lots, fill.price,
                                    0.0, "DEMO")
                journal.record_decision(Decision(
                    bar_utc=bar_utc, symbol=symbol, action="CLOSE", price=fill.price,
                    lots=pos["lots"], equity=equity, reason=reason,
                    inputs={"profit": pos["profit"], "swap": pos["swap"],
                            "slippage": fill.slippage_points, "ticket": fill.ticket},
                ))
            except mt5_demo.ExecutionRefusal as exc:
                print(f"  close {symbol:<9} REFUSED: {exc}")

        held = mt5_demo.our_positions()

        # --- open what is new ---
        print(f"\n  {'rank':>5} {'symbol':<9} {'weight':>8} {'lots':>9} "
              f"{'fill':>13} {'slip':>9}  status")
        print("  " + "-" * 78)

        placed = refused = 0
        for t in targets:
            if t.symbol in held:
                print(f"  {t.rank:>5} {t.symbol:<9} {t.weight:>+8.3f} "
                      f"{held[t.symbol]['lots']:>+9.2f} {'':>13} {'':>9}  held")
                continue
            if state.halted:
                refused += 1
                continue

            spec = specs[t.symbol]
            vol = float(panel[t.symbol].pct_change()
                        .rolling(prod.VOL_LOOKBACK_BARS).std().iloc[-1])
            try:
                lots = risk.book_leg_size(
                    state, symbol=t.symbol, weight=t.weight, price=prices[t.symbol],
                    annual_vol=vol * (252 ** 0.5), contract_size=spec["contract_size"],
                    volume_min=spec["volume_min"], volume_step=spec["volume_step"],
                    volume_max=spec["volume_max"], n_legs=len(targets),
                )
                fill = mt5_demo.open_position(t.symbol, lots)
                placed += 1
                print(f"  {t.rank:>5} {t.symbol:<9} {t.weight:>+8.3f} {lots:>+9.2f} "
                      f"{fill.price:>13,.5f} {fill.slippage_points:>+9.5f}  filled")
                journal.record_fill(bar_utc, t.symbol, fill.side, fill.lots, fill.price,
                                    0.0, "DEMO")
                journal.record_decision(Decision(
                    bar_utc=bar_utc, symbol=t.symbol, action="TARGET", rank=t.rank,
                    weight=t.weight, trailing_ret=t.trailing_return, price=fill.price,
                    lots=lots, equity=equity, reason="cross-sectional rank",
                    inputs={"requested": fill.requested_price,
                            "slippage": fill.slippage_points, "ticket": fill.ticket},
                ))
            except (risk.RiskRefusal, mt5_demo.ExecutionRefusal) as exc:
                refused += 1
                print(f"  {t.rank:>5} {t.symbol:<9} {t.weight:>+8.3f} {'--':>9} "
                      f"{'':>13} {'':>9}  REFUSED")
                print(f"        {exc}")
                journal.record_decision(Decision(
                    bar_utc=bar_utc, symbol=t.symbol, action="REFUSED", rank=t.rank,
                    weight=t.weight, equity=equity, reason=str(exc), inputs={},
                ))

        # --- the check that matters: does the broker agree with us? ---
        expected = {t.symbol: 0.0 for t in targets}
        final = mt5_demo.our_positions()
        expected = {s: p["lots"] for s, p in final.items()}
        _, problems = mt5_demo.reconcile(expected)

        acct = br.account()
        print(f"\n  placed {placed} · closed {closed} · refused {refused}")
        print(f"  account equity ${acct.equity:,.2f} · balance ${acct.balance:,.2f} · "
              f"{len(final)} open")
        print(f"  reconciliation: {'CLEAN' if not problems else 'DISAGREEMENT'}")
        for p in problems:
            print(f"    {p}")

        journal.record_equity(
            bar_utc=bar_utc, equity=acct.equity, peak_equity=max(acct.balance, acct.equity),
            drawdown_pct=max(0.0, (1 - acct.equity / max(acct.balance, acct.equity)) * 100),
            open_legs=len(final), halted=state.halted,
            note=f"placed={placed} closed={closed} refused={refused}",
        )
        print(f"\n  journal -> {JOURNAL}")
        print(f"  {prod.VALIDATION_STATUS}")
        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
