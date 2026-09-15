"""Hand-calculated acquisition cases, independent of the business generator."""

import hashlib
import json
import subprocess
import sys
from datetime import date

import pytest

from nemo.measurement import measure
from nemo.observations import REQUIRED_TABLES

START = date(2025, 1, 2)
END = date(2025, 1, 3)


def timestamp(day, minute=0):
    return f"2025-01-{day:02d}T00:{minute:02d}:00+00:00"


@pytest.fixture
def records():
    sessions = [
        ("s1", "c1", 1, "paid_search", "a", "android"),
        ("s2", "c1", 2, "paid_search", "b", "desktop"),
        ("s3", "c2", 2, "paid_search", "a", "android"),
        ("s4", "c3", 2, "direct", None, "android"),
        ("s5", "c4", 2, "paid_search", "b", "desktop"),
        ("s6", "c5", 2, "organic_search", None, "ios"),
        ("s7", "c6", 2, "paid_search", "a", "android"),
        ("s8", "c7", 3, "paid_search", "b", "desktop"),
    ]
    return {
        "customers": [
            {
                "customer_id": f"c{i}",
                "first_seen_at": timestamp(1 if i == 1 else 3 if i == 7 else 2),
            }
            for i in range(1, 8)
        ],
        "campaigns": [{"campaign_id": key, "name": key} for key in ("a", "b")],
        "sessions": [
            dict(
                session_id=s,
                customer_id=c,
                started_at=timestamp(day),
                channel=channel,
                campaign_id=campaign,
                device=device,
            )
            for s, c, day, channel, campaign, device in sessions
        ],
        "orders": [
            dict(
                order_id=o,
                session_id=s,
                customer_id=c,
                paid_at=timestamp(day, 2),
                amount_paise=amount,
            )
            for o, s, c, day, amount in [
                ("o1", "s1", "c1", 1, 10000),
                ("o2", "s2", "c1", 2, 20000),
                ("o3", "s3", "c2", 2, 30000),
                ("o4", "s4", "c3", 2, 40000),
                ("o5", "s6", "c5", 3, 60000),
                ("o6", "s8", "c7", 3, 70000),
            ]
        ],
        "ad_performance": [
            dict(
                business_date=f"2025-01-{day:02d}",
                campaign_id=campaign,
                device=device,
                impressions=impressions,
                clicks=clicks,
                spend_paise=spend,
            )
            for day, campaign, device, impressions, clicks, spend in [
                (1, "a", "android", 100, 10, 10000),
                (2, "a", "android", 100, 20, 20000),
                (2, "b", "desktop", 900, 9, 9000),
                (3, "b", "desktop", 50, 5, 5000),
            ]
        ],
    }


