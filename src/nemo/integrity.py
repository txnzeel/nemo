"""Observation-only purchase reconciliation and fail-closed measurement gates."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, time, timedelta
from pathlib import Path

from nemo.observations import BUSINESS_ZONE, open_snapshot

VERSION = "1"
DEPENDENCIES = {
    "payment_funnel_investigation": ("purchase_tracking", "payment_funnel"),
    "event_based_funnel_diagnosis": ("purchase_tracking",),
    "attribution": ("purchase_tracking", "attribution_contract"),
    "budget_optimization": ("purchase_tracking", "paid_media", "incremental_economics"),
}
LIMITATIONS = [
    "Confidence is a deterministic check outcome, not a probability or causal evidence.",
    "Agreement cannot detect shared source errors or prove source independence.",
    "Orders are a reconciliation reference, not independently verified financial truth.",
    "Assessment covers the complete supplied snapshot, not a filtered report segment.",
    "No live ingestion freshness, attribution, profitability or optimization is assessed.",
]


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO UTC string")
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return stamp


def gate_recommendations(candidates: list[dict], assessment: dict) -> dict:
    """Filter candidate recommendations using registered, non-caller-selected dependencies."""
    allowed, suppressed = [], []
    for candidate in candidates:
        kind = candidate.get("kind")
        dependencies = DEPENDENCIES.get(kind)
        reasons = (
            ["unregistered_recommendation_kind"]
            if dependencies is None
            else [
                f"{source}:{assessment['dependencies'].get(source, 'not_assessed')}"
                for source in dependencies
                if assessment["dependencies"].get(source) != "high"
            ]
        )
        if reasons:
            suppressed.append({"candidate": candidate, "reasons": reasons})
        else:
            allowed.append(candidate)
    return {
        "measurement_eligible": allowed,
        "suppressed": suppressed,
        "notice": "Passing this gate is not causal, economic or execution authorization.",
    }


def assess(observations: Path) -> dict:
    """Read only canonical public files. Never read generator metadata or parent paths."""
    with open_snapshot(observations) as snapshot:
        manifest_bytes = (observations / "manifest.json").read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != snapshot.manifest_sha256:
            raise ValueError("manifest changed during assessment")
        manifest = json.loads(manifest_bytes)
        result = {
            "assessment_version": VERSION,
            "claim_type": "measurement_assessment",
            "dataset_id": snapshot.contract.dataset_id,
            "manifest_sha256": snapshot.manifest_sha256,
            "window": {
                "start": snapshot.start.isoformat(),
                "end_exclusive": snapshot.end.isoformat(),
            },
            "measurement_confidence": "not_assessed",
            "dependencies": {"purchase_tracking": "not_assessed"},
            "checks": [],
            "limitations": LIMITATIONS,
            "policy_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        result["recommendation_readiness"] = {
            kind: gate_recommendations([{"kind": kind}], result) for kind in DEPENDENCIES
        }
        contract = manifest.get("measurement_contract")
        if contract is None:
            result["reason"] = "missing_purchase_reconciliation_contract"
            return result
        if (
            not isinstance(contract, dict)
            or contract.get("version") != "1"
            or contract.get("purchase_semantics") != "one_purchase_event_per_paid_order"
            or type(contract.get("max_delay_seconds")) is not int
            or not 0 <= contract["max_delay_seconds"] <= 86400
        ):
            raise ValueError("unsupported purchase reconciliation contract")
        complete = _utc(contract.get("complete_through"))
        if not (
            datetime.combine(snapshot.start, time(), BUSINESS_ZONE)
            <= complete
            <= datetime.combine(snapshot.end, time(), BUSINESS_ZONE)
        ):
            raise ValueError("complete_through must be inside the observation window")
        # A producer watermark is a completeness assertion, not evidence of freshness.
        result["contract"] = contract
        details = manifest["tables"].get("events")
        if details is None:
            result["reason"] = "missing_event_observations"
            return result
        payload = (observations / "events.jsonl").read_bytes()
        if (
            not isinstance(details, dict)
            or hashlib.sha256(payload).hexdigest() != details.get("sha256")
            or type(details.get("rows")) is not int
            or len(payload.splitlines()) != details["rows"]
        ):
            raise ValueError("event checksum or row count mismatch")
        result["events_sha256"] = details["sha256"]
        orders = {
            row["order_id"]: dict(row)
            for row in snapshot.connection.execute("select * from orders")
        }
        sessions = {
            row["session_id"]
            for row in snapshot.connection.execute("select session_id from sessions")
        }
        purchases = []
        event_ids = Counter()
        invalid_links = 0
        for line in payload.splitlines():
            row = json.loads(line)
            if not isinstance(row, dict) or any(
                not isinstance(row.get(k), str) or not row[k]
                for k in ("event_id", "name", "session_id")
            ):
                raise ValueError("invalid canonical event identity")
            occurred = _utc(row.get("occurred_at"))
            event_ids[row["event_id"]] += 1
            if row["session_id"] not in sessions:
                invalid_links += 1
            if row["name"] == "purchase":
                if not isinstance(row.get("order_id"), str) or not row["order_id"]:
                    raise ValueError("purchase requires an order_id")
                purchases.append((row, occurred))
        delay = timedelta(seconds=contract["max_delay_seconds"])
        mature = {
            key: row for key, row in orders.items() if _utc(row["paid_at"]) + delay <= complete
        }
        counts = Counter()
        unmatched = mismatched = timing = beyond_watermark = 0
        for row, occurred in purchases:
            order = orders.get(row["order_id"])
            if occurred > complete:
                beyond_watermark += 1
            if order is None:
                unmatched += 1
                continue
            counts[row["order_id"]] += 1
            if row["session_id"] != order["session_id"]:
                mismatched += 1
            paid = _utc(order["paid_at"])
            if not paid <= occurred <= paid + delay:
                timing += 1
        missing = sorted(key for key in mature if counts[key] == 0)
        duplicate_orders = sum(max(n - 1, 0) for n in counts.values())
        duplicate_ids = sum(max(n - 1, 0) for n in event_ids.values())
        failures = {
            "missing_mature_purchase_events": len(missing),
            "duplicate_purchase_events": duplicate_orders,
            "duplicate_event_ids": duplicate_ids,
            "unmatched_purchase_events": unmatched,
            "session_mismatches": mismatched,
            "invalid_session_links": invalid_links,
            "purchase_timing_violations": timing,
            "events_after_complete_through": beyond_watermark,
        }
        result["checks"] = [
            {"check": name, "observed_count": count, "status": "fail" if count else "pass"}
            for name, count in failures.items()
        ]
        segments = Counter()
        for key in missing:
            session = snapshot.connection.execute(
                "select channel, device from sessions where session_id = ?",
                [orders[key]["session_id"]],
            ).fetchone()
            segments[(session["channel"], session["device"])] += 1
        result["reconciliation"] = {
            "paid_orders": len(orders),
            "mature_paid_orders": len(mature),
            "pending_paid_orders": len(orders) - len(mature),
            "purchase_events": len(purchases),
            "matched_mature_orders": sum(counts[key] > 0 for key in mature),
            "missing_order_ids_sample": missing[:20],
            "missing_by_segment": [
                {"channel": c, "device": d, "missing": n} for (c, d), n in sorted(segments.items())
            ],
        }
        confidence = (
            "low"
            if any(failures.values())
            else "high"
            if mature and len(mature) == len(orders)
            else "not_assessed"
        )
        result["measurement_confidence"] = confidence
        result["dependencies"]["purchase_tracking"] = confidence
        result["reason"] = (
            "observed_purchase_discrepancy"
            if confidence == "low"
            else "all_declared_purchase_checks_pass"
            if confidence == "high"
            else "empty_or_pending_order_coverage"
        )
        result["possible_explanations"] = (
            ["tracking loss", "ingestion delay", "incorrect source contract or identity mapping"]
            if missing
            else []
        )
        # This is readiness metadata, not fabricated recommendations or an optimizer.
        result["recommendation_readiness"] = {
            kind: gate_recommendations([{"kind": kind}], result) for kind in DEPENDENCIES
        }
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Canonical purchase measurement integrity")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = assess(args.observations)
        encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
        else:
            sys.stdout.write(encoded)
        return 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
