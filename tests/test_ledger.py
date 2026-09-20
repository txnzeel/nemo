"""Decision tracking must preserve evidence and never manufacture measured outcomes."""

import copy
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_experiments import manual as manual

from nemo.experiment_design import digest, encode
from nemo.ledger import main, read, submit
from nemo.opportunities import report


@pytest.fixture(scope="module")
def board(manual):
    source, plan, database = manual
    return report(database, source, experiment_plan=plan)


def imported(board, request_id="import-1"):
    return {
        "operation": "import",
        "request_id": request_id,
        "actor": "reviewer",
        "rationale": "Capture evidence before reviewing the proposed investigation.",
        "report": copy.deepcopy(board),
        "opportunity_id": board["opportunities"][0]["opportunity_id"],
    }


def change(state, changes, request_id="update-1"):
    return {
        "operation": "update",
        "request_id": request_id,
        "actor": "owner",
        "rationale": "Human review record; no external action is executed.",
        "decision_id": state["decision_id"],
        "expected_version": state["version"],
        "changes": changes,
    }


def plan():
    return {
        "status": "accepted",
        "owner": "marketing analyst",
        "hypotheses": ["The completed experiment merits a rollout-assumption review."],
        "expected_outcome": "Identify evidence gaps; an expectation, not a measured result.",
        "measurement_window": {
            "start_inclusive": "2025-02-01T00:00:00Z",
            "end_exclusive": "2025-02-08T00:00:00Z",
        },
    }


def resign(board):
    board["revision_id"] = digest(encode({k: v for k, v in board.items() if k != "revision_id"}))
    return board


def test_manual_canonical_evidence_lifecycle_and_audit(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    command = imported(board)
    first = submit(db, command)
    state = first["decision"]
    assert state["evidence_available"] == board
    assert state["evidence_quality"] == "conditional_randomized_experiment"
    assert state["confidence"]["calibrated_probability"] is None
    accepted = submit(db, change(state, plan()))["decision"]
    started = submit(db, change(accepted, {"status": "in_progress"}, "start"))["decision"]
    done = submit(
        db,
        change(
            started,
            {
                "status": "implemented",
                "actual_action": {
                    "description": "Reviewed assumptions and recorded gaps. No rollout performed.",
                    "occurred_at": "2025-02-08T00:00:00Z",
                },
            },
            "finish",
        ),
    )["decision"]
    assert done["status"] == "implemented" and done["version"] == 4
    assert done["execution"] == "human_reported_only"
    for key in ("actual_outcome", "difference_from_expectation", "lesson"):
        assert done[key] is None
    assert done["evidence_available"] == board
    assert submit(db, command) == first  # Retry returns original receipt, not latest state.
    view = read(db, done["decision_id"])
    assert view["decisions"] == [done]
    assert len(view["events"]) == 4
    assert view["events"][0]["command"]["actor"] == "reviewer"
    assert [event["sequence"] for event in view["events"]] == [1, 2, 3, 4]


def test_snapshot_is_isolated_and_duplicate_revision_rejected(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    command = imported(board)
    initial = submit(db, command)
    command["report"]["opportunities"][0]["recommended_next_step"] = "Edited later"
    assert read(db)["decisions"][0] == initial["decision"]
    with pytest.raises(ValueError, match="already tracked"):
        submit(db, imported(board, "different-request"))
    newer = copy.deepcopy(board)
    newer["parameters"]["minimum_attribution_range_paise"] += 1
    newer = resign(newer)
    second = submit(db, imported(newer, "new-revision"))["decision"]
    assert second["opportunity_id"] == initial["decision"]["opportunity_id"]
    assert second["decision_id"] != initial["decision"]["decision_id"]
    assert len(read(db, second["decision_id"])["events"]) == 1


def test_retry_conflict_and_stale_updates_roll_back(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    command = imported(board)
    state = submit(db, command)["decision"]
    command["rationale"] = "Conflicting retry"
    with pytest.raises(ValueError, match="reused"):
        submit(db, command)
    submit(db, change(state, {"owner": "A"}))
    with pytest.raises(ValueError, match="stale"):
        submit(db, change(state, {"owner": "B"}, "stale"))
    assert len(read(db)["events"]) == 2
    assert read(db)["decisions"][0]["owner"] == "A"


def test_concurrent_reviewers_cannot_lose_updates(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    state = submit(db, imported(board))["decision"]

    def attempt(owner):
        try:
            return submit(db, change(state, {"owner": owner}, owner))["decision"]["owner"]
        except ValueError as error:
            assert "stale" in str(error)
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["A", "B"]))
    assert results.count("stale") == 1
    assert len(read(db)["events"]) == 2


@pytest.mark.parametrize("target", ["accepted", "in_progress", "implemented"])
def test_blockers_cannot_be_overridden(board, tmp_path, target):
    blocked = copy.deepcopy(board)
    blocked["opportunities"][0].update(
        status="blocked", blockers=["attribution_contract:not_assessed"]
    )
    db = tmp_path / "ledger.sqlite"
    state = submit(db, imported(resign(blocked)))["decision"]
    update = plan()
    update["status"] = target
    with pytest.raises(ValueError, match="transition"):
        submit(db, change(state, update))
    assert read(db)["decisions"][0]["blockers"] == ["attribution_contract:not_assessed"]
    rejected = submit(db, change(state, {"status": "rejected"}))["decision"]
    assert rejected["status"] == "rejected"


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "accepted"},
        {"status": "implemented"},
        {"status": "proposed"},
        {"actual_outcome": "Conversion increased"},
        {"lesson": "Scale paid search"},
        {"evidence_quality": "causal"},
        {"blockers": []},
        {"owner": ""},
        {"hypotheses": "Unstructured"},
        {"measurement_window": {"start_inclusive": "2025-01-01", "end_exclusive": "2025-01-02"}},
        {
            "measurement_window": {
                "start_inclusive": "2025-02-08T00:00:00Z",
                "end_exclusive": "2025-02-01T00:00:00Z",
            }
        },
    ],
)
def test_invalid_updates_leave_no_history(board, tmp_path, changes):
    db = tmp_path / "ledger.sqlite"
    original = submit(db, imported(board))["decision"]
    with pytest.raises(ValueError):
        submit(db, change(original, changes))
    assert read(db)["decisions"] == [original]
    assert len(read(db)["events"]) == 1