def snapshot(tmp_path, records):
    directory = tmp_path / "observations"
    directory.mkdir(exist_ok=True)
    tables = {}
    for name, rows in records.items():
        payload = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (directory / f"{name}.jsonl").write_bytes(payload)
        tables[name] = {"rows": len(rows), "sha256": hashlib.sha256(payload).hexdigest()}
    manifest = {
        "schema_version": "1",
        "mode": "synthetic",
        "currency": "INR",
        "money_unit": "paise",
        "amount_basis": "tax_exclusive_merchandise",
        "business_timezone": "Asia/Kolkata",
        "timestamp_timezone": "UTC",
        "observation_window": {
            "start_date_inclusive": "2025-01-01",
            "end_date_exclusive": "2025-01-04",
        },
        "tables": tables,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def test_every_metric_against_hand_calculated_example(tmp_path, records):
    result = measure(snapshot(tmp_path, records), start=START, end=END)
    values = {k: v["value"] for k, v in result["total"]["metrics"].items()}
    assert values == {
        "impressions": 1000,
        "clicks": 29,
        "spend": 29000,
        "sessions": 6,
        "purchasing_sessions": 3,
        "orders": 3,
        "conversions": 3,
        "revenue": 90000,
        "new_customers": 2,
        "ctr": "0.029000",
        "cpc": "1000.000000",
        "cvr": "0.500000",
        "cpa": "14500.000000",
        "media_cac": "29000.000000",
        "cac": None,
        "roas": "1.724138",
    }
    assert result["total"]["metrics"]["cac"]["reason"] == "missing_full_acquisition_costs"
    assert result["total"]["metrics"]["roas"]["numerator"] == 50000
    assert result["measurement_health"] == "not_assessed"


def test_ratios_are_recomputed_and_nonpaid_revenue_is_excluded(tmp_path, records):
    result = measure(snapshot(tmp_path, records), start=START, end=END, group_by=("campaign_id",))
    paid = {
        g["dimensions"]["campaign_id"]: g
        for g in result["groups"]
        if g["dimensions"]["campaign_id"] is not None
    }
    assert paid["a"]["metrics"]["ctr"]["value"] == "0.200000"
    assert paid["b"]["metrics"]["ctr"]["value"] == "0.010000"
    assert result["total"]["metrics"]["ctr"]["value"] == "0.029000"  # not 0.105
    assert result["total"]["metrics"]["roas"]["numerator"] == 50000  # not 90000
    assert result["total"]["metrics"]["cpa"]["denominator"] == 2  # not 3


def test_first_purchase_ranking_precedes_date_and_campaign_filters(tmp_path, records):
    result = measure(snapshot(tmp_path, records), start=START, end=END, campaign_id="b")
    metrics = result["total"]["metrics"]
    assert metrics["orders"]["value"] == 1
    assert metrics["new_customers"]["value"] == 0  # c1 first bought through a yesterday
    assert metrics["media_cac"]["value"] is None
    assert metrics["media_cac"]["reason"] == "zero_denominator"


def test_future_orders_do_not_leak_into_session_cohorts(tmp_path, records):
    path = snapshot(tmp_path, records)
    early = measure(path, start=START, end=END, channel="organic_search")
    assert early["total"]["metrics"]["cvr"]["value"] == "0.000000"
    late = measure(path, start=START, end=date(2025, 1, 4), channel="organic_search")
    assert late["total"]["metrics"]["cvr"]["value"] == "1.000000"
    day3 = measure(path, start=END, end=date(2025, 1, 4), channel="organic_search")
    assert day3["total"]["metrics"]["sessions"]["value"] == 0
    assert day3["total"]["metrics"]["orders"]["value"] == 1
    assert day3["total"]["metrics"]["cvr"]["reason"] == "zero_denominator"


def test_multiple_orders_do_not_inflate_purchasing_sessions_or_new_buyers(tmp_path, records):
    records["orders"].append(dict(records["orders"][2], order_id="o3b", amount_paise=10000))
    result = measure(snapshot(tmp_path, records), start=START, end=END)
    metrics = result["total"]["metrics"]
    assert metrics["orders"]["value"] == metrics["conversions"]["value"] == 4
    assert metrics["purchasing_sessions"]["value"] == 3
    assert metrics["new_customers"]["value"] == 2
    assert metrics["cvr"]["value"] == "0.500000"


def test_zero_and_missing_paid_coverage_are_distinct(tmp_path, records):
    for name in ("orders", "sessions", "customers"):
        records[name] = []
    for row in records["ad_performance"]:
        row.update(impressions=0, clicks=0, spend_paise=0)
    result = measure(snapshot(tmp_path, records))
    assert result["total"]["metrics"]["spend"]["value"] == 0
    assert result["total"]["metrics"]["ctr"]["reason"] == "zero_denominator"
    assert result["total"]["metrics"]["cvr"]["reason"] == "zero_denominator"
    records["ad_performance"] = []
    empty = measure(snapshot(tmp_path, records))
    assert empty["total"]["metrics"]["spend"]["value"] is None
    assert empty["total"]["metrics"]["spend"]["reason"] == "no_paid_ad_observations_in_scope"


def test_nonpaid_cost_metrics_are_unavailable_not_zero(tmp_path, records):
    result = measure(snapshot(tmp_path, records), start=START, end=END, channel="direct")
    for metric in ("spend", "ctr", "cpc", "cpa", "media_cac", "roas"):
        assert result["total"]["metrics"][metric]["value"] is None
    assert result["total"]["metrics"]["revenue"]["value"] == 40000


def test_all_dimension_totals_reconcile(tmp_path, records):
    result = measure(
        snapshot(tmp_path, records),
        group_by=(
            "business_date",
            "channel",
            "campaign_id",
            "device",
        ),
    )
    for fact, total in result["total"]["facts"].items():
        assert sum(group["facts"][fact] for group in result["groups"]) == total


def test_private_parameters_events_and_line_items_are_not_inputs(tmp_path, records):
    path = snapshot(tmp_path, records)
    expected = measure(path)
    (tmp_path / "private").mkdir()
    (tmp_path / "private/run.json").write_text("DO NOT READ: secret interventions")
    (path / "events.jsonl").write_text("duplicate events and malformed input")
    (path / "order_items.jsonl").write_text("many lines must not fan out orders")
    assert measure(path) == expected
    assert set(expected["provenance"]["tables"]) == set(REQUIRED_TABLES)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"group_by": ("channel", "channel")},
        {"group_by": ("channel; DROP TABLE orders",)},
        {"start": date(2024, 1, 1)},
        {"end": date(2026, 1, 1)},
        {"start": START, "end": START},
        {"channel": "unknown"},
        {"device": "unknown"},
    ],
)
def test_invalid_scope_is_rejected(tmp_path, records, kwargs):
    with pytest.raises(ValueError):
        measure(snapshot(tmp_path, records), **kwargs)


