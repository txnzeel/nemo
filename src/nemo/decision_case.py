"""Deterministic observation-only Decision Cases; investigation, never causal proof."""

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import date, datetime, time
from fractions import Fraction
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.integrity import DEPENDENCIES, assess, gate_recommendations
from nemo.measurement import measure
from nemo.observations import BUSINESS_ZONE
from nemo.warehouse import open_warehouse

METHOD = {
    "version": "1",
    "minimum_sessions_per_window": 100,
    "minimum_absolute_cvr_drop": "0.02",
    "minimum_relative_cvr_drop": "0.25",
    "minimum_payment_attempts_per_window": 30,
    "minimum_payment_rate_drop": "0.20",
    "statistical_significance": "not_assessed",
}
FUNNEL_CONTRACT = {
    "version": "1",
    "semantics": "one_payment_attempt_and_terminal_event_per_attempting_session",
}


def exact(value: Fraction | None):
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def compare(baseline: dict, current: dict) -> dict:
    """Predeclared operational rule plus exact midpoint decomposition of P = S * CVR."""
    s0, s1 = baseline["sessions"], current["sessions"]
    p0, p1 = baseline["purchasing_sessions"], current["purchasing_sessions"]
    if any(type(n) is not int or n < 0 for n in (s0, s1, p0, p1)) or p0 > s0 or p1 > s1:
        raise ValueError("invalid session-cohort counts")
    r0, r1 = Fraction(p0, s0) if s0 else None, Fraction(p1, s1) if s1 else None
    enough = min(s0, s1) >= METHOD["minimum_sessions_per_window"] and r0 is not None and r0 > 0
    drop = r0 - r1 if r0 is not None and r1 is not None else None
    relative = drop / r0 if r0 and drop is not None else None
    flagged = bool(
        enough
        and drop >= Fraction(METHOD["minimum_absolute_cvr_drop"])
        and relative >= Fraction(METHOD["minimum_relative_cvr_drop"])
    )
    decomposition = None
    if r0 is not None and r1 is not None:
        volume = (s1 - s0) * (r0 + r1) / 2
        rate = (r1 - r0) * (s0 + s1) / 2
        assert volume + rate == p1 - p0
        decomposition = {
            "unit": "purchasing_sessions",
            "volume_component": exact(volume),
            "rate_component": exact(rate),
            "observed_change": p1 - p0,
            "interpretation": "Exact descriptive allocation; not causal impact or lost profit.",
        }
    return {
        "status": "flagged" if flagged else "no_signal" if enough else "insufficient_data",
        "baseline_cvr": exact(r0),
        "current_cvr": exact(r1),
        "absolute_drop": exact(drop),
        "relative_drop": exact(relative),
        "decomposition": decomposition,
    }


