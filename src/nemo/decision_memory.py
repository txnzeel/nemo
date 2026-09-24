"""Auditable prior outcomes alongside an unchanged observation-only Decision Case."""

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import date, datetime, time
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.decision_case import build_case
from nemo.experiment_design import digest, encode
from nemo.ledger import _apply, read
from nemo.observations import BUSINESS_ZONE
from nemo.outcome_contract import utc


def retrieve(case, database, *, as_of, limit=10):
    cutoff = utc(as_of)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("memory limit must be an integer from 1 to 100")
    unsigned = {k: v for k, v in case.items() if k != "revision_id"}
    expected = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if expected != case["revision_id"]:
        raise ValueError("Decision Case revision does not match content")
    scope = case["scope"]
    if scope["question"] != "purchasing_session_conversion":
        raise ValueError("memory currently supports conversion Decision Cases")
    baseline = date.fromisoformat(scope["baseline_start"])
    current = date.fromisoformat(scope["current_start"])
    end = date.fromisoformat(scope["end_exclusive"])
    if not baseline < current < end:
        raise ValueError("invalid case windows")
    if cutoff < _boundary(end):
        raise ValueError("knowledge cutoff precedes case observation end")
    states, prefix = {}, []
    for event in read(database)["events"]:
        if utc(event["recorded_at"]) <= cutoff:
            _apply(states, event["command"], event["recorded_at"])
            prefix.append(event)
    latest = {}
    source_decisions = 0
    excluded = {}
    for state in states.values():
        source = state["evidence_available"]["scope"]
        if source["dataset_id"] != scope["dataset_id"] or source["source_mode"] != scope["mode"]:
            excluded["different_dataset_or_mode"] = excluded.get("different_dataset_or_mode", 0) + 1
            continue
        source_decisions += 1
        key = state["opportunity_id"]
        if key not in latest or (state["created_at"], state["decision_id"]) > (
            latest[key]["created_at"],
            latest[key]["decision_id"],
        ):
            latest[key] = state

    def reject(reason):
        excluded[reason] = excluded.get(reason, 0) + 1

    matches = []
    for state in latest.values():
        plan = state.get("outcome_plan")
        outcome = state.get("outcome_report")
        if plan is None or outcome is None:
            reject("missing_plan_or_outcome")
            continue
        spec = plan["spec"]
        if spec["metric"] != "cvr":
            reject("different_metric")
            continue
        filters = spec["filters"]
        if filters["channel"] is not None or filters["campaign_id"] is not None:
            reject("incompatible_scope")
            continue
        device = filters["device"]
        if device is not None and device not in case["supported_devices"]:
            reject("incompatible_scope")
            continue
        if utc(state["measurement_window"]["end_exclusive"]) > _boundary(baseline):
            reject("overlapping_or_later_window")
            continue
        matches.append(
            {
                "decision_id": state["decision_id"],
                "decision_version": state["version"],
                "opportunity_id": state["opportunity_id"],
                "source_revision_id": state["source_revision_id"],
                "scope_match": "whole_dataset" if device is None else "supported_device",
                "filters": filters,
                "measurement_window": state["measurement_window"],
                "outcome_revision_id": outcome["revision_id"],
                "outcome_status": outcome["status"],
                "actual_outcome": state["actual_outcome"],
                "difference_from_expectation": state["difference_from_expectation"],
                "lesson": state["lesson"],
                "record": state,
            }
        )
    matches.sort(
        key=lambda m: (utc(m["measurement_window"]["end_exclusive"]), m["decision_id"]),
        reverse=True,
    )
    selected = matches[:limit]
    result = {
        "schema_version": "1",
        "claim_type": "historical_review_context",
        "case_id": case["case_id"],
        "case_revision_id": case["revision_id"],
        "knowledge_as_of": as_of,
        "policy": "same_source_cvr_scope_prior_window_latest_opportunity_revision_v1",
        "matches": selected,
        "summary": {
            "eligible": len(matches),
            "returned": len(selected),
            "truncated": len(matches) > limit,
            "revisions_collapsed": source_decisions - len(latest),
            "excluded": excluded,
        },
        "review_questions": [
            {
                "decision_id": m["decision_id"],
                "question": (
                    "Compare this prior outcome's population, measurement health and action "
                    "with the current case before reusing its lesson."
                ),
            }
            for m in selected
        ],
        "provenance": {
            "visible_ledger_events": len(prefix),
            "ledger_prefix_hash": prefix[-1]["event_hash"] if prefix else None,
            "code_sha256": digest(files("nemo").joinpath("decision_memory.py").read_bytes()),
        },
        "limitations": [
            "Historical outcomes are review context, not causal evidence or action authorization.",
            "No learned ranking, calibrated similarity or success probability is claimed.",
            "Ledger actors, source identity and reported actions remain assertions.",
            "Current findings, recommendations and measurement gates are unchanged.",
        ],
    }
    result["revision_id"] = digest(encode(result))
    return json.loads(encode(result))


def _boundary(day):
    return datetime.combine(day, time(), BUSINESS_ZONE)


def build_with_memory(
    warehouse, observations, database, *, baseline_start, current_start, as_of, limit=10
):
    case = build_case(
        warehouse, observations, baseline_start=baseline_start, current_start=current_start
    )
    return {"case": case, "memory": retrieve(case, database, as_of=as_of, limit=limit)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="NEMO Decision Cases with auditable prior outcomes"
    )
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--baseline-start", type=date.fromisoformat, required=True)
    parser.add_argument("--current-start", type=date.fromisoformat, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_with_memory(
            args.warehouse,
            args.observations,
            args.ledger,
            baseline_start=args.baseline_start,
            current_start=args.current_start,
            as_of=args.as_of,
            limit=args.limit,
        )
        with args.output.open("xb") as stream:
            stream.write(encode(result))
        print(json.dumps({"output": str(args.output), **result["memory"]["summary"]}))
        return 0
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        RuntimeError,
        sqlite3.Error,
        duckdb.Error,
    ) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
