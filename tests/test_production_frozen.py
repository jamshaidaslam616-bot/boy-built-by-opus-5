"""The shipped strategy and the risk engine, held to their stated promises.

Two things are guarded here that nothing else guards:

  * the strategy's parameters, which must not drift after freezing, and
  * the risk engine's refusals, which are the only thing standing between a bug and
    the owner's capital.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from goldlab.safety import risk
from goldlab.strategy import production as prod


def _panel(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {s: 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, n))) for s in prod.UNIVERSE},
        index=idx,
    )


# ------------------------------------------------------------ frozen parameters

def test_parameters_are_exactly_what_was_locked():
    """Locked 2026-08-14 from P15. A silent edit turns a forward test into a fit."""
    assert prod.LOOKBACK_BARS == 120
    assert prod.LEGS_PER_SIDE == 7
    assert prod.REBALANCE_BARS == 5
    assert prod.VOL_LOOKBACK_BARS == 60
    assert len(prod.UNIVERSE) == 25, "widened 19 -> 25 on 2026-08-16 after P19 measured the gain"


def test_the_strategy_never_claims_to_be_validated():
    assert "NOT VALIDATED" in prod.VALIDATION_STATUS
    assert prod.MEASURED["control_z"] < prod.MEASURED["control_bar"]


# ------------------------------------------------------------------- the book

def test_the_book_is_balanced_and_normalised():
    targets = prod.compute_targets(_panel())
    assert len(targets) == prod.LEGS_PER_SIDE * 2
    assert sum(1 for t in targets if t.weight > 0) == prod.LEGS_PER_SIDE
    assert sum(1 for t in targets if t.weight < 0) == prod.LEGS_PER_SIDE
    assert sum(abs(t.weight) for t in targets) == pytest.approx(1.0)


def test_no_single_market_can_dominate():
    """One market with a collapsed volatility estimate must not become the book."""
    panel = _panel()
    panel[prod.UNIVERSE[0]] = 100.0  # zero volatility, infinite raw weight
    targets = prod.compute_targets(panel)
    assert max(abs(t.weight) for t in targets) <= prod.MAX_LEG_WEIGHT + 1e-9


def test_targets_cannot_see_past_as_of():
    """Ranking on data after the decision bar would be look-ahead."""
    panel = _panel(500)
    cut = panel.index[300]
    a = prod.compute_targets(panel, as_of=cut)
    b = prod.compute_targets(panel.loc[:cut])
    assert [(t.symbol, round(t.weight, 12)) for t in a] == \
           [(t.symbol, round(t.weight, 12)) for t in b]


def test_refuses_an_incomplete_universe():
    panel = _panel().drop(columns=[prod.UNIVERSE[0]])
    with pytest.raises(ValueError, match="universe incomplete"):
        prod.compute_targets(panel)


# ------------------------------------------------------------- risk refusals

def _state(**kw) -> risk.RiskState:
    base = dict(equity=10_000.0, peak_equity=10_000.0)
    base.update(kw)
    return risk.RiskState(**base)


def _size(state, **kw):
    """A leg that IS sizeable on this account, so these tests exercise the logic.

    Gold deliberately is not used: P16 measured that a $10,000 account cannot hold
    gold as one leg of a diversified book at all, because the broker's minimum
    position is larger than the leg's whole risk budget. Using it here would make
    every test fail on the account constraint instead of the rule being tested.
    """
    args = dict(symbol="EURUSD", weight=0.25, price=1.155, stop_distance=0.010,
                contract_size=100_000.0, volume_min=0.01, volume_step=0.01, volume_max=200.0)
    args.update(kw)
    return risk.position_size(state, **args)


def test_owner_limits_are_the_agreed_numbers():
    assert risk.RISK_PER_DECISION_PCT == 0.5
    assert risk.DAILY_LOSS_STOP_PCT == 3.0
    assert risk.MAX_DRAWDOWN_PCT == 25.0, "10%->20% on 2026-08-10, 20%->25% on 2026-08-17, both owner-authorised"
    assert risk.MAX_CONCURRENT_POSITIONS == 3


def test_averaging_down_is_impossible():
    """The single most important refusal in the file."""
    with pytest.raises(risk.RiskRefusal, match="Averaging down is banned"):
        _size(_state(), weight=0.25, existing_position=0.10, existing_pnl=-250.0)


def test_adding_to_a_WINNING_position_is_allowed():
    """The ban is on averaging DOWN, not on scaling into something that works."""
    assert _size(_state(), weight=0.25, existing_position=0.10, existing_pnl=+250.0) > 0


def test_never_rounds_up_into_extra_risk():
    """If the correct size is below the broker minimum, refuse — do not round up."""
    with pytest.raises(risk.RiskRefusal, match="Refusing rather than rounding up"):
        _size(_state(equity=200.0), weight=0.05)


def test_gold_cannot_be_a_leg_of_a_diversified_book_on_this_account():
    """P16's finding, pinned so it cannot be forgotten.

    A 14-leg book gives each leg about a fourteenth of a 0.5% risk budget — roughly
    $3.50 on $10,000. Gold's smallest tradeable position risks far more than that,
    so the engine must refuse rather than quietly hold a position several times the
    intended size. The P15 backtest did not make this check and reported +$247 for a
    book that could not have been held.
    """
    with pytest.raises(risk.RiskRefusal, match="Refusing rather than rounding up"):
        risk.position_size(
            _state(), symbol="XAUUSD", weight=1.0 / 14, price=4342.0, stop_distance=80.0,
            contract_size=100.0, volume_min=0.01, volume_step=0.01, volume_max=200.0,
        )


def test_a_zero_stop_is_refused():
    with pytest.raises(risk.RiskRefusal, match="a zero stop is not a stop"):
        _size(_state(), stop_distance=0.0)


def test_the_risk_budget_is_split_by_weight_not_multiplied():
    """Three markets must share 0.5%, not take 0.5% each.

    The assertion is one-sided on purpose. Rounding down to the volume step means
    the realised risk is at most the budget and within one step below it — never
    above. An equality test would be asking the engine to round up, which is the one
    thing it must never do.
    """
    state = _state()
    value_per_lot = 0.010 * 100_000.0
    step_dollars = 0.01 * value_per_lot

    for weight in (1.0, 0.5, 0.25):
        budget = state.equity * 0.005 * weight
        risked = abs(_size(state, weight=weight)) * value_per_lot
        assert risked <= budget + 1e-9, (
            f"weight {weight}: risked ${risked:.2f} against a ${budget:.2f} budget — "
            "the engine rounded UP"
        )
        assert risked > budget - step_dollars, (
            f"weight {weight}: risked ${risked:.2f} against a ${budget:.2f} budget — "
            "more than one volume step is being left on the table"
        )


def test_drawdown_halt_fires_and_does_not_clear_itself():
    state = risk.check_halts(_state(equity=7_400.0, peak_equity=10_000.0))  # 26% drawdown
    assert state.halted and "drawdown" in state.halt_reason

    state = risk.clear_daily_halt(state, pd.Timestamp("2026-09-01").date())
    assert state.halted, "a new day must NOT clear the drawdown halt"

    with pytest.raises(risk.RiskRefusal, match="halted"):
        _size(state)


def test_daily_stop_fires_and_clears_next_day():
    state = risk.check_halts(_state(realised_today=-310.0))
    assert state.halted and "daily loss" in state.halt_reason

    state = risk.clear_daily_halt(state, pd.Timestamp("2026-09-02").date())
    assert not state.halted, "the daily stop clears at the next trading day"


def test_position_count_limit_blocks_a_fourth_market():
    with pytest.raises(risk.RiskRefusal, match="positions already open"):
        _size(_state(open_positions=3))


# ------------------------------------------- balance under refusals (2026-08-17)

def test_the_book_stays_balanced_when_legs_are_untradeable():
    """The first demo run held 5 long and 3 short legs — a directional bet.

    Cross-sectional momentum is market neutral by construction, and that neutrality
    is the whole reason to prefer it. Refusals must never be allowed to tilt it.
    """
    panel = _panel()
    # Block the instruments that were actually refused on 2026-08-17.
    blocked = {"XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "USOIL", "UKOIL"}
    targets = prod.compute_targets(panel, tradeable=lambda s: s not in blocked)

    longs = [t for t in targets if t.weight > 0]
    shorts = [t for t in targets if t.weight < 0]
    assert len(longs) == len(shorts), (
        f"book is {len(longs)} long against {len(shorts)} short — that is a "
        "directional bet, not a market-neutral one"
    )
    assert not any(t.symbol in blocked for t in targets), "held an untradeable leg"
    assert sum(abs(t.weight) for t in targets) == pytest.approx(1.0)


def test_substitution_reaches_further_down_the_ranking():
    """A refused leg is replaced, not left as a hole."""
    panel = _panel()
    top_two = [t.symbol for t in prod.compute_targets(panel) if t.weight > 0][:2]
    targets = prod.compute_targets(panel, tradeable=lambda s: s not in set(top_two))

    held_longs = [t.symbol for t in targets if t.weight > 0]
    assert not set(top_two) & set(held_longs)
    assert len(held_longs) == prod.LEGS_PER_SIDE, (
        "blocking two candidates should pull two substitutes in, not shrink the side"
    )


def test_no_symbol_can_appear_on_both_sides():
    """With few tradeable markets the two ends of the ranking can meet."""
    panel = _panel()
    allowed = set(list(prod.UNIVERSE)[:9])
    targets = prod.compute_targets(panel, tradeable=lambda s: s in allowed)
    symbols = [t.symbol for t in targets]
    assert len(symbols) == len(set(symbols)), "a symbol was held long and short at once"


def test_refuses_a_one_sided_book_rather_than_shipping_it():
    panel = _panel()
    with pytest.raises(ValueError, match="no balanced book is possible"):
        prod.compute_targets(panel, tradeable=lambda s: s == prod.UNIVERSE[0])