def test_frozen_plan_implementation_time_and_terminal_rules(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    state = submit(db, imported(board))["decision"]
    state = submit(db, change(state, plan()))["decision"]
    state = submit(db, change(state, {"status": "in_progress"}, "start"))["decision"]
    for changes in (
        {"owner": "new owner"},
        {"status": "implemented"},
        {
            "status": "implemented",
            "actual_action": {
                "description": "Future action",
                "occurred_at": "9999-01-01T00:00:00Z",
            },
        },
    ):
        with pytest.raises(ValueError):
            submit(db, change(state, changes, "invalid"))
    terminal = submit(db, change(state, {"status": "cancelled"}, "cancel"))["decision"]
    with pytest.raises(ValueError, match="terminal"):
        submit(db, change(terminal, {"owner": "B"}, "after"))
    assert read(db)["decisions"] == [terminal]


def test_tampered_report_and_unsupported_contract_rejected(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    tampered = copy.deepcopy(board)
    tampered["opportunities"][0]["recommended_next_step"] = "Spend more"
    with pytest.raises(ValueError, match="revision"):
        submit(db, imported(tampered))
    tampered["schema_version"] = "2"
    with pytest.raises(ValueError, match="unsupported"):
        submit(db, imported(resign(tampered)))
    assert read(db)["events"] == []


def test_database_protection_and_replay_corruption_detection(board, tmp_path):
    db = tmp_path / "ledger.sqlite"
    submit(db, imported(board))
    connection = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM events")
        connection.rollback()
        connection.execute("DROP TRIGGER no_update")
        connection.execute("UPDATE events SET event_hash = 'corrupt'")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ValueError, match="hash mismatch"):
        read(db)
    with pytest.raises(ValueError, match="hash mismatch"):
        submit(db, imported(board, "another"))


def test_cli_error_and_missing_read_do_not_create_db(tmp_path, capsys):
    db = tmp_path / "missing.sqlite"
    assert main(["--database", str(db), "read"]) == 1
    assert not db.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "error"


def test_cli_without_private_truth_or_generator(board, tmp_path):
    command_file = tmp_path / "command.json"
    command_file.write_bytes(encode(imported(board)))
    db = tmp_path / "ledger.sqlite"
    script = """
import builtins
import sys
from pathlib import Path
original = builtins.__import__
def guard(name, *args, **kwargs):
    if name in {'nemo.simulation', 'nemo.artifacts', 'nemo.cli', 'nemo.blind_lab',
                'nemo.lab_experiments'}:
        raise AssertionError('generator or lab import')
    return original(name, *args, **kwargs)
builtins.__import__ = guard
def audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = str(args[0]).replace('\\\\', '/').lower()
        if '/private/' in name or name.endswith('/run.json'):
            raise AssertionError('private truth access')
sys.addaudithook(audit)
from nemo.ledger import main
raise SystemExit(main(sys.argv[1:]))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            "--database",
            str(db),
            "submit",
            "--command",
            str(command_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    receipt = json.loads(result.stdout)
    assert receipt["decision"]["evidence_available"] == board
    assert main(["--database", str(db), "read"]) == 0
