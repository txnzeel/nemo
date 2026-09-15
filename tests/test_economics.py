"""Hand-calculated multi-month economics, coverage and production-boundary tests."""

import hashlib
import json
import shutil
import subprocess
import sys

import pytest

from nemo.economics import report
from nemo.economics_inputs import COST_COMPONENTS
from nemo.warehouse import build_warehouse


def rewrite(source, table, rows):
    data = "".join(json.dumps(row) + "\n" for row in rows).encode()
    (source / f"{table}.jsonl").write_bytes(data)
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["tables"][table] = {"rows": len(rows), "sha256": hashlib.sha256(data).hexdigest()}
    path.write_text(json.dumps(manifest))


def make_source(source):
    source.mkdir()
    manifest = {
        "schema_version": "2",
        "mode": "production",
        "dataset_id": "manual-economics",
        "channels": {"direct": False, "paid_social": True},
        "devices": ["tablet"],
        "currency": "INR",
        "money_unit": "paise",
        "amount_basis": "tax_exclusive_merchandise",
        "business_timezone": "Asia/Kolkata",
        "timestamp_timezone": "UTC",
        "observation_window": {
            "start_date_inclusive": "2025-01-01",
            "end_date_exclusive": "2025-04-15",
        },
        "economics_contract": {
            "version": "1",
            "refunds": {
                "basis": "tax_exclusive_merchandise",
                "coverage_end_exclusive": "2025-04-15",
            },
            "variable_costs": {
                "basis": "order_costs_net_of_recoveries",
                "coverage_end_exclusive": "2025-04-15",
                "components": list(COST_COMPONENTS),
                "provenance": "observed",
            },
        },
        "tables": {},
    }
    (source / "manifest.json").write_text(json.dumps(manifest))
    tables = {
        "customers": [
            {"customer_id": key, "first_seen_at": "2025-01-01T00:00:00Z"}
            for key in ("c1", "c2", "c3", "visitor")
        ],
        "campaigns": [{"campaign_id": "a1", "name": "Prospecting", "channel": "paid_social"}],
        "ad_performance": [],
        "sessions": [],
        "orders": [],
        "order_items": [],
        "refunds": [
            {
                "refund_id": "r1",
                "order_item_id": "i1",
                "quantity": 2,
                "amount_paise": 20000,
                "refunded_at": "2025-03-01T00:00:00Z",
            }
        ],
        "order_variable_costs": [],
    }
    specs = [
        ("c1", "2025-01-10", 100000, "direct", [40000, 10000, 1000, 1000, 0]),
        ("c1", "2025-02-05", 50000, "paid_social", [20000, 5000, 500, 0, 0]),
        ("c2", "2025-01-20", 100000, "paid_social", [50000, 10000, 1000, 0, 0]),
        ("c3", "2025-03-05", 40000, "direct", [20000, 5000, 400, 0, 0]),
    ]
    for i, (customer, day, amount, channel, costs) in enumerate(specs, 1):
        tables["sessions"].append(
            {
                "session_id": f"s{i}",
                "customer_id": customer,
                "started_at": day + "T00:00:00Z",
                "channel": channel,
                "campaign_id": "a1" if channel == "paid_social" else None,
                "device": "tablet",
            }
        )
        tables["orders"].append(
            {
                "order_id": f"o{i}",
                "session_id": f"s{i}",
                "customer_id": customer,
                "paid_at": day + "T00:05:00Z",
                "amount_paise": amount,
            }
        )
        tables["order_items"].append(
            {
                "order_item_id": f"i{i}",
                "order_id": f"o{i}",
                "product_id": "sku1",
                "quantity": amount // 10000,
                "unit_price_paise": 10000,
                "amount_paise": amount,
            }
        )
        tables["order_variable_costs"].append(
            {"order_id": f"o{i}", **dict(zip(COST_COMPONENTS, costs, strict=True))}
        )
    for table, rows in tables.items():
        rewrite(source, table, rows)
    return source


@pytest.fixture(scope="module")
def economic_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("economics")
    source = make_source(root / "source")
    database = root / "warehouse.duckdb"
    build_warehouse(source, database)
    return source, database, report(database, source, max_age=4)


def test_hand_calculated_value_and_contribution(economic_source):
    _, _, result = economic_source
    total = result["total"]
    assert total["buyers"] == 3
    assert total["paid_orders"] == 4
    assert total["repeat_buyers"] == 1
    assert total["gross_merchandise_paise"] == 290000
    assert total["refunds_paise"] == 20000
    assert total["net_merchandise_paise"] == 270000
    assert total["variable_cost_paise"] == 163900
    assert total["contribution_paise"] == 106100
    assert total["historical_net_value_paise_per_buyer"]["value"] == "90000.000000"
    assert result["coverage"]["cost_provenance"] == "observed"


def test_acquisition_credit_is_first_paid_order_not_latest(economic_source):
    customer = next(row for row in economic_source[2]["customers"] if row["customer_id"] == "c1")
    assert customer["cohort_month"] == "2025-01-01"
    assert customer["acquisition_channel"] == "direct"
    assert customer["net_merchandise_paise"] == 130000
    assert customer["contribution_paise"] == 52500


