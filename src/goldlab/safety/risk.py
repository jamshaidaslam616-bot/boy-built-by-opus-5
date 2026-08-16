"""The risk engine. It can refuse anything; nothing can refuse it.

Owner-set limits, and the reasons they are constants rather than configuration:
a limit that can be raised at runtime is a suggestion. Two of these were negotiated
directly with the owner and one was raised by them explicitly on 2026-08-10; none of
them may be moved without the owner saying so, including to avoid a halt.

Martingale, grid, averaging down and hedging are not merely discouraged here. Every
sizing request that would add to a losing position is rejected by construction,
because those four are how retail accounts actually die — they trade a smooth equity
curve for a tail that arrives once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# --------------------------------------------------------------- OWNER-SET
RISK_PER_DECISION_PCT = 0.5     # of equity, across the whole book
DAILY_LOSS_STOP_PCT = 3.0
MAX_DRAWDOWN_PCT = 20.0         # raised from 10% by the owner, 2026-08-10, see F13
MAX_CONCURRENT_POSITIONS = 3
CORRELATION_MERGE_THRESHOLD = 0.70

# Sizing that respects the drawdown limit. F13 measured that a single backtest path
# understates the 95th-percentile drawdown by 1.58x, so the target is set from the
# bootstrap, not from what one history happened to produce.
VOL_TARGET = 0.07
BOOTSTRAP_UNDERSTATEMENT = 1.58


class RiskRefusal(Exception):
    """Raised instead of returning a size. A refusal is never silent."""


@dataclass
class RiskState:
    """Everything the engine needs to decide. Reconstructed from the broker on start."""

    equity: float
    peak_equity: float
    realised_today: float = 0.0
    unrealised: float = 0.0
    trading_day: date | None = None
    open_positions: int = 0
    halted: bool = False
    halt_reason: str = ""
    refusals: list[str] = field(default_factory=list)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (1.0 - (self.equity + self.unrealised) / self.peak_equity) * 100.0)

    @property
    def daily_loss_pct(self) -> float:
        if self.equity <= 0:
            return 0.0
        return max(0.0, -(self.realised_today + self.unrealised) / self.equity * 100.0)


def check_halts(state: RiskState) -> RiskState:
    """Evaluate every automatic halt. Once tripped, a halt stays tripped.

    Clearing it is a deliberate human act, because a halt that clears itself is a
    halt that fires repeatedly while the thing it was protecting against continues.
    """
    if state.halted:
        return state

    if state.drawdown_pct >= MAX_DRAWDOWN_PCT:
        state.halted = True
        state.halt_reason = (
            f"drawdown {state.drawdown_pct:.2f}% reached the {MAX_DRAWDOWN_PCT:.0f}% limit. "
            "This does not clear on its own — understand why it fired before clearing it."
        )
    elif state.daily_loss_pct >= DAILY_LOSS_STOP_PCT:
        state.halted = True
        state.halt_reason = (
            f"daily loss {state.daily_loss_pct:.2f}% reached the {DAILY_LOSS_STOP_PCT:.0f}% "
            "limit. Clears at the next trading day."
        )
    return state


def clear_daily_halt(state: RiskState, new_day: date) -> RiskState:
    """A new trading day clears the daily stop. It never clears the drawdown halt."""
    if state.trading_day != new_day:
        state.trading_day = new_day
        state.realised_today = 0.0
        if state.halted and "daily loss" in state.halt_reason:
            state.halted = False
            state.halt_reason = ""
    return state


def position_size(
    state: RiskState,
    symbol: str,
    weight: float,
    price: float,
    stop_distance: float,
    contract_size: float,
    volume_min: float,
    volume_step: float,
    volume_max: float,
    existing_position: float = 0.0,
    existing_pnl: float = 0.0,
) -> float:
    """Lots to hold. Raises rather than returning a size it is not happy with.

    ``weight`` is this market's signed share of gross exposure, from the strategy.
    The risk budget is a book-level 0.5%, split by that weight — so three markets do
    not each risk 0.5%.
    """
    if state.halted:
        raise RiskRefusal(f"halted: {state.halt_reason}")
    if state.equity <= 0:
        raise RiskRefusal(f"equity is {state.equity}; refusing to size anything")
    if stop_distance <= 0:
        raise RiskRefusal(f"{symbol}: stop distance is {stop_distance}; a zero stop is not a stop")
    if price <= 0 or contract_size <= 0:
        raise RiskRefusal(f"{symbol}: price={price} contract_size={contract_size}")
    if not (0.0 < abs(weight) <= 1.0):
        raise RiskRefusal(f"{symbol}: weight {weight} is outside (0, 1]")

    # Banned by construction: never add to a position that is currently losing.
    # This is what makes martingale, grid and averaging down impossible rather than
    # merely discouraged.
    if existing_position != 0.0 and existing_pnl < 0.0:
        target_bigger = abs(weight) > abs(existing_position)
        same_side = (weight > 0) == (existing_position > 0)
        if same_side and target_bigger:
            raise RiskRefusal(
                f"{symbol}: refusing to add to a losing position "
                f"(open P&L {existing_pnl:.2f}). Averaging down is banned in code."
            )

    if state.open_positions >= MAX_CONCURRENT_POSITIONS and existing_position == 0.0:
        raise RiskRefusal(
            f"{symbol}: {state.open_positions} positions already open, "
            f"limit is {MAX_CONCURRENT_POSITIONS}"
        )

    risk_budget = state.equity * (RISK_PER_DECISION_PCT / 100.0) * abs(weight)
    value_per_unit = stop_distance * contract_size
    if value_per_unit <= 0:
        raise RiskRefusal(f"{symbol}: value per lot is {value_per_unit}")

    raw_lots = risk_budget / value_per_unit
    steps = int(raw_lots / volume_step)          # round DOWN, never up into extra risk
    lots = steps * volume_step

    if lots < volume_min:
        raise RiskRefusal(
            f"{symbol}: correct size is {raw_lots:.4f} lots but the broker minimum is "
            f"{volume_min}. Trading the minimum would risk "
            f"{volume_min * value_per_unit / state.equity * 100:.2f}% instead of "
            f"{abs(weight) * RISK_PER_DECISION_PCT:.2f}%. Refusing rather than rounding up."
        )
    if lots > volume_max:
        lots = volume_max

    return round(lots * (1 if weight > 0 else -1), 8)


# --------------------------------------------------- book-level sizing (owner-approved)
#
# Owner approved 2026-08-16, after the first paper run refused 11 of 14 legs.
#
# The 0.5%-per-trade rule was written for a bot holding ONE gold position, where each
# trade is a separate directional bet. A 14-leg market-neutral book is not that: the
# long and short legs offset, so the book's risk is far smaller than the sum of its
# legs. Splitting 0.5% fourteen ways produced legs below the broker's minimum, which
# the engine correctly refused — but the refusal was a symptom of measuring the wrong
# thing, not of the book being dangerous.
#
# What binds instead is the BOOK's volatility, targeted so that its 95th-percentile
# drawdown fits inside the owner's 20% halt. That is the same limit, applied where it
# actually describes the risk being taken.
BOOK_VOL_TARGET = 0.036
"""Book volatility target, calibrated from the bootstrap rather than chosen.

