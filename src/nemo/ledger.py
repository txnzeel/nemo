"""Local, append-only decision tracking from immutable opportunity snapshots."""

import argparse
import copy
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from nemo.experiment_design import digest, encode
from nemo.outcome_contract import SUPPORTED, business_window, validate_plan, validate_result

TRANSITIONS = {
    "proposed": {"accepted", "rejected", "cancelled"},
    "blocked": {"rejected", "cancelled"},
    "accepted": {"in_progress", "cancelled"},
    "in_progress": {"implemented", "cancelled"},
    "implemented": set(),
    "rejected": set(),
    "cancelled": set(),
}
PLAN_FIELDS = {"owner", "expected_outcome", "measurement_window", "hypotheses"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    sequence INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL,
    event_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected nonempty text")
    return value


def _time(value):
    _text(value)
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None or moment.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must have an explicit UTC offset")
    return moment


def _snapshot(board, opportunity_id):
    if not isinstance(board, dict):
        raise ValueError("opportunity report must be an object")
    unsigned = {k: v for k, v in board.items() if k != "revision_id"}
    if digest(encode(unsigned)) != board.get("revision_id"):
        raise ValueError("opportunity report revision does not match content")
    if board.get("schema_version") != "1" or board.get("claim_type") != "decision_recommendation":
        raise ValueError("unsupported opportunity contract")
    _text(board["scope"]["dataset_id"])
    _text(board["provenance"]["manifest_sha256"])
    items = board["opportunities"]
    ids = [item["opportunity_id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate opportunity IDs")
    selected = [item for item in items if item["opportunity_id"] == opportunity_id]
    if len(selected) != 1:
        raise ValueError("opportunity not found")
    item = selected[0]
    if item["status"] not in {"proposed", "blocked"}:
        raise ValueError("unsupported source status")
    if not isinstance(item["blockers"], list) or bool(item["blockers"]) != (
        item["status"] == "blocked"
    ):
        raise ValueError("source blockers and status disagree")
    if item["execution"] != "manual_review_only":
        raise ValueError("only manual review opportunities are supported")
    for key in ("business_question", "recommended_next_step", "evidence_strength"):
        _text(item[key])
    return item


def _apply(states, command, recorded_at):
    """Pure reducer used identically by writers and audit replay."""
    if not isinstance(command, dict):
        raise ValueError("command must be an object")
    for key in ("request_id", "actor", "rationale"):
        _text(command[key])
    moment = _time(recorded_at)
    op = command["operation"]
    common = {"operation", "request_id", "actor", "rationale"}
    if op == "import":
        if set(command) != common | {"report", "opportunity_id"}:
            raise ValueError("unexpected import fields")
        board = command["report"]
        item = _snapshot(board, command["opportunity_id"])
        decision_id = (
            "DEC-"
            + digest(
                encode([board["scope"]["dataset_id"], item["opportunity_id"], board["revision_id"]])
            )[:24]
        )
        if decision_id in states:
            raise ValueError("this opportunity revision is already tracked")
        state = {
            "schema_version": "1",
            "decision_id": decision_id,
            "decision_case_id": item["decision_case_id"],
            "opportunity_id": item["opportunity_id"],
            "source_revision_id": board["revision_id"],
            "created_at": recorded_at,
            "updated_at": recorded_at,
            "problem": item["business_question"],
            "evidence_available": copy.deepcopy(board),
            "evidence_quality": copy.deepcopy(item["evidence_strength"]),
            "hypotheses": [],
            "recommended_action": item["recommended_next_step"],
            "actual_action": None,
            "expected_outcome": None,
            "confidence": copy.deepcopy(item["confidence"]),
            "owner": None,
            "status": item["status"],
            "blockers": copy.deepcopy(item["blockers"]),
            "measurement_window": None,
            "actual_outcome": None,
            "difference_from_expectation": None,
            "lesson": None,
            "claim_type": "decision_tracking_record",
            "execution": "human_reported_only",
            "version": 1,
        }
    elif op == "update":
        if set(command) != common | {"decision_id", "expected_version", "changes"}:
            raise ValueError("unexpected update fields")
        state = copy.deepcopy(states[command["decision_id"]])
        version = command["expected_version"]
        if type(version) is not int or version != state["version"]:
            raise ValueError("stale or invalid expected version")
        if not TRANSITIONS[state["status"]]:
            raise ValueError("terminal decision is immutable")
        changes = command["changes"]
        if not isinstance(changes, dict) or not changes:
            raise ValueError("nonempty changes required")
        if set(changes) - (PLAN_FIELDS | {"status", "actual_action"}):
            raise ValueError("unsupported changes; evidence and outcomes are immutable")
        if set(changes) & PLAN_FIELDS and state["status"] == "in_progress":
            raise ValueError("plan is frozen after work starts")
        if "owner" in changes:
            _text(changes["owner"])
        if "expected_outcome" in changes:
            _text(changes["expected_outcome"])
        if "hypotheses" in changes:
            if not isinstance(changes["hypotheses"], list):
                raise ValueError("hypotheses must be a list of human assertions")
            for hypothesis in changes["hypotheses"]:
                _text(hypothesis)
        if "measurement_window" in changes and state.get("outcome_plan") is not None:
            raise ValueError("measurement window is frozen after outcome planning")
        if "measurement_window" in changes:
            window = changes["measurement_window"]
            if not isinstance(window, dict) or set(window) != {"start_inclusive", "end_exclusive"}:
                raise ValueError("measurement window requires UTC start and end")
            if _time(window["start_inclusive"]) >= _time(window["end_exclusive"]):
                raise ValueError("measurement window must be nonempty")
        target = changes.get("status", state["status"])
        if "status" in changes and target not in TRANSITIONS[state["status"]]:
            raise ValueError("invalid status transition")
        if "actual_action" in changes:
            action = changes["actual_action"]
            if target != "implemented" or not isinstance(action, dict):
                raise ValueError("actual action is only recorded on implementation")
            if set(action) != {"description", "occurred_at"}:
                raise ValueError("actual action requires description and occurrence time")
            _text(action["description"])
            if _time(action["occurred_at"]) > moment:
                raise ValueError("action occurrence cannot be in the future")
        state.update(copy.deepcopy(changes))
        if target in {"accepted", "in_progress", "implemented"}:
            if any(
                state[key] is None for key in ("owner", "expected_outcome", "measurement_window")
            ):
                raise ValueError("acceptance requires owner, expectation and measurement window")
        if target == "implemented" and state["actual_action"] is None:
            raise ValueError("implementation requires a reported actual action")
        state["version"] += 1
        state["updated_at"] = recorded_at
    elif op in {"plan_outcome", "record_outcome"}:
        payload_key = "plan" if op == "plan_outcome" else "report"
        if set(command) != common | {"decision_id", "expected_version", payload_key}:
            raise ValueError("unexpected outcome command fields")
        state = copy.deepcopy(states[command["decision_id"]])
        version = command["expected_version"]
        if type(version) is not int or version != state["version"]:
            raise ValueError("stale or invalid expected version")
        if op == "plan_outcome":
            if state["status"] != "accepted":
                raise ValueError("outcome planning requires accepted work that has not started")
            plan = validate_plan(command["plan"])
            business_window(state["measurement_window"])
            state["outcome_plan"] = {
                "spec": copy.deepcopy(plan),
                "recorded_at": recorded_at,
                "metric_definition": json.loads(encode(SUPPORTED[plan["metric"]].definition())),
            }
        else:
            if state["status"] != "implemented":
                raise ValueError("outcomes can only be recorded for implemented decisions")
            result = command["report"]
            validate_result(state, result, recorded_at)
            state["outcome_report"] = copy.deepcopy(result)
            for key in ("actual_outcome", "difference_from_expectation", "lesson"):
                state[key] = copy.deepcopy(result[key])
        state["version"] += 1
        state["updated_at"] = recorded_at
    else:
        raise ValueError("unsupported operation")
    states[state["decision_id"]] = state
    return copy.deepcopy(state)


def _replay(connection):
    states, receipts, history = {}, {}, []
    previous = None
    last_time = None
    for sequence, request_id, body, event_hash in connection.execute(
        "SELECT sequence, request_id, body, event_hash FROM events ORDER BY sequence"
    ):
        event = json.loads(body)
        if sequence != len(history) + 1 or digest(encode(event)) != event_hash:
            raise ValueError("ledger sequence or hash mismatch")
        if set(event) != {"command", "recorded_at", "previous_hash"}:
            raise ValueError("unsupported event envelope")
        moment = _time(event["recorded_at"])
        if event["previous_hash"] != previous or (last_time and moment < last_time):
            raise ValueError("ledger chain or timestamp mismatch")
        if event["command"]["request_id"] != request_id or request_id in receipts:
            raise ValueError("ledger request identity mismatch")
        state = _apply(states, event["command"], event["recorded_at"])
        receipt = {"sequence": sequence, "event_hash": event_hash, "decision": state}
        receipts[request_id] = (event["command"], receipt)
        history.append({**event, "sequence": sequence, "event_hash": event_hash})
        previous, last_time = event_hash, moment
    return states, receipts, history


def submit(database: Path, command: dict):
    """Atomically append a command; identical retries return their original receipt."""
    # JSON round trip isolates caller-owned mutable objects and rejects nonfinite numbers.
    command = json.loads(encode(command))
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=30)) as connection, connection:
        connection.executescript(SCHEMA)
        connection.execute("BEGIN IMMEDIATE")
        states, receipts, history = _replay(connection)
        request_id = _text(command["request_id"])
        if request_id in receipts:
            old_command, receipt = receipts[request_id]
            if old_command != command:
                raise ValueError("request ID reused with different content")
            return receipt
        now = datetime.now(UTC).isoformat()
        if history and _time(now) < _time(history[-1]["recorded_at"]):
            raise ValueError("clock moved backwards")
        state = _apply(states, command, now)
        event = {
            "command": command,
            "recorded_at": now,
            "previous_hash": history[-1]["event_hash"] if history else None,
        }
        event_hash = digest(encode(event))
        sequence = len(history) + 1
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            (sequence, request_id, encode(event).decode(), event_hash),
        )
        return {"sequence": sequence, "event_hash": event_hash, "decision": state}


def read(database: Path, decision_id=None):
    """Replay an existing ledger read-only; never create a missing ledger."""
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        states, _, history = _replay(connection)
    if decision_id is not None:
        states = {decision_id: states[decision_id]}
        history = [
            event
            for event in history
            if (
                event["command"].get("decision_id") == decision_id
                or (
                    event["command"]["operation"] == "import"
                    and event["command"]["opportunity_id"] == states[decision_id]["opportunity_id"]
                    and event["command"]["report"]["revision_id"]
                    == states[decision_id]["source_revision_id"]
                )
            )
        ]
    return {"schema_version": "1", "decisions": list(states.values()), "events": history}


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEMO local decision ledger")
    parser.add_argument("--database", type=Path, required=True)
    sub = parser.add_subparsers(dest="operation", required=True)
    submit_parser = sub.add_parser("submit")
    submit_parser.add_argument("--command", type=Path, required=True)
    read_parser = sub.add_parser("read")
    read_parser.add_argument("--decision-id")
    args = parser.parse_args(argv)
    try:
        result = (
            submit(args.database, json.loads(args.command.read_bytes()))
            if args.operation == "submit"
            else read(args.database, args.decision_id)
        )
        print(encode(result).decode(), end="")
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
