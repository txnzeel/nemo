"""Atomic canonical pipeline publication, independent of scheduler and data producer."""

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date
from importlib.metadata import version
from pathlib import Path

import duckdb

from nemo.analyst import explain
from nemo.decision_case import build_case
from nemo.integrity import assess
from nemo.observations import REQUIRED_TABLES, open_snapshot
from nemo.warehouse import build_warehouse, project_hash

REPORTS = ("case.json", "measurement.json", "analyst.json")
METHOD_FILES = (
    "pipeline.py",
    "analyst.py",
    "canonical.py",
    "observations.py",
    "integrity.py",
    "decision_case.py",
    "warehouse.py",
    "measurement.py",
    "metrics.py",
    "acquisition.sql",
    "funnel.sql",
)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def method():
    root = Path(__file__).parent
    return {
        "files": {name: sha((root / name).read_bytes()) for name in METHOD_FILES},
        "dbt": project_hash(),
        "runtime": {name: version(name) for name in ("duckdb", "dbt-core", "dbt-duckdb")},
        "python": ".".join(map(str, sys.version_info[:3])),
    }


def verify(directory):
    manifest = json.loads((directory / "publication.json").read_bytes())
    if manifest.get("schema_version") != "1" or set(manifest["files"]) != set(REPORTS):
        raise ValueError("invalid publication contract")
    if manifest.get("run_id") != sha(encode(manifest["identity"])):
        raise ValueError("publication identity mismatch")
    for name in REPORTS:
        target = directory / name
        if target.is_symlink() or sha(target.read_bytes()) != manifest["files"][name]:
            raise ValueError("published report checksum mismatch")
    return manifest


def run(config):
    if not isinstance(config, dict) or set(config) != {
        "observations",
        "output",
        "baseline_start",
        "current_start",
    }:
        raise ValueError("unsupported pipeline configuration")
    source, output = Path(config["observations"]), Path(config["output"])
    if not source.is_absolute() or not output.is_absolute():
        raise ValueError("pipeline paths must be absolute")
    baseline = date.fromisoformat(config["baseline_start"])
    current = date.fromisoformat(config["current_start"])
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".pipeline.lock"
    # Exclusive output ownership: an existing lock is never silently removed.
    handle = lock.open("x")
    try:
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=output) as temporary:
            workspace = Path(temporary)
            snapshot = workspace / "observations"
            snapshot.mkdir()
            shutil.copyfile(source / "manifest.json", snapshot / "manifest.json")
            tables = json.loads((snapshot / "manifest.json").read_bytes())["tables"]
            for name in (*REQUIRED_TABLES, "events"):
                if name in tables:
                    shutil.copyfile(source / (name + ".jsonl"), snapshot / (name + ".jsonl"))
            with open_snapshot(snapshot) as observed:
                source_hash = observed.manifest_sha256
            # Event validation happens before any replay shortcut.
            health = assess(snapshot)
            identity = {
                "source_manifest": source_hash,
                "method": method(),
                "baseline_start": baseline.isoformat(),
                "current_start": current.isoformat(),
            }
            run_id = sha(encode(identity))
            destination = output / run_id
            if destination.exists():
                publication = verify(destination)
                if publication["identity"] != identity:
                    raise ValueError("existing publication does not match requested run")
                build_warehouse(snapshot, output / "warehouse.duckdb")
                return {"status": "unchanged", "run_id": run_id}
            database = output / "warehouse.duckdb"
            build_warehouse(snapshot, database)
            case = build_case(database, snapshot, baseline_start=baseline, current_start=current)
            reports = {"case.json": case, "measurement.json": health, "analyst.json": explain(case)}
            pending = workspace / "publication"
            pending.mkdir()
            hashes = {}
            for name, value in reports.items():
                payload = encode(value)
                (pending / name).write_bytes(payload)
                hashes[name] = sha(payload)
            publication = {
                "schema_version": "1",
                "run_id": run_id,
                "identity": identity,
                "files": hashes,
                "action_authorization": False,
            }
            (pending / "publication.json").write_bytes(encode(publication))
            verify(pending)
            pending.rename(destination)
            return {"status": "published", "run_id": run_id}
    finally:
        handle.close()
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--verify")
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_bytes())
        if args.verify is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", args.verify):
                raise ValueError("invalid run identity")
            output = Path(config["output"])
            if not output.is_absolute():
                raise ValueError("absolute publication root required")
            publication = verify(output / args.verify)
            if publication["run_id"] != args.verify:
                raise ValueError("publication path mismatch")
            result = {"status": "verified", "run_id": args.verify}
        else:
            result = run(config)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        RuntimeError,
        sqlite3.Error,
        duckdb.Error,
        subprocess.TimeoutExpired,
    ):
        print(
            '{"status":"error","message":"Pipeline failed; inspect input, lock and validation"}',
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