Set to 7% initially by analogy with the single-market work. P20 replayed the actual
production path and measured the 95th-percentile drawdown at that size as **38.69%**
— nearly double the owner's 20% halt. A book sized that way would trip its own halt
as a matter of routine, which makes the halt noise rather than a control.

    20.0 / 38.69 x 0.07 = 0.036

So 3.6%, which puts the p95 drawdown just inside the limit with no headroom to
spare. Note this is the 95th percentile of resampled paths, not what one history
happened to produce — F13 measured that a single path understates it by about 1.58x,
and sizing to the observed figure would breach the halt in roughly half of equally
plausible futures.
"""
MAX_LEG_NOTIONAL_MULTIPLE = 2.0
"""Hard ceiling on one leg's notional, as a multiple of account equity.

**It is a plain notional cap on purpose.** A first version expressed this ceiling as
a share of equity risked to a two-sigma move, which divides by volatility — so the
cap GREW as volatility fell, tracking the very quantity it existed to bound. It never
bound anything, and a test caught it.

Volatility targeting divides by volatility, so an instrument whose volatility
estimate collapses toward zero demands an unbounded position. Only a limit that does
not itself scale with volatility can stop that. Typical legs run near 0.2x equity, so
2.0x is generous in normal conditions and finite in broken ones — which is the whole
job.
"""


def book_leg_size(
    state: RiskState,
    symbol: str,
    weight: float,
    price: float,
    annual_vol: float,
    contract_size: float,
    volume_min: float,
    volume_step: float,
    volume_max: float,
    n_legs: int,
    book_vol_target: float = BOOK_VOL_TARGET,
) -> float:
    """Lots for one leg of a diversified book, sized by volatility contribution.

    Each leg carries roughly ``book_vol_target / sqrt(n_legs)`` of the account's
    volatility, scaled by its weight in the book. Diversification is why the divisor
    is a square root rather than ``n_legs``: legs that move independently do not add
    their risks linearly.

    Raises rather than returning a size it is unhappy with, exactly like
    ``position_size``. A leg that cannot be expressed is skipped, never rounded up.
    """
    if state.halted:
        raise RiskRefusal(f"halted: {state.halt_reason}")
    if state.equity <= 0:
        raise RiskRefusal(f"equity is {state.equity}")
    if annual_vol <= 0:
        raise RiskRefusal(f"{symbol}: annual volatility is {annual_vol}; cannot size on it")
    if price <= 0 or contract_size <= 0:
        raise RiskRefusal(f"{symbol}: price={price} contract_size={contract_size}")
    if n_legs < 1:
        raise RiskRefusal(f"n_legs is {n_legs}")

    leg_vol_usd = state.equity * book_vol_target / (n_legs ** 0.5) * abs(weight) * n_legs
    notional = leg_vol_usd / annual_vol

    # Ceiling on notional directly — see MAX_LEG_NOTIONAL_MULTIPLE for why it must not
    # be expressed in volatility-scaled units.
    notional = min(notional, state.equity * MAX_LEG_NOTIONAL_MULTIPLE)

    raw_lots = notional / (contract_size * price)
    lots = int(raw_lots / volume_step) * volume_step      # round DOWN, never up

    if lots < volume_min:
        implied = volume_min * contract_size * price * annual_vol / state.equity * 100.0
        raise RiskRefusal(
            f"{symbol}: correct size is {raw_lots:.4f} lots, broker minimum is {volume_min}. "
            f"The minimum would carry {implied:.2f}% of equity in annual volatility against "
            f"a {leg_vol_usd / state.equity * 100:.2f}% budget. Refusing rather than rounding up."
        )
    if lots > volume_max:
        lots = volume_max

    return round(lots * (1 if weight > 0 else -1), 8)


def describe_limits() -> str:
    """What actually constrains the book, stated the way it now works.

    ``MAX_CONCURRENT_POSITIONS`` deliberately does not appear. It governs
    ``position_size``, the single-position path, where three open trades are three
    separate directional bets. A cross-sectional book is one bet expressed across
    many legs, and it is constrained by book volatility and the drawdown halt
    instead. Printing a "max 3 positions" limit next to a thirteen-leg book would be
    describing a rule that is not the one in force.
    """
    return (
        f"book volatility target {BOOK_VOL_TARGET:.0%} · "
        f"per-leg ceiling {MAX_LEG_NOTIONAL_MULTIPLE:.1f}x equity notional · "
        f"daily stop {DAILY_LOSS_STOP_PCT}% · "
        f"max drawdown {MAX_DRAWDOWN_PCT}% (halt does not self-clear) · "
        f"martingale/grid/averaging-down refused in code"
    )
