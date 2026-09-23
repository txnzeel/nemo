"""Measure implemented decisions through existing canonical metric semantics."""

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.experiment_design import digest, encode
from nemo.ledger import read, submit
from nemo.measurement import measure
from nemo.outcome_contract import build_result, readiness
from nemo.warehouse import open_warehouse


def now():
    return datetime.now(UTC).isoformat()


def report(database, decision_id, warehouse, observations):
    state = read(database, decision_id)["decisions"][0]
    measured_at = now()
    with open_warehouse(warehouse) as snapshot:
        source = {
            "dataset_id": snapshot.contract.dataset_id,
            "mode": snapshot.contract.mode,
            "start_inclusive": snapshot.start.isoformat(),
            "end_exclusive": snapshot.end.isoformat(),
            "manifest_sha256": snapshot.manifest_sha256,
        }
    if digest((observations / "manifest.json").read_bytes()) != source["manifest_sha256"]:
        raise ValueError("observations do not match warehouse")
    code = {
        name: digest(files("nemo").joinpath(name).read_bytes())
        for name in ("outcomes.py", "outcome_contract.py")
    }
    blockers, dates = readiness(state, source, measured_at)
    evidence = None
    if not blockers:
        plan = state["outcome_plan"]["spec"]
        evidence = measure(
            warehouse=warehouse,
            integrity_observations=observations,
            start=dates[0],
            end=dates[1],
            group_by=(),
            **plan["filters"],
        )
    result = build_result(state, source, evidence, measured_at, code)
    if digest((observations / "manifest.json").read_bytes()) != source["manifest_sha256"]:
        raise ValueError("source changed during outcome measurement")
    return json.loads(encode(result))


def record(database, result, *, actor, rationale, request_id):
    return submit(
        database,
        {
            "operation": "record_outcome",
            "request_id": request_id,
            "actor": actor,
            "rationale": rationale,
            "decision_id": result["decision_id"],
            "expected_version": result["decision_version"],
            "report": result,
        },
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEMO descriptive decision outcomes")
    parser.add_argument("--database", type=Path, required=True)
    sub = parser.add_subparsers(dest="operation", required=True)
    measure_parser = sub.add_parser("measure")
    measure_parser.add_argument("--decision-id", required=True)
    measure_parser.add_argument("--warehouse", type=Path, required=True)
    measure_parser.add_argument("--observations", type=Path, required=True)
    measure_parser.add_argument("--output", type=Path)
    record_parser = sub.add_parser("record")
    record_parser.add_argument("--report", type=Path, required=True)
    record_parser.add_argument("--request-id", required=True)
    record_parser.add_argument("--actor", required=True)
    record_parser.add_argument("--rationale", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "measure":
            result = report(args.database, args.decision_id, args.warehouse, args.observations)
            if args.output:
                with args.output.open("xb") as stream:
                    stream.write(encode(result))
        else:
            result = record(
                args.database,
                json.loads(args.report.read_bytes()),
                actor=args.actor,
                rationale=args.rationale,
                request_id=args.request_id,
            )
        print(encode(result).decode(), end="")
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
