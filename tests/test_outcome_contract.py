"""Pure outcome/ledger contract tests; warehouse integration lives in test_outcomes."""

import copy
import json
from datetime import UTC, datetime

import pytest

from nemo.experiment_design import digest, encode
from nemo.ledger import _apply, read, submit
from nemo.metrics import FACTS, REGISTRY
from nemo.outcome_contract import (
    SUPPORTED,
    build_result,
    business_window,
    fraction,
    validate_plan,
    validate_result,
)


def source():
    return {
        "dataset_id": "manual-company",
        "mode": "production",
        "start_inclusive": "2025-01-01",
        "end_exclusive": "2025-01-09",
        "manifest_sha256": "a" * 64,
    }


def spec():
    return {
        "version": "1",
        "metric": "cvr",
        "filters": {"channel": None, "device": None, "campaign_id": None},
        "comparator": "at_least",
        "target": {"numerator": 1, "denominator": 5},
    }


def state():
    return {
        "decision_id": "manual-decision",
        "version": 5,
        "updated_at": "2025-01-01T18:00:00Z",
        "status": "implemented",
        "actual_action": {"description": "Reported change", "occurred_at": "2025-01-01T18:00:00Z"},
        "evidence_available": {
            "scope": {"dataset_id": "manual-company", "source_mode": "production"}
        },
        "measurement_window": {
            "start_inclusive": "2025-01-01T18:30:00Z",
            "end_exclusive": "2025-01-08T18:30:00Z",
        },
        "outcome_plan": {
            "spec": spec(),
            "recorded_at": "2024-12-31T00:00:00Z",
            "metric_definition": SUPPORTED["cvr"].definition(),
        },
    }


def evidence():
    facts = dict.fromkeys(FACTS, 0)
    facts.update(sessions=100, purchasing_sessions=21, orders=21, revenue_paise=2100000)
    return {
        "window": {"start_inclusive": "2025-01-02", "end_exclusive": "2025-01-09"},
        "filters": spec()["filters"],
        "dataset_id": "manual-company",
        "mode": "production",
        "measurement_health": "low",
        "provenance": {"manifest_sha256": "a" * 64},
        "total": {"facts": facts, "metrics": {m.name: m.evaluate(facts) for m in REGISTRY}},
    }


def test_exact_percentage_point_difference_and_health_preserved():
    value = build_result(state(), source(), evidence(), "2025-01-09T00:00:00Z", {})
    assert value["actual_outcome"]["value"] == {"numerator": 21, "denominator": 100}
    assert value["difference_from_expectation"]["value"] == {"numerator": 1, "denominator": 100}
    assert value["target_assessment"] == "observed_target_met"
    assert value["lesson"]["measurement_health"] == "low"
    assert value["lesson"]["planning_timing"] == "prospective"
    validate_result(state(), value, "2025-01-10T00:00:00Z")


@pytest.mark.parametrize("field", ["window", "filters", "dataset_id", "mode", "provenance"])
def test_wrong_measurement_scope_rejected(field):
    value = evidence()
    value[field] = {"wrong": True} if isinstance(value[field], dict) else "wrong"
    with pytest.raises((ValueError, KeyError)):
        build_result(state(), source(), value, "2025-01-09T00:00:00Z", {})


def test_arithmetic_tampering_and_float_facts_rejected():
    value = evidence()
    value["total"]["metrics"]["cvr"]["numerator"] = 100
    with pytest.raises(ValueError, match="arithmetic"):
        build_result(state(), source(), value, "2025-01-09T00:00:00Z", {})
    value = evidence()
    value["total"]["facts"]["purchasing_sessions"] = 21.0
    with pytest.raises(ValueError, match="integer"):
        build_result(state(), source(), value, "2025-01-09T00:00:00Z", {})


def test_pending_window_rejects_supplied_values_and_makes_no_comparison():
    with pytest.raises(ValueError, match="ineligible"):
        build_result(state(), source(), evidence(), "2025-01-08T18:29:59Z", {})
    pending = build_result(state(), source(), None, "2025-01-08T18:29:59Z", {})
    assert pending["blockers"] == ["window_not_elapsed"]
    assert pending["actual_outcome"] is None
    complete = build_result(state(), source(), evidence(), "2025-01-08T18:30:00Z", {})
    assert complete["status"] == "measured"


