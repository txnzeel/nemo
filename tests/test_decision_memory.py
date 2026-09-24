"""Memory uses only eligible, point-in-time ledger evidence."""

import copy
import hashlib
import json
from datetime import UTC, date, datetime

import pytest
from test_experiments import manual as manual
from test_ledger import board as board
from test_ledger import imported, resign
from test_outcomes import append, compute, decision, spec

from nemo.decision_case import build_case
from nemo.decision_memory import build_with_memory, main, retrieve
from nemo.ledger import read, submit


def case():
    return signed(
        {
            "schema_version": "1",
            "case_id": "DC-manual",
            "claim_type": "diagnostic_hypothesis",
            "scope": {
                "dataset_id": "manual-experiment",
                "mode": "production",
                "question": "purchasing_session_conversion",
                "baseline_start": "2025-01-10",
                "current_start": "2025-01-11",
                "end_exclusive": "2025-01-12",
            },
            "analysis_cutoff": "2025-01-12",
            "supported_devices": ["tablet"],
        }
    )


def signed(value):
    value.pop("revision_id", None)
    value["revision_id"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return value


@pytest.fixture
def history(board, manual, tmp_path):
    db = tmp_path / "ledger.sqlite"
    plan = spec()
    plan["filters"]["channel"] = None
    state = decision(db, board, plan)
    result = compute(db, state, manual)
    append(db, result)
    return db, state, result


def query(db, target=None, **kwargs):
    return retrieve(
        target or case(), db, as_of=kwargs.pop("as_of", datetime.now(UTC).isoformat()), **kwargs
    )


def test_retrieves_bounded_evidence_without_changing_case(history):
    db, _, result = history
    target = case()
    before = copy.deepcopy(target)
    value = query(db, target)
    assert target == before
    (match,) = value["matches"]
    assert match["lesson"] == result["lesson"]
    assert match["scope_match"] == "supported_device"
    assert match["record"]["evidence_available"]
    assert value["claim_type"] == "historical_review_context"
    assert value["review_questions"][0]["decision_id"] == match["decision_id"]
    assert value["summary"]["eligible"] == 1


def test_knowledge_cutoff_uses_audit_prefix(history):
    db, _, _ = history
    events = read(db)["events"]
    value = query(db, as_of=events[-2]["recorded_at"])
    assert value["matches"] == []
    assert value["provenance"]["ledger_prefix_hash"] == events[-2]["event_hash"]
    assert value["summary"]["excluded"] == {"missing_plan_or_outcome": 1}


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("source", "different_dataset_or_mode"),
        ("device", "incompatible_scope"),
        ("overlap", "overlapping_or_later_window"),
    ],
)
def test_incompatible_context_excluded(history, kind, reason):
    db, _, _ = history
    target = case()
    if kind == "source":
        target["scope"]["dataset_id"] = "another-company"
    elif kind == "device":
        target["supported_devices"] = []
    else:
        target["scope"]["baseline_start"] = "2025-01-08"
    value = query(db, signed(target))
    assert value["matches"] == []
    assert value["summary"]["excluded"][reason] == 1


def test_latest_revision_without_outcome_does_not_revive_success(history, board):
    db, _, _ = history
    newer = copy.deepcopy(board)
    newer["parameters"]["minimum_attribution_range_paise"] += 1
    submit(db, imported(resign(newer), "new-revision"))
    value = query(db)
    assert value["matches"] == []
    assert value["summary"]["revisions_collapsed"] == 1
    assert value["summary"]["excluded"] == {"missing_plan_or_outcome": 1}


def test_unresolved_outcome_is_preserved(board, manual, tmp_path):
    db = tmp_path / "ledger.sqlite"
    plan = spec()
    plan["filters"]["channel"] = None
    state = decision(db, board, plan, action="2025-01-03T00:00:00Z")
    result = compute(db, state, manual)
    append(db, result)
    value = query(db)
    (match,) = value["matches"]
    assert match["outcome_status"] == "not_ready"
    assert match["actual_outcome"] is None
    assert match["lesson"]["finding"] == "unresolved"


@pytest.mark.parametrize("limit", [0, True, 101, 1.5])
def test_invalid_limit(history, limit):
    with pytest.raises(ValueError, match="limit"):
        query(history[0], limit=limit)


def test_tampered_case_and_early_cutoff(history):
    target = case()
    target["case_id"] = "changed"
    with pytest.raises(ValueError, match="revision"):
        query(history[0], target)
    with pytest.raises(ValueError, match="precedes"):
        query(history[0], as_of="2025-01-01T00:00:00Z")


def test_wrapper_preserves_frozen_case_and_cli(history, manual, tmp_path):
    db, _, _ = history
    source, _, warehouse = manual
    params = {"baseline_start": date(2025, 1, 1), "current_start": date(2025, 1, 5)}
    value = build_with_memory(warehouse, source, db, as_of=datetime.now(UTC).isoformat(), **params)
    assert value["case"] == build_case(warehouse, source, **params)
    assert value["memory"]["matches"] == []
    args = [
        "--warehouse",
        str(warehouse),
        "--observations",
        str(source),
        "--ledger",
        str(db),
        "--baseline-start",
        "2025-01-01",
        "--current-start",
        "2025-01-05",
        "--as-of",
        datetime.now(UTC).isoformat(),
        "--output",
        str(tmp_path / "case.json"),
    ]
    assert main(args) == 0
    assert main(args) == 1
