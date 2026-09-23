"""Canonical outcomes preserve exact targets, window gates and historical decisions."""

import copy
import json
import subprocess
import sys

import pytest
from test_experiments import manual as manual
from test_ledger import board as board
from test_ledger import change, imported

from nemo import outcomes
from nemo.experiment_design import digest, encode
from nemo.ledger import read, submit
from nemo.outcome_contract import build_result, validate_plan
from nemo.outcomes import main, record, report


def spec(metric="cvr", numerator=1, denominator=2, comparator="at_least"):
    return {
        "version": "1",
        "metric": metric,
        "filters": {"channel": "direct", "device": "tablet", "campaign_id": None},
        "comparator": comparator,
        "target": {"numerator": numerator, "denominator": denominator},
    }


def plan_command(state, plan, request_id="plan"):
    return {
        "operation": "plan_outcome",
        "request_id": request_id,
        "actor": "analyst",
        "rationale": "Declare the observed target; no causal claim.",
        "decision_id": state["decision_id"],
        "expected_version": state["version"],
        "plan": plan,
    }


def decision(db, board, plan=None, *, register=True, finish=True, window=None, action=None):
    state = submit(db, imported(board))["decision"]
    state = submit(
        db,
        change(
            state,
            {
                "status": "accepted",
                "owner": "analyst",
                "expected_outcome": "Observe the declared metric target.",
                "measurement_window": window
                or {
                    "start_inclusive": "2025-01-01T18:30:00Z",
                    "end_exclusive": "2025-01-08T18:30:00Z",
                },
            },
            "accept",
        ),
    )["decision"]
    if register:
        state = submit(db, plan_command(state, plan or spec()))["decision"]
    if finish:
        state = submit(db, change(state, {"status": "in_progress"}, "start"))["decision"]
        state = submit(
            db,
            change(
                state,
                {
                    "status": "implemented",
                    "actual_action": {
                        "description": "Fixture-only reported review, no production execution.",
                        "occurred_at": action or "2025-01-01T18:00:00Z",
                    },
                },
                "finish",
            ),
        )["decision"]
    return state


def compute(db, state, manual):
    source, _, warehouse = manual
    return report(db, state["decision_id"], warehouse, source)


def append(db, result, request_id="outcome"):
    return record(
        db, result, actor="analyst", rationale="Record observed comparison.", request_id=request_id
    )


@pytest.mark.parametrize(
    "metric,target,denominator,actual,difference",
    [
        ("sessions", 300, 1, 330, 30),
        ("orders", 400, 1, 330, -70),
        ("revenue", 32999999, 1, 33000000, 1),
        ("cvr", 1, 2, 1, None),
    ],
)
def test_exact_canonical_metrics_and_ledger_lessons(
    board, manual, tmp_path, metric, target, denominator, actual, difference
):
    db = tmp_path / "ledger.sqlite"
    state = decision(db, board, spec(metric, target, denominator))
    result = compute(db, state, manual)
    assert result["status"] == "measured"
    assert result["actual_outcome"]["value"] == {"numerator": actual, "denominator": 1}
    expected = {"numerator": difference, "denominator": 1}
    if metric == "cvr":
        expected = {"numerator": 1, "denominator": 2}
    assert result["difference_from_expectation"]["value"] == expected
    assert result["lesson"]["causal_effect"] == "not_established"
    assert result["lesson"]["planning_timing"] == "retrospective_or_unplanned"
    assert result["lesson"]["measurement_health"] == "not_assessed"
    old_history = read(db)["events"]
    receipt = append(db, result)
    assert append(db, result) == receipt
    latest = read(db, state["decision_id"])["decisions"][0]
    assert latest["actual_outcome"] == result["actual_outcome"]
    assert latest["lesson"] == result["lesson"]
    assert latest["evidence_available"] == state["evidence_available"]
    assert latest["status"] == "implemented"
    assert read(db)["events"][:-1] == old_history
    assert latest["version"] == state["version"] + 1


