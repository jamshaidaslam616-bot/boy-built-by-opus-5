"""The harness is tested before anything is tested WITH it.

Two obligations, and they pull in opposite directions:

  1. It must FIND an edge that is genuinely there   (no false negatives)
  2. It must find NOTHING in a random series        (no false positives)

A harness that only satisfies (1) is a machine for approving strategies. A harness
that only satisfies (2) rejects everything and is equally useless. Both tests live
here permanently, and every future result rests on them still passing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from goldlab.research.control import run_all_controls
from goldlab.research.metrics import (
    annualised_to_per_bar_sharpe_variance,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    sharpe_ratio,
)
from goldlab.research.returns import CostModel, strategy_returns, turnover
from goldlab.research.splits import assert_no_overlap, purged_walk_forward, walk_forward_efficiency

BARS_PER_YEAR = 252.0
N_BARS = 5000


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2015-01-01", periods=n, freq="D", tz="UTC")


def random_walk(n: int, seed: int, sigma: float = 0.01) -> pd.Series:
    """A price series with no serial structure whatsoever."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, sigma, size=n)
    return pd.Series(100.0 * np.exp(np.cumsum(returns)), index=_index(n))


def planted_momentum(n: int, seed: int, strength: float = 0.20, sigma: float = 0.01) -> pd.Series:
    """A price series with a REAL, known momentum edge deliberately planted in it.

    ``r[t] = strength * sigma * sign(r[t-1]) + sigma * noise``

    A rule that goes long after an up bar and short after a down bar earns
    ``strength * sigma`` per bar against a standard deviation of ``sigma``, so its
    per-bar Sharpe is approximately ``strength``. This is the positive control:
    if the harness cannot see this, it cannot see anything.
    """
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, sigma, size=n)
    returns = np.zeros(n)
    returns[0] = noise[0]
    for t in range(1, n):
        returns[t] = strength * sigma * np.sign(returns[t - 1]) + noise[t]
    return pd.Series(100.0 * np.exp(np.cumsum(returns)), index=_index(n))


def momentum_position(close: pd.Series) -> pd.Series:
    """Long after an up bar, short after a down bar.

    Uses only bar t's close to decide the position held over bar t+1; the framework
    applies the lag, so this function does not need to (and must not) shift.
    """
    return np.sign(close.pct_change()).fillna(0.0)


def free_costs() -> CostModel:
    return CostModel(
        spread_bp=0.0, commission_bp=0.0, slippage_bp=0.0,
        carry_long_annual_pct=0.0, carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR,
    )


# ---------------------------------------------------------------- obligation 1

def test_harness_finds_a_planted_edge():
    """A real, known edge must clear the controls decisively."""
    close = planted_momentum(N_BARS, seed=1)
    pos = momentum_position(close)

    results = run_all_controls(pos, close, BARS_PER_YEAR, n_controls=100, seed=7)
    rotation = next(r for r in results if r.method == "rotation")

    assert rotation.z_score >= 2.0, (
        f"harness failed to detect a deliberately planted edge (z={rotation.z_score:.2f}). "
        "It cannot be trusted to detect a real one."
    )
    assert rotation.percentile > 95.0
    assert sharpe_ratio(strategy_returns(pos, close), BARS_PER_YEAR) > 1.0


def test_planted_edge_also_clears_deflated_sharpe():
    """The planted edge must survive a realistic multiple-testing penalty."""
    close = planted_momentum(N_BARS, seed=2)
    net = strategy_returns(momentum_position(close), close)

    from goldlab.research.metrics import per_bar_sharpe, summarise

    perf = summarise(net, BARS_PER_YEAR)
    # 50 trials whose ANNUALISED Sharpes span roughly -0.5..+0.5 give a variance
    # near 0.09; deflation works in per-bar units, so convert rather than guess.
    trial_var = annualised_to_per_bar_sharpe_variance(0.09, BARS_PER_YEAR)
    dsr, sr0 = deflated_sharpe_ratio(
        observed_sharpe=per_bar_sharpe(net),
        n_obs=perf.n_obs,
        skew=perf.skew,
        kurtosis=perf.kurtosis,
        n_trials=50,
        sharpe_variance_across_trials=trial_var,
    )
    assert dsr >= 0.95, (
        f"planted edge should survive deflation over 50 trials, got DSR={dsr:.4f} "
        f"against luck benchmark {sr0:.4f}/bar"
    )


