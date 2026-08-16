"""Performance metrics, including the one that accounts for how hard we searched.

The headline metric of this project is not the Sharpe ratio. It is the **Deflated
Sharpe Ratio**: the probability that an observed Sharpe is real, given how many
strategies were tried before this one looked good.

Try fifty strategies on the same data and one will clear any fixed bar by luck —
the way one of fifty coin-flippers will hit eight straight heads. Deflation is the
arithmetic that removes that flatterer, and it is why every trial in this project
is counted rather than quietly forgotten.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

EULER_MASCHERONI = 0.5772156649015329


@dataclass(frozen=True)
class Performance:
    n_obs: int
    ann_return_pct: float
    ann_vol_pct: float
    sharpe: float
    max_drawdown_pct: float
    profit_factor: float
    hit_rate_pct: float
    skew: float
    kurtosis: float
    turnover_per_year: float

    def as_row(self) -> dict[str, float]:
        return {
            "n_obs": self.n_obs,
            "ann_return_%": round(self.ann_return_pct, 3),
            "ann_vol_%": round(self.ann_vol_pct, 3),
            "sharpe": round(self.sharpe, 4),
            "max_dd_%": round(self.max_drawdown_pct, 3),
            "profit_factor": round(self.profit_factor, 4),
            "hit_rate_%": round(self.hit_rate_pct, 2),
            "turnover/yr": round(self.turnover_per_year, 1),
        }


def max_drawdown_pct(returns: pd.Series) -> float:
    curve = (1.0 + returns.fillna(0.0)).cumprod()
    peak = curve.cummax()
    return float(((curve / peak) - 1.0).min() * -100.0)


def sharpe_ratio(returns: pd.Series, bars_per_year: float) -> float:
    """Annualised Sharpe. Zero excess-return assumption is stated, not hidden.

    Returns 0.0 rather than infinity for a zero-variance series — a strategy that
    never moves has no risk-adjusted return, and NaN here poisons every aggregate.
    """
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(r.mean() / sd * math.sqrt(bars_per_year))


def profit_factor(returns: pd.Series) -> float:
    r = returns.dropna()
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def summarise(
    returns: pd.Series,
    bars_per_year: float,
    turnover: pd.Series | None = None,
) -> Performance:
    r = returns.dropna()
    n = len(r)
    if n == 0:
        raise ValueError("cannot summarise an empty return series")

    ann_vol = float(r.std(ddof=1) * math.sqrt(bars_per_year) * 100.0)
    years = n / bars_per_year
    total_growth = float((1.0 + r).prod())
    ann_ret = ((total_growth ** (1.0 / years)) - 1.0) * 100.0 if years > 0 and total_growth > 0 else -100.0

    active = r[r != 0]
    return Performance(
        n_obs=n,
        ann_return_pct=ann_ret,
        ann_vol_pct=ann_vol,
        sharpe=sharpe_ratio(r, bars_per_year),
        max_drawdown_pct=max_drawdown_pct(r),
        profit_factor=profit_factor(r),
        hit_rate_pct=float((active > 0).mean() * 100.0) if len(active) else 0.0,
        skew=float(stats.skew(r)) if n > 2 else 0.0,
        kurtosis=float(stats.kurtosis(r, fisher=False)) if n > 3 else 3.0,
        turnover_per_year=float(turnover.sum() / years) if turnover is not None and years > 0 else float("nan"),
    )


def annualised_to_per_bar_sharpe_variance(
    annualised_variance: float, bars_per_year: float
) -> float:
    """Convert a variance of ANNUALISED trial Sharpes into per-bar units.

    Exists because mixing the two units is the easiest way to break deflation, and
    it breaks it silently in the direction that looks rigorous: an annualised
    variance passed as a per-bar one inflates the luck benchmark by roughly
    ``bars_per_year``, so the harness rejects everything, including real edges.

    Concretely: 50 trials whose annualised Sharpes span about -0.5..+0.5 have an
    annualised variance near 0.09, which is a per-bar variance of 0.00036 on daily
    bars — two and a half orders of magnitude apart.
    """
    if bars_per_year <= 0:
        raise ValueError("bars_per_year must be positive")
    return annualised_variance / bars_per_year


def expected_max_sharpe(n_trials: int, sharpe_variance_across_trials: float) -> float:
    """The Sharpe you expect from the LUCKIEST of ``n_trials`` worthless strategies.

    Bailey & López de Prado (2014). This is the bar a real edge has to clear: not
    zero, but whatever noise alone would have produced given how many times we looked.

    ``sharpe_variance_across_trials`` is in **per-bar** units, matching
    ``per_bar_sharpe``. Use ``annualised_to_per_bar_sharpe_variance`` if what you
    have is annualised.
    """
    if n_trials < 1:
        raise ValueError("n_trials must be at least 1")
    if sharpe_variance_across_trials < 0:
        raise ValueError("sharpe variance cannot be negative")
    if n_trials == 1:
        return 0.0

    sd = math.sqrt(sharpe_variance_across_trials)
    a = stats.norm.ppf(1.0 - 1.0 / n_trials)
    b = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return sd * ((1.0 - EULER_MASCHERONI) * a + EULER_MASCHERONI * b)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_obs: int,
    skew: float,
    kurtosis: float,
    n_trials: int,
    sharpe_variance_across_trials: float,
) -> tuple[float, float]:
    """Probability the observed Sharpe reflects a real edge, not the best of N tries.

    ``observed_sharpe`` and the returned threshold are per-observation (NOT
    annualised) — annualising both sides would cancel, but mixing them silently
    inflates the result, so this function demands the raw figure.

    Returns ``(dsr, benchmark_sharpe)``. A DSR above 0.95 is the usual bar; this
    project treats **DSR > 0.95** as the pass and reports the number either way.

    Non-normal returns are handled explicitly: negative skew and fat tails make a
    Sharpe *less* trustworthy, and the denominator below encodes that.
    """
    if n_obs < 2:
        raise ValueError("need at least 2 observations")

    # Per-bar Sharpes live in roughly [-0.3, 0.3]. A trial variance above 0.01
    # (sd > 0.1/bar, i.e. ~1.6 annualised on daily data) almost always means an
    # annualised figure was passed by mistake. That failure mode is invisible —
    # it just makes everything fail deflation, which reads as rigour.
    if sharpe_variance_across_trials > 0.01:
        raise ValueError(
            f"sharpe_variance_across_trials={sharpe_variance_across_trials:.4g} is implausibly "
            "large for PER-BAR Sharpes. This is almost certainly an annualised variance; "
            "convert it with annualised_to_per_bar_sharpe_variance() first. Passing it "
            "unconverted silently rejects every strategy, including real ones."
        )

    sr0 = expected_max_sharpe(n_trials, sharpe_variance_across_trials)

    variance_term = 1.0 - skew * observed_sharpe + ((kurtosis - 1.0) / 4.0) * observed_sharpe**2
    if variance_term <= 0:
        # Extreme skew/kurtosis relative to the Sharpe: the estimator is unusable
        # rather than merely uncertain. Report no confidence, do not fabricate one.
        return 0.0, sr0

    z = (observed_sharpe - sr0) * math.sqrt(n_obs - 1) / math.sqrt(variance_term)
    return float(stats.norm.cdf(z)), sr0


def per_bar_sharpe(returns: pd.Series) -> float:
    """Sharpe without annualisation — what ``deflated_sharpe_ratio`` expects."""
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(r.mean() / sd)
