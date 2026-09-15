"""Manual canonical cases prove diagnosis without generator or lab access."""

import hashlib
import json
import subprocess
import sys
from datetime import date
from fractions import Fraction

import pytest

from nemo.decision_case import build_case, compare, save_case
from nemo.warehouse import build_warehouse


def write_source(directory, kind):
    directory.mkdir()
    tables = {
        "customers": [{"customer_id": "c1", "first_seen_at": "2025-01-01T00:00:00Z"}],
        "campaigns": [],
        "ad_performance": [],
        "sessions": [],
        "orders": [],
        "events": [],
    }
    for day in (1, 2):
        for i in range(200):
            session = f"session:{day}:{i}"
            stamp = f"2025-01-0{day}"
            tables["sessions"].append(
                {
                    "session_id": session,
                    "customer_id": "c1",
                    "started_at": stamp + "T00:00:00Z",
                    "channel": "direct",
                    "campaign_id": None,
                    "device": "tablet",
                }
            )
            if i >= 50:
                continue
            success = i < (10 if kind == "business" and day == 2 else 40)
            order_id = f"order:{day}:{i}" if success else None

            def event(name, suffix, timestamp, linked_order, session=session, stamp=stamp):
                return {
                    "event_id": session + suffix,
                    "name": name,
                    "session_id": session,
                    "order_id": linked_order,
                    "occurred_at": stamp + timestamp,
                }

            tables["events"].append(event("payment_attempted", ":attempt", "T00:00:30Z", None))
            tables["events"].append(
                event(
                    "payment_succeeded" if success else "payment_failed",
                    ":terminal",
                    "T00:01:00Z",
                    order_id,
                )
            )
            if success:
                tables["orders"].append(
                    {
                        "order_id": order_id,
                        "session_id": session,
                        "customer_id": "c1",
                        "paid_at": stamp + "T00:01:00Z",
                        "amount_paise": 50000,
                    }
                )
                if not (kind == "tracking" and day == 2):
                    tables["events"].append(event("purchase", ":purchase", "T00:01:01Z", order_id))
    manifest = {
        "schema_version": "2",
        "mode": "production",
        "dataset_id": "manual-case",
        "channels": {"direct": False},
        "devices": ["tablet"],
        "currency": "INR",
        "money_unit": "paise",
        "amount_basis": "tax_exclusive_merchandise",
        "business_timezone": "Asia/Kolkata",
        "timestamp_timezone": "UTC",
        "observation_window": {
            "start_date_inclusive": "2025-01-01",
            "end_date_exclusive": "2025-01-03",
        },
        "measurement_contract": {
            "version": "1",
            "purchase_semantics": "one_purchase_event_per_paid_order",
            "max_delay_seconds": 300,
            "complete_through": "2025-01-02T18:30:00Z",
        },
        "funnel_contract": {
            "version": "1",
            "semantics": "one_payment_attempt_and_terminal_event_per_attempting_session",
        },
        "tables": {},
    }
    for table, rows in tables.items():
        data = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (directory / f"{table}.jsonl").write_bytes(data)
        manifest["tables"][table] = {"rows": len(rows), "sha256": hashlib.sha256(data).hexdigest()}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


def run_case(source, database):
    build_warehouse(source, database)
    return build_case(
        database, source, baseline_start=date(2025, 1, 1), current_start=date(2025, 1, 2)
    )


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory):
    root = tmp_path_factory.mktemp("decision-cases")
    results = {}
    for kind in ("healthy", "business", "tracking"):
        source = write_source(root / kind, kind)
        database = root / f"{kind}.duckdb"
        results[kind] = (source, database, run_case(source, database))
    return results


def test_healthy_control_has_no_signal(scenarios):
    case = scenarios["healthy"][2]
    assert case["finding"] == "no_signal"
    assert not case["recommendations"]["measurement_eligible"]
    assert case["measurement"]["dependencies"]["payment_funnel"] == "high"


def test_business_deterioration_supports_only_observational_hypothesis(scenarios):
    case = scenarios["business"][2]
    assert case["finding"] == "payment_stage_hypothesis"
    assert case["supported_devices"] == ["tablet"]
    assert case["observations"]["comparison"]["status"] == "flagged"
    assert case["estimated_incremental_profit"] is None
    assert case["evidence_strength"] == "observational_only"
    assert len(case["recommendations"]["measurement_eligible"]) == 1
    assert case["measurement"]["recommendation_readiness"]["budget_optimization"]["suppressed"]


def test_tracking_loss_is_not_diagnosed_as_business_failure(scenarios):
    case = scenarios["tracking"][2]
    assert case["finding"] == "measurement_issue"
    assert case["observations"]["comparison"]["status"] == "no_signal"
    assert not case["supported_devices"]
    assert not case["recommendations"]["measurement_eligible"]
    assert case["observations"]["current"] == scenarios["healthy"][2]["observations"]["current"]


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((1000, 100), (800, 40), "flagged"),
        ((200, 8), (200, 6), "no_signal"),
        ((99, 40), (99, 1), "insufficient_data"),
        ((200, 0), (200, 0), "insufficient_data"),
        ((0, 0), (200, 10), "insufficient_data"),
    ],
)
def test_anomaly_thresholds_and_unknown_denominators(a, b, expected):
    result = compare(
        dict(zip(("sessions", "purchasing_sessions"), a, strict=True)),
        dict(zip(("sessions", "purchasing_sessions"), b, strict=True)),
    )
    assert result["status"] == expected


