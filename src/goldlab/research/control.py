"""The null-hypothesis control: is this strategy distinguishable from luck?

A profit factor of 1.15 sounds like an edge until you learn that a strategy taking
1.5R targets wins 40% of the time with **no signal at all**, purely from the exit
geometry. Every headline number a backtest produces has a component that comes from
the trade structure and the asset's own drift rather than from the entry rule.

This module measures that component directly. It builds strategies that keep
everything about the candidate except its alignment with the market, and asks where
the real one sits in that distribution.

The bar: **z >= +2.0** against the control distribution. Two previously-built
strategies on this owner's data scored +0.27 and +0.75 — both looked profitable in
places, and neither was distinguishable from a coin.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import sharpe_ratio


@dataclass(frozen=True)
class ControlResult:
    method: str
    n_controls: int
    strategy_sharpe: float
    control_mean: float
    control_std: float
    z_score: float
    percentile: float

    @property
    def passes(self) -> bool:
        """+2 standard deviations. Stated here so it cannot drift between reports."""
        return self.z_score >= 2.0

    def report(self) -> str:
        verdict = "PASS" if self.passes else "FAIL"
        return (
            f"  [{verdict}] {self.method:<18} strategy SR {self.strategy_sharpe:+.4f} vs "
            f"control {self.control_mean:+.4f} +/- {self.control_std:.4f}  "
            f"z={self.z_score:+.2f}  pct={self.percentile:.1f}"
        )


def circular_shift_controls(
    position: pd.Series,
    n_controls: int,
    seed: int,
    min_shift_frac: float = 0.05,
) -> list[pd.Series]:
    """Controls that preserve **everything** about the position series but its timing.

    Rotating the position series keeps the exact same trade count, holding periods,
    position sizes, autocorrelation, session concentration and long/short balance.
    The only thing destroyed is the alignment between the signal and the returns it
    claims to predict.

    This makes it the strictest of the controls here: if a strategy beats its own
    rotations, the advantage cannot be attributed to its trade structure, because
    the controls have an identical one.
    """
    n = len(position)
    if n < 20:
        raise ValueError("need at least 20 bars to build rotation controls")
    rng = np.random.default_rng(seed)
    low = max(1, int(n * min_shift_frac))
    high = n - low
    if high <= low:
        raise ValueError("series too short for a meaningful rotation")

    values = position.fillna(0.0).to_numpy()
    shifts = rng.integers(low, high, size=n_controls)
    return [pd.Series(np.roll(values, int(s)), index=position.index) for s in shifts]


def sign_flip_controls(
    position: pd.Series,
    n_controls: int,
    seed: int,
) -> list[pd.Series]:
    """Controls that keep exposure timing and size, but randomise direction.

    Isolates a narrower question than rotation: does the entry rule know *which
    way* to bet, given that it has already chosen *when* to bet? A strategy can
    pass this and fail rotation (its timing was the edge) or vice versa.
    """
    rng = np.random.default_rng(seed)
    values = position.fillna(0.0).to_numpy()
    out = []
    for _ in range(n_controls):
        signs = rng.choice([-1.0, 1.0], size=len(values))
        out.append(pd.Series(values * signs, index=position.index))
    return out


def block_bootstrap_controls(
    position: pd.Series,
    n_controls: int,
    seed: int,
    block_bars: int,
) -> list[pd.Series]:
    """Controls built by resampling contiguous blocks of the position series.

    Preserves short-run structure inside a block while destroying it across blocks.
    Complements rotation: rotation preserves the series exactly, this one preserves
    only its local character, so together they bracket how much of the result
    depends on the precise sequence.
    """
    if block_bars < 2:
        raise ValueError("block_bars must be at least 2")
    rng = np.random.default_rng(seed)
    values = position.fillna(0.0).to_numpy()
    n = len(values)
    n_blocks = int(np.ceil(n / block_bars))

    out = []
    for _ in range(n_controls):
        starts = rng.integers(0, max(1, n - block_bars), size=n_blocks)
        sampled = np.concatenate([values[s : s + block_bars] for s in starts])[:n]
        out.append(pd.Series(sampled, index=position.index))
    return out


def evaluate_against_controls(
    strategy_position: pd.Series,
    controls: list[pd.Series],
    close: pd.Series,
    bars_per_year: float,
    method: str,
    costs=None,
) -> ControlResult:
    """Score the strategy against its own controls, on identical costs and data."""
    from .returns import strategy_returns  # local import: avoids a cycle

    if not controls:
        raise ValueError("no controls supplied")

    strat_sr = sharpe_ratio(strategy_returns(strategy_position, close, costs), bars_per_year)
    control_srs = np.array(
        [sharpe_ratio(strategy_returns(c, close, costs), bars_per_year) for c in controls]
    )

    mean = float(control_srs.mean())
    std = float(control_srs.std(ddof=1))

    if std == 0 or not np.isfinite(std):
        # Every control produced the same Sharpe — usually an all-flat position.
        # A z-score is undefined; say so rather than dividing by ~0 and reporting
        # a spectacular number, which is exactly the bug that produced a
        # "walk-forward efficiency" of -172 on the previous project.
        z = 0.0
    else:
        z = (strat_sr - mean) / std

    return ControlResult(
        method=method,
        n_controls=len(controls),
        strategy_sharpe=strat_sr,
        control_mean=mean,
        control_std=std,
        z_score=float(z),
        percentile=float((control_srs < strat_sr).mean() * 100.0),
    )


def run_all_controls(
    strategy_position: pd.Series,
    close: pd.Series,
    bars_per_year: float,
    n_controls: int = 100,
    seed: int = 20260808,
    costs=None,
    block_bars: int = 32,
) -> list[ControlResult]:
    """All three controls. A candidate must clear **rotation**; the others inform.

    Rotation is the gate because it is the only one whose controls are, trade for
    trade, the same strategy as the candidate.
    """
    return [
        evaluate_against_controls(
            strategy_position,
            circular_shift_controls(strategy_position, n_controls, seed),
            close, bars_per_year, "rotation", costs,
        ),
        evaluate_against_controls(
            strategy_position,
            sign_flip_controls(strategy_position, n_controls, seed + 1),
            close, bars_per_year, "sign-flip", costs,
        ),
        evaluate_against_controls(
            strategy_position,
            block_bootstrap_controls(strategy_position, n_controls, seed + 2, block_bars),
            close, bars_per_year, "block-bootstrap", costs,
        ),
    ]
