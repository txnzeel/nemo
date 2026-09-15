"""Manual observations and lab perturbations prove integrity and suppression behavior."""

import hashlib
import json
import subprocess
import sys
from datetime import date

import pytest
from test_source_boundary import canonical_source as canonical_source

from nemo.integrity import assess, gate_recommendations
from nemo.lab_tracking import inject_tracking_loss
from nemo.measurement import measure
from nemo.warehouse import build_warehouse


def rewrite(source, events):
    data = "".join(json.dumps(row) + "\n" for row in events).encode()
    (source / "events.jsonl").write_bytes(data)
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["tables"]["events"] = {"rows": len(events), "sha256": hashlib.sha256(data).hexdigest()}
    manifest["measurement_contract"] = {
        "version": "1",
        "purchase_semantics": "one_purchase_event_per_paid_order",
        "max_delay_seconds": 300,
        "complete_through": "2025-01-01T18:30:00Z",
    }
    path.write_text(json.dumps(manifest))


@pytest.fixture
def tracked(canonical_source):
    event = {
        "event_id": "external:purchase:1",
        "name": "purchase",
        "session_id": "company:session:8",
        "order_id": "company:order:4",
        "occurred_at": "2025-01-01T00:01:01Z",
    }
    rewrite(canonical_source, [event])
    return canonical_source, event


def test_manual_source_passes_only_declared_checks(tracked):
    source, _ = tracked
    result = assess(source)
    assert result["measurement_confidence"] == "high"
    assert result["reconciliation"]["matched_mature_orders"] == 1
    candidates = [{"kind": "event_based_funnel_diagnosis"}, {"kind": "budget_optimization"}]
    gated = gate_recommendations(candidates, result)
    assert gated["measurement_eligible"] == candidates[:1]
    assert gated["suppressed"][0]["candidate"] == candidates[1]
    assert "paid_media:not_assessed" in gated["suppressed"][0]["reasons"]


def test_missing_events_reduce_trust_and_suppress(tracked):
    source, _ = tracked
    rewrite(source, [])
    result = assess(source)
    assert result["measurement_confidence"] == "low"
    assert result["reconciliation"]["missing_by_segment"] == [
        {"channel": "paid_social", "device": "tablet", "missing": 1}
    ]
    candidate = {"kind": "event_based_funnel_diagnosis", "text": "candidate supplied by caller"}
    gated = gate_recommendations([candidate], result)
    assert gated["measurement_eligible"] == []
    assert gated["suppressed"][0]["reasons"] == ["purchase_tracking:low"]


@pytest.mark.parametrize(
    ("changes", "check"),
    [
        ({"order_id": "unknown"}, "unmatched_purchase_events"),
        ({"session_id": "unknown"}, "session_mismatches"),
        ({"occurred_at": "2025-01-01T00:10:00Z"}, "purchase_timing_violations"),
        ({"occurred_at": "2025-01-01T00:00:59Z"}, "purchase_timing_violations"),
        ({"occurred_at": "2025-01-02T00:00:00Z"}, "events_after_complete_through"),
    ],
)
def test_mismatches_are_observed_failures(tracked, changes, check):
    source, event = tracked
    rewrite(source, [dict(event, **changes)])
    result = assess(source)
    assert result["measurement_confidence"] == "low"
    assert next(c for c in result["checks"] if c["check"] == check)["status"] == "fail"


def test_duplicates_are_not_silently_deduplicated(tracked):
    source, event = tracked
    rewrite(source, [event, event])
    result = assess(source)
    counts = {c["check"]: c["observed_count"] for c in result["checks"]}
    assert counts["duplicate_event_ids"] == counts["duplicate_purchase_events"] == 1
    assert result["measurement_confidence"] == "low"


def test_missing_contract_and_unknown_candidates_fail_closed(canonical_source):
    result = assess(canonical_source)
    assert result["measurement_confidence"] == "not_assessed"
    candidates = [
        {"kind": "event_based_funnel_diagnosis"},
        {"kind": "invented", "dependencies": []},
    ]
    assert len(gate_recommendations(candidates, result)["suppressed"]) == 2


def test_pending_orders_are_not_reported_as_tracking_loss(tracked):
    source, _ = tracked
    rewrite(source, [])
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["measurement_contract"]["complete_through"] = "2025-01-01T00:02:00Z"
    path.write_text(json.dumps(manifest))
    result = assess(source)
    assert result["measurement_confidence"] == "not_assessed"
    assert result["reconciliation"]["pending_paid_orders"] == 1
    assert result["reconciliation"]["missing_order_ids_sample"] == []


def test_corrupt_events_are_rejected(tracked):
    source, _ = tracked
    (source / "events.jsonl").write_text("")
    with pytest.raises(ValueError, match="checksum"):
        assess(source)


def test_lab_injection_preserves_commerce_and_keeps_truth_private(tracked, tmp_path):
    source, _ = tracked
    output = tmp_path / "lab"
    inject_tracking_loss(
        source, output, device="tablet", start=date(2025, 1, 1), end=date(2025, 1, 2)
    )
    healthy, failure = (output / name / "observations" for name in ("healthy", "failure"))
    assert (healthy / "orders.jsonl").read_bytes() == (failure / "orders.jsonl").read_bytes()
    assert assess(healthy)["measurement_confidence"] == "high"
    assert assess(failure)["measurement_confidence"] == "low"
    truth = output / "private" / "tracking-truth.json"
    before = assess(failure)
    truth.write_text("deliberately invalid and unavailable truth")
    assert assess(failure) == before
    with pytest.raises(FileExistsError):
        inject_tracking_loss(
            source, output, device="tablet", start=date(2025, 1, 1), end=date(2025, 1, 2)
        )


def test_report_uses_exact_snapshot_and_preserves_order_metrics(tracked, tmp_path):
    source, _ = tracked
    database = tmp_path / "warehouse.duckdb"
    build_warehouse(source, database)
    healthy = measure(warehouse=database, integrity_observations=source)
    rewrite(source, [])
    with pytest.raises(ValueError, match="do not match"):
        measure(warehouse=database, integrity_observations=source)
    build_warehouse(source, database)
    failed = measure(warehouse=database, integrity_observations=source)
    assert healthy["total"] == failed["total"]
    assert healthy["measurement_health"] == "high"
    assert failed["measurement_health"] == "low"


def test_detector_cannot_import_lab_or_generator(tracked):
    source, _ = tracked
    code = """import importlib.abc, sys
class BlockLab(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('nemo.lab_tracking', 'nemo.simulation', 'nemo.contracts', 'nemo.artifacts'):
            raise AssertionError(fullname)
sys.meta_path.insert(0, BlockLab())
from pathlib import Path
from nemo.integrity import assess
assert assess(Path(sys.argv[1]))['measurement_confidence'] == 'high'
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(source)], cwd=source, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "watermark", ["2099-01-01T00:00:00Z", "2024-01-01T00:00:00Z", "2025-01-01T00:00:00"]
)
def test_invalid_watermarks_are_rejected(tracked, watermark):
    source, _ = tracked
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["measurement_contract"]["complete_through"] = watermark
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        assess(source)


def test_absent_event_feed_is_unknown_not_healthy(tracked):
    source, _ = tracked
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["tables"]["events"]
    path.write_text(json.dumps(manifest))
    result = assess(source)
    assert result["measurement_confidence"] == "not_assessed"
    assert result["recommendation_readiness"]["event_based_funnel_diagnosis"]["suppressed"]