def test_filter_values_are_bound_parameters(tmp_path, records):
    result = measure(snapshot(tmp_path, records), campaign_id="a' OR 1=1 --")
    assert result["total"]["metrics"]["orders"]["value"] == 0
    assert result["groups"] == []


@pytest.mark.parametrize("defect", ["checksum", "count", "missing_file", "missing_table", "units"])
def test_artifact_integrity_errors_are_explicit(tmp_path, records, defect):
    path = snapshot(tmp_path, records)
    manifest = json.loads((path / "manifest.json").read_text())
    if defect == "checksum":
        (path / "orders.jsonl").write_text("{}")
    elif defect == "count":
        manifest["tables"]["orders"]["rows"] += 1
    elif defect == "missing_file":
        (path / "orders.jsonl").unlink()
    elif defect == "missing_table":
        del manifest["tables"]["orders"]
    else:
        manifest["currency"] = "USD"
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        measure(path)


@pytest.mark.parametrize(
    "defect",
    [
        "duplicate_order",
        "duplicate_session",
        "orphan_order",
        "wrong_customer",
        "negative_money",
        "boolean_money",
        "naive_time",
        "before_session",
        "invalid_campaign",
        "too_many_clicks",
    ],
)
def test_rehashed_structurally_invalid_records_are_rejected(tmp_path, records, defect):
    if defect == "duplicate_order":
        records["orders"].append(records["orders"][0])
    elif defect == "duplicate_session":
        records["sessions"].append(records["sessions"][0])
    elif defect == "orphan_order":
        records["orders"][0]["session_id"] = "missing"
    elif defect == "wrong_customer":
        records["orders"][0]["customer_id"] = "c2"
    elif defect == "negative_money":
        records["orders"][0]["amount_paise"] = -1
    elif defect == "boolean_money":
        records["orders"][0]["amount_paise"] = True
    elif defect == "naive_time":
        records["orders"][0]["paid_at"] = "2025-01-01T00:02:00"
    elif defect == "before_session":
        records["orders"][0]["paid_at"] = "2024-12-31T23:59:59+00:00"
    elif defect == "invalid_campaign":
        records["sessions"][0]["campaign_id"] = "missing"
    else:
        records["ad_performance"][0]["clicks"] = 101
    with pytest.raises(ValueError):
        measure(snapshot(tmp_path, records))


def test_business_midnight_uses_indian_date_and_exclusive_end(tmp_path, records):
    # 18:30 UTC is midnight of the next Indian business date.
    records["orders"][2]["paid_at"] = "2025-01-02T18:30:00+00:00"
    result = measure(snapshot(tmp_path, records), start=START, end=END)
    assert result["total"]["metrics"]["orders"]["value"] == 2
    assert result["total"]["metrics"]["new_customers"]["value"] == 1


def test_installed_module_cli_and_no_simulator_import(tmp_path, records):
    path = snapshot(tmp_path, records)
    output = tmp_path / "report.json"
    command = [
        sys.executable,
        "-m",
        "nemo.measurement",
        "--observations",
        str(path),
        "--output",
        str(output),
    ]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report["total"]["metrics"]["orders"]["value"] == 6
    refused = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert refused.returncode == 1
    assert json.loads(output.read_text()) == report
    checked = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, nemo.measurement; assert 'nemo.simulation' not in sys.modules",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stderr


def test_registry_cli_needs_no_source_files(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "nemo.measurement", "--registry"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    definitions = {row["name"]: row for row in json.loads(result.stdout)}
    assert definitions["ctr"]["formula"] == "clicks / impressions"
    for definition in definitions.values():
        assert all(
            key in definition
            for key in (
                "version",
                "formula",
                "unit",
                "sources",
                "dimensions",
                "grain",
                "freshness_requirement",
                "limitations",
            )
        )


def test_first_purchase_ties_use_order_id_not_input_order(tmp_path, records):
    records["sessions"].append(
        dict(
            records["sessions"][2],
            session_id="s9",
            campaign_id="b",
            device="desktop",
        )
    )
    records["orders"].append(
        dict(
            records["orders"][2],
            order_id="o0",
            session_id="s9",
        )
    )
    first = measure(snapshot(tmp_path, records), start=START, end=END, campaign_id="b")
    assert first["total"]["metrics"]["new_customers"]["value"] == 1
    for rows in records.values():
        rows.reverse()
    second = measure(snapshot(tmp_path, records), start=START, end=END, campaign_id="b")
    assert first["total"] == second["total"]
    assert first["groups"] == second["groups"]


def test_cli_source_failure_creates_no_report(tmp_path, records):
    path = snapshot(tmp_path, records)
    (path / "orders.jsonl").write_text("broken")
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "nemo.measurement",
            "--observations",
            str(path),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stderr)["status"] == "error"
    assert "checksum mismatch" in result.stderr
    assert not output.exists()
