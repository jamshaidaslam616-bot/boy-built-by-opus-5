"""Paper broker: live prices, simulated fills, no orders ever sent.

It shares the decision path with everything else — the same strategy, the same risk
engine, the same journal. Only the fill is simulated, and it is simulated
pessimistically: entries pay the spread and the modelled slippage, commission is
charged wholly on open the way the account actually charges it, and financing is
booked at the rollover rather than smeared.

Erring expensive is deliberate. A paper record that flatters itself teaches nothing,
and the whole point of running this is to find out what is true.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Measured 2026-08-08/10, sources in COSTS.md.
SPREAD_BP = 0.12
COMMISSION_BP = 0.25      # $11.00/lot round turn, charged wholly on OPEN
SLIPPAGE_BP = 0.10


@dataclass
class Position:
    symbol: str
    lots: float
    entry_price: float
    opened_utc: datetime
    contract_size: float

    def notional(self, price: float) -> float:
        return abs(self.lots) * self.contract_size * price

    def unrealised(self, price: float) -> float:
        return self.lots * self.contract_size * (price - self.entry_price)

    def days_held(self, now: datetime) -> int:
        return (now - self.opened_utc).days


@dataclass
class PaperBroker:
    """Simulated fills against live prices. Cannot place a real order — there is no
    code path from here to the terminal's order functions, by construction."""

    equity: float
    positions: dict[str, Position] = field(default_factory=dict)
    realised: float = 0.0
    costs_paid: float = 0.0

    # The broker's free window, confirmed with Exness by the owner. A position held
    # longer starts paying, so the runner closes and reopens inside it.
    FREE_DAYS = 7

    def mark_to_market(self, prices: dict[str, float]) -> float:
        unrealised = sum(
            p.unrealised(prices[s]) for s, p in self.positions.items() if s in prices
        )
        return self.equity + unrealised

    def _transaction_cost(self, notional: float, opening: bool) -> float:
        """Spread and slippage on both sides; commission only on the open."""
        bp = SPREAD_BP + SLIPPAGE_BP + (COMMISSION_BP if opening else 0.0)
        return notional * bp / 10_000.0

    def open(self, symbol: str, lots: float, price: float, contract_size: float,
             now: datetime) -> float:
        if symbol in self.positions:
            raise ValueError(f"{symbol}: already open; close before reopening")
        notional = abs(lots) * contract_size * price
        cost = self._transaction_cost(notional, opening=True)
        self.equity -= cost
        self.costs_paid += cost
        self.positions[symbol] = Position(symbol, lots, price, now, contract_size)
        return cost

    def close(self, symbol: str, price: float) -> tuple[float, float]:
        position = self.positions.pop(symbol)
        pnl = position.unrealised(price)
        cost = self._transaction_cost(position.notional(price), opening=False)
        self.equity += pnl - cost
        self.realised += pnl
        self.costs_paid += cost
        return pnl, cost

    def stale_positions(self, now: datetime) -> list[str]:
        """Positions approaching the end of the financing-free window.

        Returned one day early so the runner can act before anything is charged.
        """
        return [s for s, p in self.positions.items() if p.days_held(now) >= self.FREE_DAYS - 1]
