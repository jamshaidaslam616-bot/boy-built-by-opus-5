"""The only module in this project that can send an order.

Everything else is read-only by construction. This one is not, so it carries the
safeguards that the rest of the codebase gets for free by being unable to act:

  * **It refuses to run on a live account.** The account's trade mode is checked on
    every call, not once at startup. A demo account cannot become live, but a
    terminal can be pointed at a different account between runs, and this is the
    place where that must never go unnoticed.
  * **It requires an explicit unlock.** Importing it, or running the runner, is not
    enough — ``GOLDLAB_DEMO_TRADING=enabled`` must be set. Nothing can send an order
    by accident or by being invoked with the wrong script name.
  * **It touches only its own positions.** Every order carries ``MAGIC``, and
    anything without it is invisible to this module. Manual trades on the same
    account are never closed, modified, or counted.
  * **The broker is the truth.** State is reconstructed from ``positions_get()`` on
    every run. Local files are a hint and are never trusted over what the broker
    actually holds — if the two disagree, the broker wins and the disagreement is
    reported.
  * **Idempotent by symbol.** A position that already exists is never opened again.
    Duplicate orders are the classic way an automated system doubles its intended
    risk without anyone noticing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import MetaTrader5 as mt5

MAGIC = 20260817
"""Stamped on every order. Positions without it belong to someone else."""

UNLOCK_ENV = "GOLDLAB_DEMO_TRADING"
UNLOCK_VALUE = "enabled"

MAX_SLIPPAGE_POINTS = 50
"""Deviation allowed on a market order. Wide enough to fill, tight enough that a
genuinely dislocated market rejects rather than fills at any price."""


class ExecutionRefusal(RuntimeError):
    """Raised instead of sending. Every refusal is loud and none is a silent no-op."""


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: str
    lots: float
    price: float
    ticket: int
    filled_utc: datetime
    requested_price: float

    @property
    def slippage_points(self) -> float:
        """Signed, in price units. Positive means we paid worse than we asked."""
        sign = 1.0 if self.side == "BUY" else -1.0
        return (self.price - self.requested_price) * sign


def assert_unlocked() -> None:
    """Two independent conditions, both required, checked on every send."""
    if os.getenv(UNLOCK_ENV, "").strip().lower() != UNLOCK_VALUE:
        raise ExecutionRefusal(
            f"demo trading is locked. Set {UNLOCK_ENV}={UNLOCK_VALUE} to enable it. "
            "This is deliberate: no script name or import can unlock the order path."
        )

    info = mt5.account_info()
    if info is None:
        raise ExecutionRefusal("account_info() returned None; refusing to send blind")
    if info.trade_mode != 0:  # 0 = DEMO, 1 = CONTEST, 2 = REAL
        raise ExecutionRefusal(
            f"account {info.login} has trade_mode={info.trade_mode}, which is not DEMO. "
            "This module sends orders and will not do so on a live account."
        )


def our_positions() -> dict[str, dict]:
    """What the BROKER says we hold. Local state never overrides this.

    Filtered to our magic number, so a human trading the same account by hand is
    invisible here and their positions are never touched.
    """
    positions = mt5.positions_get()
    if positions is None:
        code, desc = mt5.last_error()
        raise ExecutionRefusal(f"positions_get() returned None ({code}: {desc})")

    out: dict[str, dict] = {}
    for p in positions:
        if p.magic != MAGIC:
            continue
        lots = p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume
        out[p.symbol] = {
            "ticket": p.ticket, "lots": lots, "entry": p.price_open,
            "profit": p.profit, "swap": p.swap,
            "opened_utc": datetime.fromtimestamp(p.time, tz=timezone.utc),
        }
    return out


def _filling_mode(symbol: str) -> int:
    """The filling mode this symbol actually accepts.

    Brokers differ and a wrong mode is rejected with an unhelpful code. Reading it
    beats guessing, and guessing beats nothing only when it happens to be right.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        raise ExecutionRefusal(f"{symbol}: symbol_info() returned None")
    allowed = info.filling_mode
    if allowed & 1:      # SYMBOL_FILLING_FOK
        return mt5.ORDER_FILLING_FOK
    if allowed & 2:      # SYMBOL_FILLING_IOC
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def open_position(symbol: str, lots: float, comment: str = "goldlab") -> Fill:
    """Send a market order. Refuses if a position in this symbol already exists."""
    assert_unlocked()
    if lots == 0:
        raise ExecutionRefusal(f"{symbol}: refusing to send an order for zero lots")

    if symbol in our_positions():
        raise ExecutionRefusal(
            f"{symbol}: a position already exists. Refusing to open a second one — "
            "duplicate orders are how an automated system silently doubles its risk."
        )

    if not mt5.symbol_select(symbol, True):
        raise ExecutionRefusal(f"{symbol}: could not be selected in Market Watch")
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or tick.bid <= 0:
        raise ExecutionRefusal(f"{symbol}: no tradeable quote")

    is_buy = lots > 0
    price = tick.ask if is_buy else tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": abs(lots),
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": MAX_SLIPPAGE_POINTS,
        "magic": MAGIC,
        "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling_mode(symbol),
    }

    result = mt5.order_send(request)
    if result is None:
        code, desc = mt5.last_error()
        raise ExecutionRefusal(f"{symbol}: order_send() returned None ({code}: {desc})")
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise ExecutionRefusal(
            f"{symbol}: order rejected, retcode={result.retcode} ({result.comment})"
        )

    return Fill(
        symbol=symbol, side="BUY" if is_buy else "SELL", lots=abs(lots),
        price=result.price, ticket=result.order,
        filled_utc=datetime.now(timezone.utc), requested_price=price,
    )