def test_mixing_sharpe_units_is_refused_not_absorbed():
    """Passing an annualised trial variance must raise, not silently fail everything.

    This footgun was found by the planted-edge test failing: an annualised variance
    used as a per-bar one pushes the luck benchmark above any real edge, so the
    harness rejects everything — and a harness that rejects everything looks
    rigorous rather than broken.
    """
    with pytest.raises(ValueError, match="implausibly large"):
        deflated_sharpe_ratio(
            observed_sharpe=0.05, n_obs=2000, skew=0.0, kurtosis=3.0,
            n_trials=50, sharpe_variance_across_trials=0.09,  # annualised, unconverted
        )


# ---------------------------------------------------------------- obligation 2

def test_harness_finds_nothing_in_a_random_walk():
    """With a fixed seed, the same rule on structureless data must not pass."""
    close = random_walk(N_BARS, seed=1)
    pos = momentum_position(close)

    rotation = next(
        r for r in run_all_controls(pos, close, BARS_PER_YEAR, n_controls=100, seed=7)
        if r.method == "rotation"
    )
    assert rotation.z_score < 2.0, (
        f"harness found an 'edge' (z={rotation.z_score:.2f}) in a pure random walk. "
        "Any result it produces would be noise wearing a suit."
    )


def test_false_positive_rate_is_controlled():
    """Across many random series, few must pass. This measures the false-positive rate.

    A +2 sigma threshold implies roughly 2.5% one-sided false positives, so a
    handful out of 30 is expected and acceptable; a large fraction would mean the
    control distribution is mis-estimated.
    """
    passes = 0
    for seed in range(30):
        close = random_walk(1500, seed=1000 + seed)
        pos = momentum_position(close)
        rotation = next(
            r for r in run_all_controls(pos, close, BARS_PER_YEAR, n_controls=60, seed=seed)
            if r.method == "rotation"
        )
        passes += int(rotation.z_score >= 2.0)

    assert passes <= 5, (
        f"{passes}/30 random series passed the control gate. The threshold is not "
        "protecting against luck."
    )


def test_costs_turn_a_coin_flip_into_a_loss():
    """Zero edge plus real costs must be a losing strategy — never break-even."""
    close = random_walk(N_BARS, seed=3)
    pos = momentum_position(close)  # flips often, so it pays the spread often

    costly = CostModel(
        spread_bp=1.2, commission_bp=2.5, slippage_bp=0.5,
        carry_long_annual_pct=-5.66, carry_short_annual_pct=0.0,
        bars_per_year=BARS_PER_YEAR,
    )
    net = strategy_returns(pos, close, costly)
    gross = strategy_returns(pos, close, None)

    assert net.sum() < gross.sum(), "costs must reduce returns"
    assert net.sum() < 0, "a no-edge strategy paying real costs must lose money"


# ------------------------------------------------------- structural guarantees

def test_returns_cannot_see_the_future():
    """Changing a future price must not change a past return.

    This is the truncation-invariance property. Look-ahead is dangerous precisely
    because it makes a backtest look BETTER, so it cannot be spotted by reading the
    output — it has to be proved.
    """
    close = random_walk(500, seed=5)
    pos = momentum_position(close)
    base = strategy_returns(pos, close, free_costs())

    tampered = close.copy()
    tampered.iloc[400:] *= 1.5  # violently change the future
    tampered_pos = momentum_position(tampered)
    after = strategy_returns(tampered_pos, tampered, free_costs())

    pd.testing.assert_series_equal(
        base.iloc[:399], after.iloc[:399],
        check_exact=False, rtol=1e-12,
        obj="returns before bar 400 changed when prices AFTER bar 400 were altered",
    )


def test_position_is_lagged_by_exactly_one_bar():
    """A position taken at bar t earns bar t+1's move, never bar t's."""
    close = pd.Series([100.0, 110.0, 121.0], index=_index(3))
    pos = pd.Series([1.0, 0.0, 0.0], index=close.index)  # long over bar 1 only

    net = strategy_returns(pos, close, None)
    assert net.iloc[0] == pytest.approx(0.0), "bar 0 cannot earn anything; we entered at its close"
    assert net.iloc[1] == pytest.approx(0.10), "the position from bar 0 must earn bar 1's +10%"
    assert net.iloc[2] == pytest.approx(0.0), "we were flat over bar 2"


