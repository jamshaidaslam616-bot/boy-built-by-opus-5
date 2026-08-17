"""Read-only MT5 adapter.

Two properties of this module are deliberate and load-bearing:

1. **Attach-only.** ``initialize()`` is called without credentials, so this process
   binds to whichever account the terminal is already logged into. It never calls
   ``initialize(login=...)``. A terminal holds exactly one login at a time —
   whichever process passes credentials last wins, and silently breaks the others.

   Since 2026-08-17 this project has its own terminal (``GOLDLAB_MT5_PATH``,
   logged into 472250693 by hand) rather than sharing one. ``path=`` picks a
   terminal; it does not log anything in, so the property above still holds.
   ``GOLDLAB_MT5_LOGIN`` is then checked on every connect, because ``path=`` is
   a hint about what to *launch* and not a guarantee about what answers: a
   sibling bot on this machine had its terminal exit, silently attached to a
   different one, and read a foreign account for two hours.

2. **There are no order functions here.** Not stubbed, not disabled — absent. This
   module physically cannot place, modify or close anything.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import MetaTrader5 as mt5


class BrokerReadError(RuntimeError):
    """Raised when the terminal cannot be read. Never swallowed, never defaulted."""


# MT5's ENUM_DAY_OF_WEEK is 0=Sunday, not 0=Monday. Getting this wrong misattributes
# the triple-swap night by two days.
_MT5_WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


@dataclass(frozen=True)
class AccountSnapshot:
    login: int
    server: str
    company: str
    currency: str
    balance: float
    equity: float
    leverage: int
    margin_free: float
    trade_mode: str


@dataclass(frozen=True)
class SymbolCosts:
    """Everything the terminal will tell us about what a trade costs.

    ``commission`` is absent on purpose: MT5 does not expose it on ``symbol_info``,
    on ``order_check`` or on ``order_calc_profit``. The server applies it at fill
    time. It can be observed from a real fill or looked up — it cannot be read.
    Anything that needs it must take it as an explicit input, never a default.
    """

    symbol: str
    path: str
    digits: int
    point: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level: int
    freeze_level: int

    spread_current_points: int
    spread_float: bool
    bid: float
    ask: float

    swap_long_points: float
    swap_short_points: float
    swap_mode: int
    swap_rollover_3x_weekday: int

    tick_value: float
    tick_size: float
    read_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # --- derived, all from the fields above; nothing hardcoded ---

    @property
    def value_per_point_per_lot(self) -> float:
        """USD moved by one point of price, on one lot."""
        return self.point * self.contract_size

    @property
    def spread_cost_per_lot(self) -> float:
        """Cost of crossing the spread once, per lot, in account currency."""
        return self.spread_current_points * self.value_per_point_per_lot

    @property
    def notional_per_lot(self) -> float:
        return ((self.bid + self.ask) / 2.0) * self.contract_size

    @property
    def swap_long_per_lot_per_night(self) -> float:
        return self.swap_long_points * self.value_per_point_per_lot

    @property
    def swap_short_per_lot_per_night(self) -> float:
        return self.swap_short_points * self.value_per_point_per_lot

    @property
    def triple_swap_day(self) -> str:
        idx = self.swap_rollover_3x_weekday
        return _MT5_WEEKDAYS[idx] if 0 <= idx < len(_MT5_WEEKDAYS) else f"unknown({idx})"

    def swap_annual_pct_of_notional(self, side: str) -> float:
        """Carry drag as a percentage of notional per year.

        Uses 365 nights plus 52 extra nights for the weekly triple-swap rollover
        (a 3x night charges two nights more than a normal one).
        """
        per_night = (
            self.swap_long_per_lot_per_night if side == "long" else self.swap_short_per_lot_per_night
        )
        if self.notional_per_lot <= 0:
            raise BrokerReadError(f"{self.symbol}: non-positive notional, cannot compute carry")
        nights = 365.0 + 52.0 * 2.0
        return (per_night * nights) / self.notional_per_lot * 100.0


_env_loaded = False


def _load_env_once() -> None:
    """Read the project's .env, without overriding anything already exported.

    Kept here rather than at import time so that importing this module for its
    dataclasses has no side effects. Real environment variables win, so a
    script can still point itself at a different terminal deliberately.
    """
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is optional
        return
    root = Path(__file__).resolve().parents[3]
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


def connect(expect_login: int | None = None) -> None:
    """Attach to the already-running, already-logged-in terminal.

    Still no credentials — the "never logs in" property above is unchanged.
    ``GOLDLAB_MT5_PATH`` only chooses *which* terminal to attach to, and a
    terminal's login is whatever a human set it to. Nothing here can switch an
    account out from under another project.

    Pointing at a dedicated terminal matters for read-only work too. Attaching
    to "whatever is running" means reading whatever account that terminal
    happens to hold, and on this machine those differ in ways that silently
    corrupt research: one carries XAUUSD at a ~40 point spread, another
    XAUUSDm at ~190. A cost study that samples the wrong one is measuring a
    different instrument and will never say so.

    ``expect_login`` is checked when given. A terminal can exit and the library
    will attach to a different one that happens to be running — that is how a
    sibling bot on this box spent two hours reading a foreign account.
    """
    _load_env_once()
    path = os.getenv("GOLDLAB_MT5_PATH", "").strip()
    ok = mt5.initialize(path=path) if path else mt5.initialize()
    if not ok:
        code, desc = mt5.last_error()
        raise BrokerReadError(
            f"could not attach to the MT5 terminal ({code}: {desc})"
            + (f" at {path}" if path else "")
            + ". Start MetaTrader 5 and log in manually — this module never logs in."
        )

    if expect_login is None:
        raw = os.getenv("GOLDLAB_MT5_LOGIN", "").strip()
        expect_login = int(raw) if raw.isdigit() else None
    if expect_login:
        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            raise BrokerReadError("attached, but account_info() returned None")
        if int(info.login) != expect_login:
            actual = int(info.login)
            mt5.shutdown()
            raise BrokerReadError(
                f"attached to account {actual}, expected {expect_login}. "
                "Refusing to read the wrong account's data."
            )


def disconnect() -> None:
    mt5.shutdown()


def account() -> AccountSnapshot:
    info = mt5.account_info()
    if info is None:
        code, desc = mt5.last_error()
        raise BrokerReadError(f"account_info() returned None ({code}: {desc})")
    modes = {0: "DEMO", 1: "CONTEST", 2: "REAL"}
    return AccountSnapshot(
        login=info.login,
        server=info.server,
        company=info.company,
        currency=info.currency,
        balance=info.balance,
        equity=info.equity,
        leverage=info.leverage,
        margin_free=info.margin_free,
        trade_mode=modes.get(info.trade_mode, f"unknown({info.trade_mode})"),
    )


def find_symbols(*roots: str) -> dict[str, list[str]]:
    """Resolve symbol roots to the broker's actual names, suffixes and all.

    Exness decorates symbols per account type (``XAUUSD`` vs ``XAUUSDm``), so the
    name is discovered, never assumed.
    """
    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        code, desc = mt5.last_error()
        raise BrokerReadError(f"symbols_get() returned None ({code}: {desc})")
    out: dict[str, list[str]] = {}
    for root in roots:
        matches = sorted(
            s.name for s in all_symbols if s.name.upper().startswith(root.upper())
        )
        out[root] = matches
    return out


def _require(value: Any, symbol: str, field_name: str) -> Any:
    """A missing contract property is a hard failure, never a substituted default.

    Hardcoding or defaulting contract size is how a position ends up sized 100x wrong.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise BrokerReadError(f"{symbol}: required property '{field_name}' is missing")
    return value