def _payment_evidence(snapshot, observations: Path, baseline_start: date, current_start: date):
    manifest_bytes = (observations / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != snapshot.manifest_sha256:
        raise ValueError("funnel source does not match warehouse")
    manifest = json.loads(manifest_bytes)
    if manifest.get("funnel_contract") != FUNNEL_CONTRACT:
        return {
            "confidence": "not_assessed",
            "reason": "missing_or_unsupported_funnel_contract",
            "rows": [],
        }
    payload = (observations / "events.jsonl").read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["tables"]["events"]["sha256"]:
        raise ValueError("funnel event checksum mismatch")
    # Purchase assessment has already validated event schema, IDs and aware UTC timestamps.
    # Validate terminal-event order links separately; generic events are not purchases.
    orders = dict(
        snapshot.connection.execute(
            "select order_id, session_id from analytics.fct_orders"
        ).fetchall()
    )
    end = datetime.combine(snapshot.end, time(), BUSINESS_ZONE)
    start = datetime.combine(snapshot.start, time(), BUSINESS_ZONE)
    invalid_links = 0
    for line in payload.splitlines():
        event = json.loads(line)
        stamp = datetime.fromisoformat(event["occurred_at"])
        if not start <= stamp < end:
            invalid_links += 1
        if (
            event["name"] == "payment_succeeded"
            and orders.get(event.get("order_id")) != event["session_id"]
        ):
            invalid_links += 1
        if event["name"] == "payment_failed" and event.get("order_id") is not None:
            invalid_links += 1
    sql = files("nemo").joinpath("funnel.sql").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="nemo-funnel-") as directory:
        events = Path(directory) / "events.jsonl"
        events.write_bytes(payload)
        cursor = snapshot.connection.execute(
            sql,
            {
                "events": str(events),
                "baseline_start": baseline_start,
                "current_start": current_start,
                "end": snapshot.end,
            },
        )
        columns = [item[0] for item in cursor.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    invalid = invalid_links + sum(row["invalid_sessions"] for row in rows)
    attempts = sum(row["attempting_sessions"] for row in rows)
    return {
        "confidence": "low" if invalid else "high" if attempts else "not_assessed",
        "reason": "invalid_stage_observations" if invalid else "declared_stage_checks",
        "invalid_event_links_or_times": invalid_links,
        "rows": rows,
        "contract": FUNNEL_CONTRACT,
        "limitations": "One attempt per session; shared observation errors remain possible.",
    }


def build_case(
    warehouse: Path, observations: Path, *, baseline_start: date, current_start: date
) -> dict:
    with open_warehouse(warehouse) as snapshot:
        end = snapshot.end
        if (
            type(baseline_start) is not date
            or type(current_start) is not date
            or not snapshot.start <= baseline_start < current_start < end
            or current_start - baseline_start != end - current_start
        ):
            raise ValueError("comparison requires equal adjacent windows ending at snapshot cutoff")
        manifest_hash = snapshot.manifest_sha256
        integrity = assess(observations)
        if integrity["manifest_sha256"] != manifest_hash:
            raise ValueError("integrity observations do not match warehouse")
        if "events_sha256" in integrity:
            payment = _payment_evidence(snapshot, observations, baseline_start, current_start)
        else:
            payment = {"confidence": "not_assessed", "reason": "no_validated_events", "rows": []}
        mode, dataset_id = snapshot.contract.mode, snapshot.contract.dataset_id
    baseline = measure(
        warehouse=warehouse, start=baseline_start, end=current_start, group_by=("device",)
    )
    current = measure(warehouse=warehouse, start=current_start, end=end, group_by=("device",))
    if any(
        report["provenance"]["manifest_sha256"] != manifest_hash for report in (baseline, current)
    ):
        raise ValueError("warehouse changed during case generation")
    comparison = compare(baseline["total"]["facts"], current["total"]["facts"])
    groups = {}
    for period, report in (("baseline", baseline), ("current", current)):
        for group in report["groups"]:
            groups.setdefault(group["dimensions"]["device"], {})[period] = group["facts"]
    device_changes = []
    for device, periods in sorted(groups.items()):
        b, c = periods.get("baseline", {}), periods.get("current", {})
        device_changes.append(
            {
                "device": device,
                "purchasing_session_change": c.get("purchasing_sessions", 0)
                - b.get("purchasing_sessions", 0),
                "baseline_sessions": b.get("sessions", 0),
                "current_sessions": c.get("sessions", 0),
            }
        )
    stage_groups = {}
    for row in payment["rows"]:
        stage_groups.setdefault(row["device"], {})[row["period"]] = row
    stage_comparisons = []
    for device, periods in sorted(stage_groups.items()):
        b, c = periods.get("baseline", {}), periods.get("current", {})
        n0, n1 = b.get("attempting_sessions", 0), c.get("attempting_sessions", 0)
        r0 = Fraction(b["successful_sessions"], n0) if n0 else None
        r1 = Fraction(c["successful_sessions"], n1) if n1 else None
        decline = r0 - r1 if r0 is not None and r1 is not None else None
        flagged = bool(
            min(n0, n1) >= METHOD["minimum_payment_attempts_per_window"]
            and decline >= Fraction(METHOD["minimum_payment_rate_drop"])
        )
        stage_comparisons.append(
            {
                "device": device,
                "baseline_attempts": n0,
                "current_attempts": n1,
                "baseline_success_rate": exact(r0),
                "current_success_rate": exact(r1),
                "absolute_drop": exact(decline),
                "rule_status": (
                    "insufficient_data"
                    if min(n0, n1) < METHOD["minimum_payment_attempts_per_window"]
                    else "flagged"
                    if flagged
                    else "no_signal"
                ),
                "supports_deterioration": (
                    flagged
                    and payment["confidence"] == "high"
                    and integrity["dependencies"]["purchase_tracking"] == "high"
                ),
            }
        )
    integrity["dependencies"]["payment_funnel"] = payment["confidence"]
    integrity["recommendation_readiness"] = {
        kind: gate_recommendations([{"kind": kind}], integrity) for kind in DEPENDENCIES
    }
    candidates = []
    supporting = [row["device"] for row in stage_comparisons if row["supports_deterioration"]]
    trust = integrity["dependencies"]["purchase_tracking"]
    if trust != "high" or payment["confidence"] != "high":
        finding = (
            "measurement_issue"
            if "low" in (trust, payment["confidence"])
            else "insufficient_measurement"
        )
        next_step = (
            "Inspect reconciliation and telemetry coverage before interpreting funnel movement."
        )
    elif comparison["status"] == "flagged" and supporting:
        finding = "payment_stage_hypothesis"
        next_step = "Inspect device payment errors, provider responses and release history."
        candidates = [
            {
                "kind": "payment_funnel_investigation",
                "devices": supporting,
                "action": next_step,
                "claim_type": "diagnostic_hypothesis",
                "execution": "manual_investigation_only",
            }
        ]
    elif comparison["status"] == "flagged":
        finding = "conversion_decline_unexplained"
        next_step = "Investigate traffic mix and earlier stages; payment evidence is insufficient."
    else:
        finding = comparison["status"]
        next_step = (
            "Collect more comparable observations."
            if finding == "insufficient_data"
            else "No investigation triggered by this rule."
        )
    gated = gate_recommendations(candidates, integrity)
    identity = {
        "dataset_id": dataset_id,
        "mode": mode,
        "question": "purchasing_session_conversion",
        "baseline_start": baseline_start.isoformat(),
        "current_start": current_start.isoformat(),
        "end_exclusive": end.isoformat(),
    }

    def fingerprint(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()

    result = {
        "schema_version": "1",
        "case_id": "DC-" + fingerprint(identity)[:20],
        "question": "Is the conversion decline consistent with payment-stage deterioration?",
        "scope": identity,
        "analysis_cutoff": end.isoformat(),
        "status": "no_signal" if finding == "no_signal" else "under_investigation",
        "owner": None,
        "finding": finding,
        "claim_type": "diagnostic_hypothesis"
        if finding == "payment_stage_hypothesis"
        else "observed_assessment",
        "evidence_strength": "observational_only",
        "method": METHOD,
        "metric_contracts": current["registry"],
        "measurement": integrity,
        "observations": {
            "baseline": baseline["total"],
            "current": current["total"],
            "comparison": comparison,
            "device_contributions": device_changes,
        },
        "payment_evidence": payment,
        "device_payment_comparisons": stage_comparisons,
        "supported_devices": supporting if finding == "payment_stage_hypothesis" else [],
        "alternatives": [
            "Traffic composition or demand changed.",
            "Telemetry sources share omissions or mapping errors.",
            "Payment/provider conditions changed; a specific deployment cause is unverified.",
        ],
        "contradictions": [row for row in stage_comparisons if row["rule_status"] == "no_signal"],
        "next_investigation": next_step,
        "recommendations": gated,
        "economic_action": "not_supported: incremental economics and causal effect are unassessed",
        "estimated_incremental_profit": None,
        "experiments": [],
        "ledger_entries": [],
        "limitations": [
            "Operational thresholds are not significance tests or calibrated false-positive rates.",
            "Decomposition is descriptive; root cause and incremental impact remain unproven.",
            "Equal windows reduce duration bias but not seasonality or traffic-mix confounding.",
            "CVR uses existing within-window session follow-up; late-window cohorts are censored.",
            "Latest corrected snapshot through cutoff is not an arrival-as-of reconstruction.",
            "Whole-snapshot integrity can conservatively block a narrower-window diagnosis.",
        ],
        "provenance": {
            **current["provenance"],
            "case_code_sha256": {
                name: hashlib.sha256(files("nemo").joinpath(name).read_bytes()).hexdigest()
                for name in ("decision_case.py", "funnel.sql")
            },
        },
    }
    result["revision_id"] = fingerprint(result)
    return result


def save_case(case: dict, directory: Path) -> Path:
    """Immutable revisions; identical case/revision replay is a no-op."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case['case_id']}-{case['revision_id']}.json"
    encoded = json.dumps(case, sort_keys=True, indent=2, allow_nan=False) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("existing case revision differs") from None
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Observation-only NEMO Decision Case")
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--baseline-start", type=date.fromisoformat, required=True)
    parser.add_argument("--current-start", type=date.fromisoformat, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        case = build_case(
            args.warehouse,
            args.observations,
            baseline_start=args.baseline_start,
            current_start=args.current_start,
        )
        path = save_case(case, args.output_directory)
        print(json.dumps({"case": str(path.absolute()), "finding": case["finding"]}))
        return 0
    except (ValueError, OSError, RuntimeError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