def test_retention_distinguishes_complete_zero_partial_and_future(economic_source):
    cells = {
        r["age_months"]: r
        for r in economic_source[2]["retention"]
        if r["cohort_month"] == "2025-01-01"
    }
    assert cells[0]["retention"]["value"] == "1.000000"
    assert cells[1]["retention"]["value"] == "0.500000"
    assert cells[1]["buyers"] == 2
    assert cells[2]["retention"]["value"] == "0.000000"  # refund is not a purchase
    assert cells[3]["observation_status"] == "partial_month"
    assert cells[3]["retention"]["value"] is None
    assert cells[4]["observation_status"] == "not_yet_observed"
    assert cells[4]["observed_active_buyers"] is None


def test_cohort_and_acquisition_sums_reconcile(economic_source):
    result = economic_source[2]
    for grouping in ("customers", "cohorts", "acquisition"):
        for field in (
            "gross_merchandise_paise",
            "refunds_paise",
            "net_merchandise_paise",
            "contribution_paise",
        ):
            assert sum(row[field] for row in result[grouping]) == result["total"][field]


def changed_source(economic_source, tmp_path):
    source = tmp_path / "changed"
    shutil.copytree(economic_source[0], source)
    return source


def build_report(source, tmp_path):
    database = tmp_path / "new.duckdb"
    build_warehouse(source, database)
    return report(database, source, max_age=4)


@pytest.mark.parametrize("missing", ["contract", "cost_row", "cost_component"])
def test_unknown_coverage_never_becomes_zero(economic_source, tmp_path, missing):
    source = changed_source(economic_source, tmp_path)
    if missing == "contract":
        path = source / "manifest.json"
        manifest = json.loads(path.read_text())
        del manifest["economics_contract"]
        path.write_text(json.dumps(manifest))
    else:
        costs = [
            json.loads(line)
            for line in (source / "order_variable_costs.jsonl").read_text().splitlines()
        ]
        if missing == "cost_row":
            costs.pop()
        else:
            costs[0]["net_cogs_paise"] = None
        rewrite(source, "order_variable_costs", costs)
    result = build_report(source, tmp_path)
    assert result["total"]["contribution_paise"] is None
    assert result["total"]["gross_merchandise_paise"] == 290000
    if missing == "contract":
        assert result["total"]["net_merchandise_paise"] is None
    else:
        assert result["total"]["net_merchandise_paise"] == 270000


@pytest.mark.parametrize(
    "defect",
    [
        "duplicate_refund",
        "excess_refund",
        "refund_before_order",
        "item_amount",
        "duplicate_cost",
        "negative_cost",
        "float_cost",
    ],
)
def test_invalid_economic_observations_rejected(economic_source, tmp_path, defect):
    source = changed_source(economic_source, tmp_path)
    table = "refunds"
    data = [json.loads(line) for line in (source / "refunds.jsonl").read_text().splitlines()]
    if defect == "duplicate_refund":
        data.append(data[0])
    elif defect == "excess_refund":
        data[0].update(quantity=11, amount_paise=110000)
    elif defect == "refund_before_order":
        data[0]["refunded_at"] = "2025-01-01T00:00:00Z"
    elif defect == "item_amount":
        table = "order_items"
        data = [json.loads(line) for line in (source / f"{table}.jsonl").read_text().splitlines()]
        data[0]["amount_paise"] += 1
    else:
        table = "order_variable_costs"
        data = [json.loads(line) for line in (source / f"{table}.jsonl").read_text().splitlines()]
        if defect == "duplicate_cost":
            data.append(data[0])
        else:
            data[0]["net_cogs_paise"] = -1 if defect == "negative_cost" else 1.25
    rewrite(source, table, data)
    with pytest.raises(ValueError):
        build_report(source, tmp_path)


def test_large_exact_costs_and_negative_contribution(economic_source, tmp_path):
    source = changed_source(economic_source, tmp_path)
    costs = [
        json.loads(line)
        for line in (source / "order_variable_costs.jsonl").read_text().splitlines()
    ]
    costs[0].update({key: 2**63 - 1 for key in COST_COMPONENTS})
    rewrite(source, "order_variable_costs", costs)
    result = build_report(source, tmp_path)
    assert result["total"]["variable_cost_paise"] == 5 * (2**63 - 1) + 111900
    assert result["total"]["contribution_paise"] == 270000 - result["total"]["variable_cost_paise"]


def test_source_binding_and_age_validation(economic_source, tmp_path):
    source = changed_source(economic_source, tmp_path)
    (source / "manifest.json").write_text((source / "manifest.json").read_text() + "\n")
    with pytest.raises(ValueError, match="do not match"):
        report(economic_source[1], source)
    with pytest.raises(ValueError, match="max_age"):
        report(economic_source[1], economic_source[0], max_age=True)


def test_generator_and_private_cost_assumptions_are_not_inputs(economic_source):
    source, database, _ = economic_source
    private = source.parent / "private"
    private.mkdir(exist_ok=True)
    (private / "cost-assumptions.json").write_text("invalid private data")
    code = """import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('nemo.simulation','nemo.contracts','nemo.artifacts','nemo.lab_economics'):
            raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from pathlib import Path
from nemo.economics import report
r=report(Path(sys.argv[1]),Path(sys.argv[2]))
assert r['total']['contribution_paise']==106100
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(database), str(source)],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