def symbol_costs(symbol: str) -> SymbolCosts:
    """Read every cost-relevant property the terminal exposes for one symbol."""
    if not mt5.symbol_select(symbol, True):
        raise BrokerReadError(f"{symbol}: could not be selected in Market Watch")

    info = mt5.symbol_info(symbol)
    if info is None:
        code, desc = mt5.last_error()
        raise BrokerReadError(f"{symbol}: symbol_info() returned None ({code}: {desc})")

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        code, desc = mt5.last_error()
        raise BrokerReadError(f"{symbol}: symbol_info_tick() returned None ({code}: {desc})")

    if tick.bid <= 0 or tick.ask <= 0:
        raise BrokerReadError(f"{symbol}: non-positive quote bid={tick.bid} ask={tick.ask}")

    # A zero spread is not a price. It means the session is shut and we are looking
    # at a frozen print. Recorded as-is here, but callers must check `feed_state`
    # before putting any of these numbers into a cost model.
    if tick.ask - tick.bid <= 0 and info.spread == 0:
        pass  # reported by the caller via feed_state(); not silently corrected here

    return SymbolCosts(
        symbol=info.name,
        path=info.path,
        digits=_require(info.digits, symbol, "digits"),
        point=_require(info.point, symbol, "point"),
        contract_size=_require(info.trade_contract_size, symbol, "trade_contract_size"),
        volume_min=_require(info.volume_min, symbol, "volume_min"),
        volume_max=_require(info.volume_max, symbol, "volume_max"),
        volume_step=_require(info.volume_step, symbol, "volume_step"),
        stops_level=info.trade_stops_level,
        freeze_level=info.trade_freeze_level,
        spread_current_points=info.spread,
        spread_float=info.spread_float,
        bid=tick.bid,
        ask=tick.ask,
        swap_long_points=_require(info.swap_long, symbol, "swap_long"),
        swap_short_points=_require(info.swap_short, symbol, "swap_short"),
        swap_mode=info.swap_mode,
        swap_rollover_3x_weekday=info.swap_rollover3days,
        tick_value=_require(info.trade_tick_value, symbol, "trade_tick_value"),
        tick_size=_require(info.trade_tick_size, symbol, "trade_tick_size"),
    )