def test_exact_decomposition_and_device_reconciliation(scenarios):
    result = compare(
        {"sessions": 1000, "purchasing_sessions": 100}, {"sessions": 800, "purchasing_sessions": 40}
    )
    decomposition = result["decomposition"]
    assert Fraction(**decomposition["volume_component"]) == -15
    assert Fraction(**decomposition["rate_component"]) == -45
    case = scenarios["business"][2]
    assert (
        sum(
            row["purchasing_session_change"] for row in case["observations"]["device_contributions"]
        )
        == -30
    )


def test_invalid_counts_rejected():
    with pytest.raises(ValueError):
        compare(
            {"sessions": 1, "purchasing_sessions": 2}, {"sessions": 1, "purchasing_sessions": 1}
        )


def test_replay_and_immutable_revisions(scenarios, tmp_path):
    source, database, case = scenarios["business"]
    repeated = build_case(
        database, source, baseline_start=date(2025, 1, 1), current_start=date(2025, 1, 2)
    )
    assert repeated == case
    path = save_case(case, tmp_path)
    assert save_case(repeated, tmp_path) == path
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert case["case_id"] == scenarios["healthy"][2]["case_id"]
    assert case["revision_id"] != scenarios["healthy"][2]["revision_id"]
    path.write_text("corrupt")
    with pytest.raises(ValueError, match="differs"):
        save_case(case, tmp_path)


def test_source_binding_and_invalid_windows(scenarios):
    _, database, _ = scenarios["business"]
    with pytest.raises(ValueError, match="do not match"):
        build_case(
            database,
            scenarios["healthy"][0],
            baseline_start=date(2025, 1, 1),
            current_start=date(2025, 1, 2),
        )
    with pytest.raises(ValueError, match="equal adjacent"):
        build_case(
            database,
            scenarios["business"][0],
            baseline_start=date(2025, 1, 1),
            current_start=date(2025, 1, 3),
        )


@pytest.mark.parametrize("defect", ["missing_terminal", "duplicate_attempt", "missing_contract"])
def test_invalid_payment_telemetry_blocks_hypothesis(tmp_path, defect):
    source = write_source(tmp_path / "source", "business")
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    events = [json.loads(line) for line in (source / "events.jsonl").read_text().splitlines()]
    if defect == "missing_contract":
        del manifest["funnel_contract"]
    else:
        if defect == "missing_terminal":
            events = [row for row in events if row["name"] != "payment_failed"]
        else:
            duplicate = dict(next(row for row in events if row["name"] == "payment_attempted"))
            duplicate["event_id"] += ":duplicate"
            events.append(duplicate)
        data = "".join(json.dumps(row) + "\n" for row in events).encode()
        (source / "events.jsonl").write_bytes(data)
        manifest["tables"]["events"] = {
            "rows": len(events),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    manifest_path.write_text(json.dumps(manifest))
    case = run_case(source, tmp_path / "warehouse.duckdb")
    assert case["finding"] in ("measurement_issue", "insufficient_measurement")
    assert case["observations"]["comparison"]["status"] == "flagged"
    assert not case["recommendations"]["measurement_eligible"]


def test_generator_and_lab_imports_blocked_and_private_truth_ignored(scenarios):
    source, database, expected = scenarios["business"]
    private = source.parent / "private"
    private.mkdir(exist_ok=True)
    (private / "run.json").write_text("not even valid JSON")
    code = """import importlib.abc,sys,json
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('nemo.simulation','nemo.contracts','nemo.artifacts',
                        'nemo.lab_tracking','nemo.lab_payment'):
            raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from pathlib import Path
from datetime import date
from nemo.decision_case import build_case
result=build_case(Path(sys.argv[1]),Path(sys.argv[2]),
                  baseline_start=date(2025,1,1),current_start=date(2025,1,2))
print(result['revision_id'])
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(database), str(source)],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected["revision_id"]


def test_lab_business_and_tracking_controls_are_distinct(tmp_path):
    from nemo.integrity import assess
    from nemo.lab_payment import plant_payment_problem

    source = write_source(tmp_path / "reference", "healthy")
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        plant_payment_problem(
            source, output, device="tablet", start=date(2025, 1, 2), end=date(2025, 1, 3)
        )
    for branch in ("healthy", "failure", "business"):
        a, b = (folder / branch / "observations" for folder in (first, second))
        assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()
        assert (a / "sessions.jsonl").read_bytes() == (source / "sessions.jsonl").read_bytes()
        assessment = assess(a)
        assert assessment["measurement_confidence"] == ("low" if branch == "failure" else "high")
    business = first / "business" / "observations"
    result = run_case(business, tmp_path / "business.duckdb")
    assert result["finding"] == "payment_stage_hypothesis"
    assert result["supported_devices"] == ["tablet"]
    (first / "private" / "payment-truth.json").write_text("invalid truth")
    repeated = build_case(
        tmp_path / "business.duckdb",
        business,
        baseline_start=date(2025, 1, 1),
        current_start=date(2025, 1, 2),
    )
    assert result == repeated