def test_turnover_charges_a_reversal_twice():
    """Flipping -1 to +1 crosses two full positions' worth of spread."""
    close = random_walk(10, seed=6)
    pos = pd.Series([0, 1, 1, -1, 0, 0, 0, 0, 0, 0], index=close.index, dtype=float)
    t = turnover(pos)
    assert t.iloc[1] == pytest.approx(1.0)
    assert t.iloc[2] == pytest.approx(0.0), "holding costs no turnover"
    assert t.iloc[3] == pytest.approx(2.0), "a reversal is two units of turnover"


# --------------------------------------------------------------- split hygiene

def test_walk_forward_folds_never_overlap():
    folds = purged_walk_forward(
        _index(4000), n_folds=4, lookback_bars=50, holding_bars=20, min_train_bars=800
    )
    assert len(folds) == 4
    assert_no_overlap(folds)


def test_asking_for_n_folds_returns_n_folds_or_raises():
    """Never silently return fewer folds than requested.

    The first version reserved only ``min_train_bars`` before the first test block,
    so the purge ate into it and fold 0 was dropped without a word. Aggregate
    out-of-sample counts computed from a quietly shortened fold list are wrong in
    the direction that looks fine.
    """
    folds = purged_walk_forward(
        _index(4000), n_folds=4, lookback_bars=50, holding_bars=20, min_train_bars=800
    )
    assert len(folds) == 4

    # 810 bars cannot hold 800 training + a 20-bar purge + 4 test blocks.
    with pytest.raises(ValueError, match="cannot support|clean training bars"):
        purged_walk_forward(
            _index(810), n_folds=4, lookback_bars=50, holding_bars=20, min_train_bars=800
        )


def test_purge_actually_removes_the_boundary_bars():
    holding = 30
    folds = purged_walk_forward(
        _index(4000), n_folds=3, lookback_bars=10, holding_bars=holding, min_train_bars=800
    )
    for f in folds:
        gap_days = (f.test[0] - f.train[-1]).days  # bars are daily in this fixture
        assert gap_days >= holding, (
            f"fold {f.index}: only {gap_days} days between train end and test start; "
            f"the {holding}-bar outcome window leaks across the boundary"
        )


def test_efficiency_excludes_folds_with_no_in_sample_edge():
    """A fold with no in-sample edge must be excluded, never counted as zero.

    Dividing by a near-zero in-sample Sharpe produced an 'efficiency' of -172 on a
    previous project. That was a broken measurement, not a broken strategy.
    """
    eff, excluded = walk_forward_efficiency(
        in_sample_sharpes=[0.01, 1.0, 0.9],
        out_sample_sharpes=[-3.0, 0.5, 0.45],
    )
    assert excluded == [0], "the negligible-edge fold must be excluded"
    assert eff == pytest.approx(0.5, abs=0.01), "and must not drag the mean"


def test_efficiency_is_none_when_nothing_had_an_edge():
    eff, excluded = walk_forward_efficiency([0.01, 0.02], [5.0, -5.0])
    assert eff is None, "must report NOT MEASURABLE rather than invent a number"
    assert excluded == [0, 1]


# ------------------------------------------------------------ deflation itself

def test_more_trials_raise_the_bar():
    """Searching harder must make it harder to pass. That is the entire point."""
    v = 0.01
    bars = [expected_max_sharpe(n, v) for n in (1, 10, 100, 1000)]
    assert bars == sorted(bars), "the luck benchmark must increase with trial count"
    assert bars[0] == 0.0, "a single trial has no selection bias to remove"
    assert bars[-1] > bars[1]


def test_deflation_rejects_a_marginal_result_found_after_many_tries():
    """The same Sharpe passes as a first guess and fails as the best of 200."""
    common = dict(observed_sharpe=0.05, n_obs=2000, skew=0.0, kurtosis=3.0,
                  sharpe_variance_across_trials=0.0025)
    few, _ = deflated_sharpe_ratio(n_trials=1, **common)
    many, _ = deflated_sharpe_ratio(n_trials=200, **common)

    assert few > many, "deflation must penalise the wider search"
    assert few >= 0.95, "an unsearched result at this Sharpe should stand"
    assert many < 0.95, "the same number, found after 200 tries, should not"
