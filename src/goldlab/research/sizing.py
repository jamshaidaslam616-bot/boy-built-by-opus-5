"""One canonical answer to "how big can this be run?".

Three scripts had grown their own copy of this, each hardcoding a 10% limit and each
comparing against the drawdown the single backtest path happened to produce. Both
of those are now wrong:

  * the live halt was raised to 20% on 2026-08-10, and
  * F13 measured that a single path understates the 95th-percentile drawdown by
    about 1.58x, so sizing against the observed figure is optimistic by that factor.

Duplicated risk logic drifts silently, and it drifts in the direction of taking more
risk than intended, because nobody notices a stale limit that permits a bigger
position. So there is one implementation and everything calls it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import Performance, max_drawdown_pct, summarise
from .returns import CostModel, strategy_returns, vol_target

# Owner-set, 2026-08-10. The live halt. Not to be raised without the owner saying so.
LIVE_HALT_PCT = 20.0

# Blocks average one month so the trend persistence that actually creates drawdowns
# survives the resampling. Day-by-day resampling would destroy it and understate risk.
BOOTSTRAP_BLOCK_BARS = 21


@dataclass(frozen=True)
class CompliantSize:
    vol_target: float
    performance: Performance
    p95_drawdown_pct: float
    observed_drawdown_pct: float

    def dollars(self, capital: float) -> float:
        return capital * self.performance.ann_return_pct / 100.0

    def worst_case_dollars(self, capital: float) -> float:
        return -capital * self.p95_drawdown_pct / 100.0


def bootstrap_max_drawdowns(
    returns: pd.Series, n_paths: int = 2_000, seed: int = 20260810
) -> np.ndarray:
    """Distribution of maximum drawdown across resampled paths of the same length."""
    values = returns.dropna().to_numpy()
    n = len(values)
    if n < BOOTSTRAP_BLOCK_BARS * 4:
        raise ValueError(f"need at least {BOOTSTRAP_BLOCK_BARS * 4} observations to bootstrap")

    rng = np.random.default_rng(seed)
    out = np.empty(n_paths)
    for path in range(n_paths):
        pieces, filled = [], 0
        while filled < n:
            start = rng.integers(0, n)
            length = min(int(rng.geometric(1.0 / BOOTSTRAP_BLOCK_BARS)), n - filled)
            pieces.append(values[(np.arange(start, start + length)) % n])
            filled += length
        out[path] = max_drawdown_pct(pd.Series(np.concatenate(pieces)[:n]))
    return out


def largest_compliant_size(
    raw_position: pd.Series,
    close: pd.Series,
    costs: CostModel,
    bars_per_year: float,
    live_halt_pct: float = LIVE_HALT_PCT,
    vol_lookback: int = 60,
    candidates: tuple[float, ...] = (0.20, 0.15, 0.12, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03),
    n_paths: int = 800,
) -> CompliantSize | None:
    """Largest volatility target whose 95th-percentile drawdown fits inside the halt.

    The p95 rather than the observed drawdown, deliberately. Sizing to what one
    historical path produced means the halt fires in roughly half of equally
    plausible futures — which is not a safety limit, it is a coin flip.

    Returns ``None`` when no tested size complies, which is a real answer and must
    not be silently replaced with the smallest candidate.
    """
    for target in candidates:
        position = vol_target(raw_position, close, target, vol_lookback, bars_per_year)
        net = strategy_returns(position, close, costs)
        p95 = float(np.percentile(bootstrap_max_drawdowns(net, n_paths=n_paths), 95))
        if p95 <= live_halt_pct:
            perf = summarise(net, bars_per_year)
            return CompliantSize(
                vol_target=target,
                performance=perf,
                p95_drawdown_pct=p95,
                observed_drawdown_pct=perf.max_drawdown_pct,
            )
    return None