def cross_check_point_value(costs: SymbolCosts) -> tuple[float, float, bool]:
    """Verify our arithmetic against the broker's own profit calculator.

    If ``value_per_point_per_lot`` and ``order_calc_profit`` ever disagree, every
    position size in the system is wrong by the same factor. Returns
    (ours, brokers, agree) for a 1.000 price move on 1.00 lot.
    """
    ours = costs.value_per_point_per_lot * (1.0 / costs.point)
    brokers = mt5.order_calc_profit(
        mt5.ORDER_TYPE_BUY, costs.symbol, 1.0, costs.ask, costs.ask + 1.0
    )
    if brokers is None:
        code, desc = mt5.last_error()
        raise BrokerReadError(f"{costs.symbol}: order_calc_profit() returned None ({code}: {desc})")
    return ours, brokers, math.isclose(ours, brokers, rel_tol=1e-6)


# A quote older than this is not a live market. Gold ticks many times a second
# during the session, so anything beyond a couple of minutes means the session is
# closed (or the feed is dead) — either way the quote is not tradeable.
STALE_TICK_SECONDS = 120.0


@dataclass(frozen=True)
class FeedState:
    symbol: str
    last_tick_utc: datetime
    local_utc: datetime
    tick_age_seconds: float
    trade_mode: int
    session_open: bool

    @property
    def is_live(self) -> bool:
        return self.session_open and self.tick_age_seconds <= STALE_TICK_SECONDS


def feed_state(symbol: str) -> FeedState:
    """Is this a live market, or are we looking at Friday's closing print?

    A stale quote and a skewed clock look identical if you only subtract two
    timestamps, and they demand opposite responses. This separates them: the
    broker's own session flag says whether the market is open, and the tick age
    says whether the feed is alive. Reading a spread from a closed market and
    feeding it to a cost model is how a backtest invents free trades.
    """
    if not mt5.symbol_select(symbol, True):
        raise BrokerReadError(f"{symbol}: could not be selected in Market Watch")
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None:
        code, desc = mt5.last_error()
        raise BrokerReadError(f"{symbol}: no tick/info for feed check ({code}: {desc})")

    last = datetime.fromtimestamp(tick.time, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    return FeedState(
        symbol=symbol,
        last_tick_utc=last,
        local_utc=now,
        tick_age_seconds=(now - last).total_seconds(),
        trade_mode=info.trade_mode,
        # SYMBOL_TRADE_MODE_FULL == 4; anything less restricts or disables trading.
        session_open=(info.trade_mode == 4) and (now - last).total_seconds() <= STALE_TICK_SECONDS,
    )
