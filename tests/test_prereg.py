"""The pre-registration log must be impossible to quietly rewrite.

Its whole value is that "we expected this all along" becomes a checkable claim.
That only holds if editing history is detectable, so tampering is what these tests
are mostly about.
"""

from __future__ import annotations

import json

import pytest

from goldlab.research.prereg import Hypothesis, PreRegistrationLog, Result


def make_hypothesis(name: str = "A1-trend-daily", combos: int = 12) -> Hypothesis:
    return Hypothesis(
        name=name,
        family="A1",
        claim="Daily gold returns exhibit positive serial dependence over 20-100 day horizons.",
        economic_rationale=(
            "Slow diffusion of macro information (real yields, central bank flows) into a "
            "market with heterogeneous participant horizons produces under-reaction."
        ),
        pass_criteria={"control_z": 2.0, "deflated_sharpe": 0.95, "wf_efficiency": 0.50},
        n_param_combinations=combos,
        data_scope="XAUUSD D1, 2018-01-02..2026-08-07, Exness Zero",
        predicted_outcome="Weak positive edge, likely below the deflated-Sharpe bar.",
    )


def test_registering_then_recording_a_result(tmp_path):
    log = PreRegistrationLog(tmp_path / "prereg.jsonl")
    log.register(make_hypothesis())
    log.record_result(Result("A1-trend-daily", "FAIL", {"control_z": 0.4}, "indistinguishable"))

    ok, msg = log.verify()
    assert ok, msg
    assert len(log.entries()) == 2


def test_cannot_record_a_result_for_an_unregistered_hypothesis(tmp_path):
    """No retro-fitting a hypothesis around a result that already exists."""
    log = PreRegistrationLog(tmp_path / "prereg.jsonl")
    with pytest.raises(ValueError, match="no pre-registration found"):
        log.record_result(Result("never-registered", "PASS", {}, ""))


def test_cannot_re_register_the_same_hypothesis(tmp_path):
    """Re-registering after seeing a result is the exact behaviour this prevents."""
    log = PreRegistrationLog(tmp_path / "prereg.jsonl")
    log.register(make_hypothesis())
    with pytest.raises(ValueError, match="already registered"):
        log.register(make_hypothesis(combos=999))


def test_editing_a_past_entry_is_detected(tmp_path):
    """Quietly softening a prediction after the fact must break the chain."""
    path = tmp_path / "prereg.jsonl"
    log = PreRegistrationLog(path)
    log.register(make_hypothesis())
    log.record_result(Result("A1-trend-daily", "FAIL", {"control_z": 0.4}, "no edge"))
    assert log.verify()[0]

    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["payload"]["predicted_outcome"] = "I predicted it would fail, obviously."
    lines[0] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, msg = log.verify()
    assert not ok
    assert "modified after writing" in msg


def test_deleting_an_entry_is_detected(tmp_path):
    """Dropping a failed trial would understate the multiple-testing penalty."""
    path = tmp_path / "prereg.jsonl"
    log = PreRegistrationLog(path)
    log.register(make_hypothesis("first"))
    log.register(make_hypothesis("second"))
    log.register(make_hypothesis("third"))

    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")

    ok, msg = log.verify()
    assert not ok
    assert "sequence number" in msg


def test_trial_count_accumulates_every_registration_including_failures(tmp_path):
    """The deflation N counts everything tried. Forgetting failures is the bias."""
    log = PreRegistrationLog(tmp_path / "prereg.jsonl")
    log.register(make_hypothesis("A1-trend", combos=12))
    log.register(make_hypothesis("B3-spread", combos=16))
    log.register(make_hypothesis("C2-vol", combos=8))
    log.record_result(Result("A1-trend", "FAIL", {}, ""))

    assert log.trial_count() == 36, "failed hypotheses still count as trials"


def test_empty_log_verifies_clean(tmp_path):
    ok, msg = PreRegistrationLog(tmp_path / "nothing.jsonl").verify()
    assert ok
    assert "0 entries" in msg
