"""The daily run. Read prices, decide, size, journal, report.

Sends no orders. Every fill is simulated and every decision — including every
refusal — is written to an append-only journal.

**What this is for.** The strategy's control z is +0.78 against a +2.00 bar, and
establishing its measured Sharpe needs about sixteen years of data against the six
and a half that exist. Nothing can shorten that except letting the clock run. Each
day this executes adds one out-of-sample observation, and that is the entire point:
it is an experiment collecting evidence, not a business earning a return.

Run it once per trading day after the daily close.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import MetaTrader5 as mt5  # noqa: E402

from goldlab.broker import mt5_read as br  # noqa: E402
from goldlab.execution import state as paper_state  # noqa: E402
from goldlab.journal.store import Decision, Journal  # noqa: E402
from goldlab.safety import risk  # noqa: E402
from goldlab.strategy import production as prod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "reports" / "paper.sqlite"
STATE = ROOT / "reports" / "paper_state.json"
CAPITAL = float(sys.argv[1]) if len(sys.argv) > 1 else 100_000.0


def banner() -> None:
    print("=" * 92)
    print("PAPER RUN — no orders are sent")
    print("=" * 92)
    print(f"  {prod.VALIDATION_STATUS}")
    print()


def fetch_panel() -> tuple[pd.DataFrame, dict, dict]:
    """Closed daily bars plus live specs, for every symbol in the universe."""
    need = prod.LOOKBACK_BARS + prod.VOL_LOOKBACK_BARS + 20
    closes, specs, prices = {}, {}, {}
    for symbol in prod.UNIVERSE:
        if not mt5.symbol_select(symbol, True):
            continue
        # start_pos=1 skips the still-forming bar. Using bar 0 would be look-ahead.
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, need)
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if rates is None or len(rates) < need or info is None or tick is None:
            continue
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        closes[symbol] = df.set_index("time")["close"]
        specs[symbol] = {
            "contract_size": info.trade_contract_size, "volume_min": info.volume_min,
            "volume_step": info.volume_step, "volume_max": info.volume_max,
            "point": info.point,
        }
        prices[symbol] = (tick.bid + tick.ask) / 2.0
    panel = pd.DataFrame(closes)
    return panel.loc[panel.notna().all(axis=1)], specs, prices


def main() -> int:
    banner()
    run_id = uuid.uuid4().hex[:12]
    journal = Journal(JOURNAL, run_id)
    now = datetime.now(timezone.utc)

    br.connect()
    try:
        acct = br.account()
        print(f"  account {acct.login} ({acct.trade_mode}) · capital basis ${CAPITAL:,.0f}")
        print(f"  limits: {risk.describe_limits()}")

        panel, specs, prices = fetch_panel()
        missing = [s for s in prod.UNIVERSE if s not in panel.columns]
        if missing:
            print(f"\n  {len(missing)} symbols unavailable this run: {missing}")
            print("  Refusing to trade a partial universe — a cross-sectional rank over a")
            print("  different set of markets is a different strategy.")
            journal.record_decision(Decision(
                bar_utc=now, symbol="-", action="HALTED",
                reason=f"universe incomplete: {missing}", inputs={"missing": missing},
            ))
            return 1

        bar_utc = panel.index[-1]
        print(f"\n  decision bar {bar_utc:%Y-%m-%d} · {len(panel):,} bars available")

        targets = prod.compute_targets(panel)

        # Restore the book. Without this the runner opened a fresh set of positions
        # every day, never closed anything, and reset equity to the starting capital —
        # producing a journal that recorded activity and measured nothing.
        broker = paper_state.load(STATE, CAPITAL)
        marked_open = broker.mark_to_market(prices)
        peak = paper_state.peak_equity(STATE, marked_open)

        state = risk.RiskState(equity=broker.equity, peak_equity=peak,
                               unrealised=marked_open - broker.equity,
                               open_positions=len(broker.positions))
        state = risk.clear_daily_halt(state, bar_utc.date())
        state = risk.check_halts(state)

        print(f"\n  carried in: {len(broker.positions)} open legs · "
              f"equity ${broker.equity:,.2f} · marked ${marked_open:,.2f} · "
              f"peak ${peak:,.2f} · drawdown {state.drawdown_pct:.2f}%")
        if state.halted:
            print(f"  *** HALTED: {state.halt_reason} ***")

        # --- close what should no longer be held ---
        wanted = {t.symbol: t for t in targets}
        stale = set(broker.stale_positions(now))
        closed = 0
        for symbol in list(broker.positions):
            if symbol not in prices:
                continue
            leaving = symbol not in wanted
            flipping = (not leaving and
                        (broker.positions[symbol].lots > 0) != (wanted[symbol].weight > 0))
            aging = symbol in stale
            if not (leaving or flipping or aging or state.halted):
                continue
            reason = ("no longer in the book" if leaving else
                      "side flipped" if flipping else
                      "halted" if state.halted else
                      f"approaching the {broker.FREE_DAYS}-day financing-free window")
            pnl, cost = broker.close(symbol, prices[symbol])
            closed += 1
            print(f"  closed {symbol:<9} P&L {pnl:>+9.2f}  cost {cost:>6.2f}  ({reason})")
            journal.record_decision(Decision(
                bar_utc=bar_utc, symbol=symbol, action="CLOSE", price=prices[symbol],
                equity=broker.equity, reason=reason, inputs={"pnl": pnl, "cost": cost},
            ))
            journal.record_fill(bar_utc, symbol, "CLOSE", 0.0, prices[symbol], cost, "PAPER")

        print(f"\n  {'rank':>5} {'symbol':<9} {'weight':>8} {'120d ret':>10} "
              f"{'lots':>10}  status")
        print("  " + "-" * 74)

        placed = refused = 0
        for t in targets:
            if t.symbol in broker.positions:
                # Already held on the correct side and inside the free window.
                print(f"  {t.rank:>5} {t.symbol:<9} {t.weight:>+8.3f} "
                      f"{t.trailing_return:>+9.1%} {broker.positions[t.symbol].lots:>+10.2f}"
                      f"  held")
                continue
            if state.halted:
                refused += 1
                journal.record_decision(Decision(
                    bar_utc=bar_utc, symbol=t.symbol, action="HALTED", rank=t.rank,
                    weight=t.weight, reason=state.halt_reason, inputs={},
                ))
                continue
            spec = specs[t.symbol]
            price = prices[t.symbol]
            # Stop distance from the market's own volatility, not a fixed number.
            vol = float(panel[t.symbol].pct_change().rolling(prod.VOL_LOOKBACK_BARS)
                        .std().iloc[-1])
            stop_distance = max(price * vol * 2.0, spec["point"] * 10)

            annual_vol = vol * (252 ** 0.5)
            try:
                # Book-level volatility sizing, owner-approved 2026-08-16. The
                # per-trade stop rule was written for a single-position bot and is
                # not what constrains a balanced 14-leg book — see risk.py.
                lots = risk.book_leg_size(
                    state, symbol=t.symbol, weight=t.weight, price=price,
                    annual_vol=annual_vol, contract_size=spec["contract_size"],
                    volume_min=spec["volume_min"], volume_step=spec["volume_step"],
                    volume_max=spec["volume_max"], n_legs=len(targets),
                )
                cost = broker.open(t.symbol, lots, price, spec["contract_size"], now)
                placed += 1
                print(f"  {t.rank:>5} {t.symbol:<9} {t.weight:>+8.3f} "
                      f"{t.trailing_return:>+9.1%} {lots:>+10.2f}  opened (cost ${cost:.2f})")
                journal.record_decision(Decision(
                    bar_utc=bar_utc, symbol=t.symbol, action="TARGET", rank=t.rank,
                    weight=t.weight, trailing_ret=t.trailing_return, price=price,
                    lots=lots, equity=state.equity, reason="cross-sectional rank",
                    inputs={"stop_distance": stop_distance, "vol": vol, **spec},
                ))
                journal.record_fill(bar_utc, t.symbol, "BUY" if lots > 0 else "SELL",
                                    abs(lots), price, cost, "PAPER")
            except risk.RiskRefusal as exc:
                refused += 1
                print(f"  {t.rank:>5} {t.symbol:<9} {t.weight:>+8.3f} "
                      f"{t.trailing_return:>+9.1%} {'--':>10}  REFUSED")
                print(f"        {exc}")
                journal.record_decision(Decision(
                    bar_utc=bar_utc, symbol=t.symbol, action="REFUSED", rank=t.rank,
                    weight=t.weight, trailing_ret=t.trailing_return, price=price,
                    equity=state.equity, reason=str(exc),
                    inputs={"stop_distance": stop_distance, "vol": vol, **spec},
                ))

        marked = broker.mark_to_market(prices)
        peak = max(peak, marked)
        drawdown = max(0.0, (1 - marked / peak) * 100.0) if peak > 0 else 0.0

        paper_state.save(STATE, broker, peak)
        journal.record_equity(
            bar_utc=bar_utc, equity=marked, peak_equity=peak, drawdown_pct=drawdown,
            open_legs=len(broker.positions), halted=state.halted,
            note=f"placed={placed} closed={closed} refused={refused}",
        )

        pnl_total = marked - CAPITAL
        print(f"\n  placed {placed} · closed {closed} · refused {refused}")
        print(f"  equity ${marked:,.2f}  ({pnl_total:+,.2f} since inception, "
              f"{pnl_total / CAPITAL:+.2%})")
        print(f"  realised ${broker.realised:+,.2f} · costs paid ${broker.costs_paid:,.2f} · "
              f"drawdown {drawdown:.2f}% of a {risk.MAX_DRAWDOWN_PCT:.0f}% limit")

        observations = journal.observation_count()
        needed = prod.MEASURED["years_to_prove"] * 260
        print(f"\n  out-of-sample observations: {observations:,} of roughly "
              f"{needed:,.0f} needed ({observations / needed:.2%})")
        print(f"  journal -> {JOURNAL}")
        print()
        print("  " + prod.VALIDATION_STATUS)
        return 0
    finally:
        br.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