@pytest.mark.parametrize("comparator,expected", [("at_least", "met"), ("at_most", "missed")])
def test_comparator_directions(board, manual, tmp_path, comparator, expected):
    db = tmp_path / "ledger.sqlite"
    state = decision(db, board, spec("orders", 300, 1, comparator))
    assert compute(db, state, manual)["target_assessment"] == "observed_target_" + expected


@pytest.mark.parametrize(
    "changes",
    [
        {"metric": "profit"},
        {"metric": "cac"},
        {"version": "2"},
        {"comparator": "increase"},
        {"target": {"numerator": True, "denominator": 1}},
        {"target": {"numerator": 1, "denominator": 0}},
        {"target": {"numerator": 2, "denominator": 1}},
        {"target": {"numerator": -1, "denominator": 2}},
        {"metric": "revenue", "target": {"numerator": 1, "denominator": 2}},
        {"filters": {"channel": None}},
    ],
)
def test_invalid_plans_fail(changes):
    value = spec()
    value.update(changes)
    with pytest.raises(ValueError):
        validate_plan(value)


def test_plan_freezes_window_and_cannot_be_added_after_start(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    state = decision(db, board, finish=False)
    with pytest.raises(ValueError, match="window is frozen"):
        submit(db, change(state, {"measurement_window": state["measurement_window"]}, "window"))
    amended = submit(db, plan_command(state, spec("orders", 300, 1), "amend"))["decision"]
    assert amended["outcome_plan"]["spec"]["metric"] == "orders"
    started = submit(db, change(amended, {"status": "in_progress"}, "start"))["decision"]
    with pytest.raises(ValueError, match="not started"):
        submit(db, plan_command(started, spec(), "late"))
    assert read(db)["decisions"][0] == started


def test_non_business_day_alignment_rejected(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    with pytest.raises(ValueError, match="midnight"):
        decision(
            db,
            board,
            window={
                "start_inclusive": "2025-01-02T00:00:00Z",
                "end_exclusive": "2025-01-09T00:00:00Z",
            },
        )


@pytest.mark.parametrize(
    "kind", ["unplanned", "not_implemented", "uncovered", "not_elapsed", "pre_action"]
)
def test_readiness_gates_and_no_invented_values(board, manual, tmp_path, kind):
    db = tmp_path / "ledger.sqlite"
    kwargs = {}
    blocker = {
        "unplanned": "missing_outcome_plan",
        "not_implemented": "decision_not_implemented",
        "uncovered": "source_does_not_cover_window",
        "not_elapsed": "window_not_elapsed",
        "pre_action": "window_precedes_reported_action",
    }[kind]
    if kind == "unplanned":
        kwargs["register"] = False
    elif kind == "not_implemented":
        kwargs["finish"] = False
    elif kind in {"uncovered", "not_elapsed"}:
        year = "2099" if kind == "not_elapsed" else "2025"
        kwargs["window"] = {
            "start_inclusive": year + "-02-01T18:30:00Z",
            "end_exclusive": year + "-02-08T18:30:00Z",
        }
    else:
        kwargs["action"] = "2025-01-04T00:00:00Z"
    state = decision(db, board, **kwargs)
    result = compute(db, state, manual)
    assert result["status"] == "not_ready" and blocker in result["blockers"]
    assert result["actual_outcome"] is result["difference_from_expectation"] is None
    assert result["measurement_evidence"] is None
    assert result["lesson"]["finding"] == "unresolved"
    if kind == "not_implemented":
        with pytest.raises(ValueError, match="implemented"):
            append(db, result)
    else:
        assert append(db, result)["decision"]["lesson"]["finding"] == "unresolved"


def test_zero_denominator_is_unresolved_not_zero_conversion(board, manual, tmp_path):
    db = tmp_path / "ledger.sqlite"
    state = decision(
        db,
        board,
        window={
            "start_inclusive": "2025-01-04T18:30:00Z",
            "end_exclusive": "2025-01-05T18:30:00Z",
        },
    )
    result = compute(db, state, manual)
    assert result["blockers"] == ["zero_denominator"]
    assert result["actual_outcome"] is None
    assert result["measurement_evidence"]["total"]["facts"]["sessions"] == 0
    append(db, result)


def test_tampering_stale_versions_and_new_measurement_history(board, manual, tmp_path):
    db = tmp_path / "ledger.sqlite"
    state = decision(db, board)
    result = compute(db, state, manual)
    tampered = copy.deepcopy(result)
    tampered["lesson"]["causal_effect"] = "proven"
    tampered["revision_id"] = digest(
        encode({k: v for k, v in tampered.items() if k != "revision_id"})
    )
    with pytest.raises(ValueError, match="derived claims"):
        append(db, tampered)
    append(db, result)
    with pytest.raises(ValueError, match="stale"):
        append(db, result, "stale")
    next_result = compute(db, state, manual)
    assert next_result["decision_version"] == state["version"] + 1
    append(db, next_result, "remeasure")
    events = read(db)["events"]
    assert events[-2]["command"]["report"] == result
    assert events[-1]["command"]["report"] == next_result


def test_scope_and_manifest_mismatch(board, manual, tmp_path):
    db = tmp_path / "ledger.sqlite"
    state = decision(db, board)
    result = compute(db, state, manual)
    wrong = copy.deepcopy(result["source"])
    wrong["dataset_id"] = "another-company"
    with pytest.raises(ValueError, match="dataset"):
        build_result(state, wrong, None, result["measured_at"], {})
    source = tmp_path / "wrong"
    source.mkdir()
    (source / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="warehouse"):
        report(db, state["decision_id"], manual[2], source)


def test_source_change_during_measurement_detected(board, manual, tmp_path, monkeypatch):
    db = tmp_path / "ledger.sqlite"
    state = decision(db, board)
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_bytes((manual[0] / "manifest.json").read_bytes())
    original = outcomes.measure

    def mutate(**kwargs):
        kwargs["integrity_observations"] = manual[0]
        result = original(**kwargs)
        (source / "manifest.json").write_text("{}")
        return result

    monkeypatch.setattr(outcomes, "measure", mutate)
    with pytest.raises(ValueError, match="source changed"):
        report(db, state["decision_id"], manual[2], source)


def test_prospective_label_depends_on_actual_plan_recording_time(board, manual, tmp_path):
    db = tmp_path / "ledger.sqlite"
    state = decision(db, board)
    result = compute(db, state, manual)
    # Pure contract scenario, never written to a real audit log.
    state["outcome_plan"]["recorded_at"] = "2024-12-31T00:00:00Z"
    value = build_result(
        state, result["source"], result["measurement_evidence"], result["measured_at"], {}
    )
    assert value["lesson"]["planning_timing"] == "prospective"
    assert value["lesson"]["causal_effect"] == "not_established"


def test_cli_saved_report_retry_and_no_generator_access(board, manual, tmp_path, capsys):
    db = tmp_path / "ledger.sqlite"
    state = decision(db, board)
    output = tmp_path / "outcome.json"
    script = r"""
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith('nemo.lab') or name in {'nemo.simulation', 'nemo.blind_lab'}:
        raise AssertionError('generator import')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
def audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = str(args[0]).replace('\\', '/').lower()
        if '/private/' in name or name.endswith('/run.json'):
            raise AssertionError('private truth read')
sys.addaudithook(audit)
from nemo.outcomes import main
raise SystemExit(main(sys.argv[1:]))
"""
    args = [
        "--database",
        str(db),
        "measure",
        "--decision-id",
        state["decision_id"],
        "--warehouse",
        str(manual[2]),
        "--observations",
        str(manual[0]),
        "--output",
        str(output),
    ]
    completed = subprocess.run(
        [sys.executable, "-c", script, *args], capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "measured"
    assert main(args) == 1  # Existing reports cannot be overwritten.
    capsys.readouterr()
    record_args = [
        "--database",
        str(db),
        "record",
        "--report",
        str(output),
        "--request-id",
        "cli-outcome",
        "--actor",
        "analyst",
        "--rationale",
        "Observe, not infer cause.",
    ]
    assert main(record_args) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(record_args) == 0
    assert json.loads(capsys.readouterr().out) == first