def test_decision_binding_and_claim_replay():
    value = build_result(state(), source(), evidence(), "2025-01-09T00:00:00Z", {})
    for field, replacement in (
        ("decision_version", 99),
        ("decision_sha256", "wrong"),
        ("target_assessment", "causal_success"),
        ("actual_outcome", None),
    ):
        edited = copy.deepcopy(value)
        edited[field] = replacement
        with pytest.raises(ValueError, match="derived claims"):
            validate_result(state(), edited, "2025-01-10T00:00:00Z")
    with pytest.raises(ValueError, match="before it was computed"):
        validate_result(state(), value, "2025-01-08T00:00:00Z")
    newer = state()
    newer["updated_at"] = "2025-01-10T00:00:00Z"
    with pytest.raises(ValueError, match="predates"):
        validate_result(newer, value, "2025-01-11T00:00:00Z")


@pytest.mark.parametrize(
    "value", [0.2, {"numerator": True, "denominator": 5}, {"numerator": 1, "denominator": 0}]
)
def test_exact_target_types(value):
    with pytest.raises(ValueError):
        fraction(value)


def test_plan_schema_and_business_boundary():
    validate_plan(spec())
    assert [d.isoformat() for d in business_window(state()["measurement_window"])] == [
        "2025-01-02",
        "2025-01-09",
    ]
    invalid = spec()
    invalid["metric"] = "incremental_profit"
    with pytest.raises(ValueError, match="unsupported"):
        validate_plan(invalid)
    with pytest.raises(ValueError, match="midnight"):
        business_window(
            {
                "start_inclusive": "2025-01-02T00:00:00Z",
                "end_exclusive": "2025-01-09T00:00:00Z",
            }
        )


def test_plan_and_outcome_events_persist_without_warehouse_runtime(tmp_path):
    # A manually authored report contract for reducer testing, not an analytical result.
    board = {
        "schema_version": "1",
        "claim_type": "decision_recommendation",
        "scope": {"dataset_id": "manual-company", "source_mode": "production"},
        "provenance": {"manifest_sha256": "a" * 64},
        "opportunities": [
            {
                "opportunity_id": "OP-manual",
                "decision_case_id": None,
                "status": "proposed",
                "blockers": [],
                "execution": "manual_review_only",
                "business_question": "What observations follow the reported review?",
                "recommended_next_step": "Review evidence.",
                "evidence_strength": "measurement_assessment",
                "confidence": {"calibrated_probability": None},
            }
        ],
    }
    board["revision_id"] = digest(encode(board))
    db = tmp_path / "ledger.sqlite"
    command = {
        "operation": "import",
        "actor": "analyst",
        "rationale": "Contract test",
        "request_id": "import",
        "report": board,
        "opportunity_id": "OP-manual",
    }
    current = submit(db, command)["decision"]

    def send(operation, key, payload):
        nonlocal current
        cmd = {
            "operation": operation,
            "actor": "analyst",
            "rationale": "Contract test",
            "request_id": str(current["version"]),
            "decision_id": current["decision_id"],
            "expected_version": current["version"],
            key: payload,
        }
        receipt = submit(db, cmd)
        assert submit(db, cmd) == receipt
        current = receipt["decision"]

    send(
        "update",
        "changes",
        {
            "status": "accepted",
            "owner": "analyst",
            "expected_outcome": "Reach the specified target.",
            "measurement_window": state()["measurement_window"],
        },
    )
    send("plan_outcome", "plan", spec())
    send("update", "changes", {"status": "in_progress"})
    send("update", "changes", {"status": "implemented", "actual_action": state()["actual_action"]})
    result = build_result(current, source(), evidence(), datetime.now(UTC).isoformat(), {})
    send("record_outcome", "report", result)
    assert current["actual_outcome"]["value"] == {"numerator": 21, "denominator": 100}
    assert read(db)["decisions"] == [current]
    assert read(db) == json.loads(encode(read(db)))
    assert len(read(db)["events"]) == 6
    with pytest.raises(ValueError, match="terminal"):
        send("update", "changes", {"owner": "someone else"})
    assert len(read(db)["events"]) == 6


def test_old_reducer_records_have_no_added_fields():
    # Old record shapes must not change merely because M13 exists.
    states = {
        "legacy": {
            "decision_id": "legacy",
            "version": 1,
            "status": "proposed",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    }
    result = _apply(
        states,
        {
            "operation": "update",
            "request_id": "update",
            "actor": "analyst",
            "rationale": "Old command",
            "decision_id": "legacy",
            "expected_version": 1,
            "changes": {"status": "cancelled"},
        },
        "2025-01-02T00:00:00Z",
    )
    assert "outcome_plan" not in result and "outcome_report" not in result
