"""Blind Lab orchestration and scoring. This evaluation-side module may read truth."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime, time, timedelta
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

from nemo.observations import BUSINESS_ZONE, REQUIRED_TABLES, open_snapshot
from nemo.warehouse import project_hash

SPLITS = ("development", "calibration", "held_out")
RECIPE = ((101, "android"), (202, "desktop"), (303, "android"))
START, ONSET, END = date(2026, 5, 1), date(2026, 5, 29), date(2026, 6, 12)
CUTOFFS = (ONSET, ONSET + timedelta(days=7), END)
KINDS = {
    "healthy": "no_signal",
    "failure": "measurement_issue",
    "business": "payment_stage_hypothesis",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def write_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encode(value))


def method_fingerprint():
    names = (
        "canonical.py",
        "observations.py",
        "metrics.py",
        "measurement.py",
        "integrity.py",
        "warehouse.py",
        "decision_case.py",
        "acquisition.sql",
        "funnel.sql",
        "blind_worker.py",
    )
    return {
        "code": {name: digest(files("nemo").joinpath(name).read_bytes()) for name in names},
        "dbt_project": project_hash(),
        "runtime": {name: version(name) for name in ("duckdb", "dbt-core", "dbt-duckdb")},
        "python": sys.version,
    }


def crop_snapshot(source: Path, destination: Path, cutoff: date):
    """Materialize event-time history through cutoff, excluding future rows before analysis."""
    with open_snapshot(source) as snapshot:
        if not snapshot.start < cutoff <= snapshot.end:
            raise ValueError("cutoff must be inside source history")
        manifest = json.loads((source / "manifest.json").read_bytes())
        rows = {}
        for table in (*REQUIRED_TABLES, "events"):
            payload = (source / f"{table}.jsonl").read_bytes()
            entry = manifest["tables"][table]
            if digest(payload) != entry["sha256"] or len(payload.splitlines()) != entry["rows"]:
                raise ValueError("source checksum/count mismatch before cropping")
            rows[table] = [json.loads(line) for line in payload.splitlines()]
        boundary = datetime.combine(cutoff, time(), BUSINESS_ZONE)
        rows["customers"] = [
            r for r in rows["customers"] if datetime.fromisoformat(r["first_seen_at"]) < boundary
        ]
        rows["sessions"] = [
            r for r in rows["sessions"] if datetime.fromisoformat(r["started_at"]) < boundary
        ]
        session_ids = {r["session_id"] for r in rows["sessions"]}
        rows["orders"] = [
            r
            for r in rows["orders"]
            if datetime.fromisoformat(r["paid_at"]) < boundary and r["session_id"] in session_ids
        ]
        order_ids = {r["order_id"] for r in rows["orders"]}
        rows["ad_performance"] = [
            r for r in rows["ad_performance"] if r["business_date"] < cutoff.isoformat()
        ]
        rows["events"] = [
            r
            for r in rows["events"]
            if datetime.fromisoformat(r["occurred_at"]) < boundary
            and r["session_id"] in session_ids
            and (r.get("order_id") is None or r["order_id"] in order_ids)
        ]
        manifest["observation_window"]["end_date_exclusive"] = cutoff.isoformat()
        manifest["measurement_contract"]["complete_through"] = boundary.astimezone(UTC).isoformat()
        manifest["tables"] = {}
        destination.mkdir(parents=True, exist_ok=False)
        for table, data in rows.items():
            payload = b"".join(json.dumps(row, sort_keys=True).encode() + b"\n" for row in data)
            (destination / f"{table}.jsonl").write_bytes(payload)
            manifest["tables"][table] = {"rows": len(data), "sha256": digest(payload)}
        write_new(destination / "manifest.json", manifest)
    with open_snapshot(destination):
        pass


def prepare(root: Path):
    """Producer/evaluator side only. Never export seeds, labels or onset to the worker."""
    from nemo.artifacts import write_world
    from nemo.contracts import SimulationConfig
    from nemo.lab_payment import plant_payment_problem
    from nemo.simulation import generate

    root.mkdir(parents=True, exist_ok=False)
    frozen_method = method_fingerprint()
    trials, truths = [], {}
    for split, (seed, device) in zip(SPLITS, RECIPE, strict=True):
        world = root / "private" / split / "world"
        write_world(generate(SimulationConfig(seed=seed, start_date=START, end_date=END)), world)
        branches = root / "private" / split / "branches"
        plant_payment_problem(world / "observations", branches, device=device, start=ONSET, end=END)
        for branch, target in KINDS.items():
            for cutoff in CUTOFFS:
                trial_id = f"t{len(trials) + 1:04d}"
                source = root / "inputs" / trial_id / "observations"
                crop_snapshot(branches / branch / "observations", source, cutoff)
                trials.append(
                    {
                        "trial_id": trial_id,
                        "split": split,
                        "baseline_start": (cutoff - timedelta(days=28)).isoformat(),
                        "current_start": (cutoff - timedelta(days=14)).isoformat(),
                        "cutoff": cutoff.isoformat(),
                        "manifest_sha256": digest((source / "manifest.json").read_bytes()),
                    }
                )
                active = branch != "healthy" and cutoff > ONSET
                truths[trial_id] = {
                    "expected": target if active else "no_signal",
                    "device": device if active and branch == "business" else None,
                    "onset": ONSET.isoformat() if branch != "healthy" else None,
                    "scenario": f"{split}:{branch}",
                    "world": split,
                    "cutoff": cutoff.isoformat(),
                    "condition": branch,
                }
    truth = {"version": "1", "trials": truths, "recipe": dict(zip(SPLITS, RECIPE, strict=True))}
    write_new(root / "private" / "truth.json", truth)
    protocol = {
        "version": "1",
        "trials": trials,
        "method": frozen_method,
        "truth_sha256": digest(encode(truth)),
        "policy": "Frozen M5 detector; no threshold tuning in M6.",
        "scoring": "Diagnosis, recall, false positives, localization, routing and checkpoint lag.",
    }
    write_new(root / "protocol.json", protocol)
    return {"trials": len(trials), "worlds": len(RECIPE), "root": str(root.absolute())}


def protocol(root):
    data = (root / "protocol.json").read_bytes()
    value = json.loads(data)
    if value.get("version") != "1" or any(t["split"] not in SPLITS for t in value["trials"]):
        raise ValueError("unsupported protocol")
    ids = [trial["trial_id"] for trial in value["trials"]]
    if len(ids) != len(set(ids)) or any(
        not identifier.startswith("t") or not identifier[1:].isdigit() for identifier in ids
    ):
        raise ValueError("invalid or duplicated trial identities")
    return value, digest(data)


def predict(root: Path, split: str):
    spec, spec_hash = protocol(root)
    if split not in SPLITS:
        raise ValueError("unknown split")
    if method_fingerprint() != spec["method"]:
        raise ValueError("detector changed after freeze; create a new benchmark")
    seal_path = root / "predictions" / split / "seal.json"
    if seal_path.exists():
        verify_seal(root, split)
        return {"status": "already_sealed", "split": split}
    entries = []
    for trial in (t for t in spec["trials"] if t["split"] == split):
        trial_id = trial["trial_id"]
        source = root / "inputs" / trial_id / "observations"
        if digest((source / "manifest.json").read_bytes()) != trial["manifest_sha256"]:
            raise ValueError("trial source changed after freeze")
        # Validate checksums before copying only declared public files into a generic folder.
        with open_snapshot(source):
            pass
        target = root / "predictions" / split / f"{trial_id}.json"
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix="nemo-blind-") as directory:
                workspace = Path(directory)
                copied = workspace / "observations"
                copied.mkdir()
                for name in (
                    "manifest.json",
                    *(f"{t}.jsonl" for t in (*REQUIRED_TABLES, "events")),
                ):
                    shutil.copyfile(source / name, copied / name)
                args = [
                    sys.executable,
                    "-m",
                    "nemo.blind_worker",
                    "--workspace",
                    str(workspace),
                    "--baseline-start",
                    trial["baseline_start"],
                    "--current-start",
                    trial["current_start"],
                ]
                result = subprocess.run(
                    args, cwd=workspace, capture_output=True, text=True, timeout=240
                )
                log = root / "predictions" / split / f"{trial_id}.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text(result.stdout + result.stderr, encoding="utf-8")
                if result.returncode:
                    raise RuntimeError(f"prediction worker failed for {trial_id}; see {log}")
                case = json.loads((workspace / "case.json").read_bytes())
                dbt_results = json.loads(
                    (workspace / "warehouse-dbt" / "target" / "run_results.json").read_bytes()
                )
                dbt_target = target.with_suffix(".dbt.json")
                if dbt_target.exists():
                    if json.loads(dbt_target.read_bytes()) != dbt_results:
                        # An interrupted attempt may have a different invocation timestamp.
                        raise ValueError("partial prediction receipt exists; use a new benchmark")
                else:
                    write_new(dbt_target, dbt_results)
                write_new(target, case)
        case_bytes = target.read_bytes()
        validate_case(json.loads(case_bytes), trial, spec["method"])
        entries.append(
            {
                "trial_id": trial_id,
                "sha256": digest(case_bytes),
                "dbt_sha256": digest(target.with_suffix(".dbt.json").read_bytes()),
            }
        )
        print(json.dumps({"split": split, "completed": len(entries)}), flush=True)
    if not entries:
        raise ValueError("empty split")
    write_new(seal_path, {"version": "1", "protocol_sha256": spec_hash, "entries": entries})
    return {"status": "sealed", "split": split, "predictions": len(entries)}


def validate_case(case, trial, method):
    revision = case["revision_id"]
    without_revision = {k: v for k, v in case.items() if k != "revision_id"}
    canonical = json.dumps(
        without_revision, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if digest(canonical) != revision:
        raise ValueError("case revision checksum mismatch")
    if (
        case["provenance"]["manifest_sha256"] != trial["manifest_sha256"]
        or case["scope"]["baseline_start"] != trial["baseline_start"]
        or case["scope"]["current_start"] != trial["current_start"]
        or case["analysis_cutoff"] != trial["cutoff"]
    ):
        raise ValueError("case scope/source does not match frozen trial")
    for key, expected in method["code"].items():
        if key == "blind_worker.py":
            continue
        hashes = case["provenance"]["code_sha256"] | case["provenance"]["case_code_sha256"]
        if hashes.get(key) != expected:
            raise ValueError("case method does not match frozen detector")
    if case["provenance"]["dbt_project_sha256"] != method["dbt_project"]:
        raise ValueError("case dbt model mismatch")


def verify_seal(root, split):
    spec, spec_hash = protocol(root)
    seal_bytes = (root / "predictions" / split / "seal.json").read_bytes()
    seal = json.loads(seal_bytes)
    expected = {t["trial_id"]: t for t in spec["trials"] if t["split"] == split}
    ids = [entry["trial_id"] for entry in seal["entries"]]
    if (
        seal["protocol_sha256"] != spec_hash
        or len(ids) != len(set(ids))
        or set(ids) != set(expected)
    ):
        raise ValueError("seal must cover every frozen trial exactly once")
    cases = {}
    for entry in seal["entries"]:
        trial_id = entry["trial_id"]
        data = (root / "predictions" / split / f"{trial_id}.json").read_bytes()
        if digest(data) != entry["sha256"]:
            raise ValueError("sealed prediction changed")
        dbt_bytes = (root / "predictions" / split / f"{trial_id}.dbt.json").read_bytes()
        if digest(dbt_bytes) != entry["dbt_sha256"]:
            raise ValueError("sealed dbt receipt changed")
        dbt_results = json.loads(dbt_bytes)["results"]
        if len(dbt_results) != 36 or any(
            r["status"] not in ("success", "pass") for r in dbt_results
        ):
            raise ValueError("prediction requires successful frozen dbt build and tests")
        cases[trial_id] = json.loads(data)
        validate_case(cases[trial_id], expected[trial_id], spec["method"])
    return spec, cases, digest(seal_bytes)


def fraction(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def score_cases(cases: dict, truths: dict):
    if not cases or set(cases) != set(truths):
        raise ValueError("score requires every trial and matching truth")
    confusion = {}
    exact_matches = positives = hits = negatives = false_alerts = tracking = tracking_hits = (
        localized
    ) = 0
    unsafe = 0
    scenarios = {}
    for trial_id, case in cases.items():
        truth = truths[trial_id]
        expected, found = truth["expected"], case["finding"]
        row = confusion.setdefault(expected, {})
        row[found] = row.get(found, 0) + 1
        exact_matches += expected == found
        if expected == "payment_stage_hypothesis":
            positives += 1
            hits += found == expected
            localized += found == expected and case["supported_devices"] == [truth["device"]]
        if expected == "no_signal":
            negatives += 1
            false_alerts += found in (
                "payment_stage_hypothesis",
                "conversion_decline_unexplained",
                "measurement_issue",
            )
        if expected == "measurement_issue":
            tracking += 1
            tracking_hits += found == expected
            unsafe += bool(case["recommendations"]["measurement_eligible"])
        scenarios.setdefault(truth["scenario"], []).append((truth, case))
    delays = []
    for scenario, checkpoints in sorted(scenarios.items()):
        checkpoints.sort(key=lambda pair: pair[0]["cutoff"])
        onset = checkpoints[0][0]["onset"]
        if onset is None:
            continue
        first = None
        for truth, case in checkpoints:
            if truth["cutoff"] <= onset:
                continue
            correct = truth["expected"] == case["finding"]
            if truth["condition"] == "business":
                correct = correct and case["supported_devices"] == [truth["device"]]
            if correct:
                first = truth["cutoff"]
                break
        last = checkpoints[-1][0]["cutoff"]
        delays.append(
            {
                "scenario": scenario,
                "first_correct_cutoff": first,
                "onset": onset,
                "lag_days": (date.fromisoformat(first) - date.fromisoformat(onset)).days
                if first
                else None,
                "right_censored": first is None,
                "horizon_days": (date.fromisoformat(last) - date.fromisoformat(onset)).days,
            }
        )
    return {
        "trials": len(cases),
        "independent_worlds": len({t["world"] for t in truths.values()}),
        "confusion": confusion,
        "exact_diagnosis": fraction(exact_matches, len(cases)),
        "payment_detection_recall": fraction(hits, positives),
        "exact_device_localization": fraction(localized, positives),
        "healthy_false_positive_rate": fraction(false_alerts, negatives),
        "tracking_routing_recall": fraction(tracking_hits, tracking),
        "tracking_cases_with_eligible_investigations": unsafe,
        "detection_lag": delays,
        "limitations": [
            "Small synthetic benchmark; related checkpoints are not independent observations.",
            "No production accuracy, causal validity or statistically calibrated confidence claim.",
            "Lag is measured only at scheduled event-time checkpoints, not ingestion arrival time.",
            "Abstentions remain in accuracy denominators; unsupported claims are not detections.",
        ],
    }


def score(root: Path, split: str):
    if split not in SPLITS:
        raise ValueError("unknown split")
    spec, cases, seal_hash = verify_seal(root, split)  # verify before reading labels
    truth_bytes = (root / "private" / "truth.json").read_bytes()
    if digest(truth_bytes) != spec["truth_sha256"]:
        raise ValueError("truth changed after commitment")
    truth = json.loads(truth_bytes)["trials"]
    if set(truth) != {t["trial_id"] for t in spec["trials"]}:
        raise ValueError("truth must cover the complete benchmark")
    result = score_cases(cases, {key: truth[key] for key in cases})
    result.update(
        split=split,
        seal_sha256=seal_hash,
        truth_sha256=spec["truth_sha256"],
        scorer_sha256=digest(Path(__file__).read_bytes()),
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEMO Blind Lab: prepare, predict, then score")
    parser.add_argument("command", choices=("prepare", "predict", "score"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--split", choices=SPLITS, default="held_out")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.root)
        elif args.command == "predict":
            result = predict(args.root, args.split)
        else:
            result = score(args.root, args.split)
        if args.output:
            write_new(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