def close_position(symbol: str) -> Fill:
    """Close our position in ``symbol``. Never touches a position without our magic."""
    assert_unlocked()
    held = our_positions()
    if symbol not in held:
        raise ExecutionRefusal(f"{symbol}: no position of ours to close")

    position = held[symbol]
    lots = abs(position["lots"])
    was_long = position["lots"] > 0

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise ExecutionRefusal(f"{symbol}: no quote to close against")
    price = tick.bid if was_long else tick.ask

    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": mt5.ORDER_TYPE_SELL if was_long else mt5.ORDER_TYPE_BUY,
        "position": position["ticket"],
        "price": price,
        "deviation": MAX_SLIPPAGE_POINTS,
        "magic": MAGIC,
        "comment": "goldlab close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling_mode(symbol),
    })
    if result is None:
        code, desc = mt5.last_error()
        raise ExecutionRefusal(f"{symbol}: close returned None ({code}: {desc})")
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise ExecutionRefusal(
            f"{symbol}: close rejected, retcode={result.retcode} ({result.comment})"
        )

    return Fill(
        symbol=symbol, side="SELL" if was_long else "BUY", lots=lots,
        price=result.price, ticket=result.order,
        filled_utc=datetime.now(timezone.utc), requested_price=price,
    )


def reconcile(expected: dict[str, float]) -> tuple[dict, list[str]]:
    """Compare what we think we hold against what the broker says.

    Returns ``(broker_positions, disagreements)``. A disagreement is never resolved
    silently — the caller reports it and stops. Local state drifting from broker
    state is the failure that turns a small bug into an unbounded position.
    """
    actual = our_positions()
    problems = []

    for symbol, lots in expected.items():
        if symbol not in actual:
            problems.append(f"{symbol}: we expect {lots:+.2f} lots, broker holds nothing")
        elif abs(actual[symbol]["lots"] - lots) > 1e-8:
            problems.append(
                f"{symbol}: we expect {lots:+.2f} lots, broker holds "
                f"{actual[symbol]['lots']:+.2f}"
            )
    for symbol in actual:
        if symbol not in expected:
            problems.append(
                f"{symbol}: broker holds {actual[symbol]['lots']:+.2f} lots we do not expect"
            )
    return actual, problems
