"""Chronological selection, untouched audit labels and conditional exact arithmetic."""

import json
from datetime import date, timedelta
from fractions import Fraction

import pytest
from test_economics import make_source, rewrite

from nemo.forecasting import backtest, main, report, scenario
from nemo.warehouse import build_warehouse


def test_weekly_pattern_beats_naive_without_audit_overlap():
    result = backtest([10, 12, 14, 8, 20, 9, 4] * 20, 7)
    assert result["method"] == "weekly_seasonal_naive"
    assert result["audit_mae"] == {"numerator": 0, "denominator": 1}
    assert result["selection_last_target_index"] < result["audit_first_target_index"]
    assert [p["point"] for p in result["forecast"]] == [10, 12, 14, 8, 20, 9, 4]
    assert all(p["lower"] == p["upper"] for p in result["forecast"])


def test_audit_does_not_choose_method_and_break_is_visible():
    values = [10, 12, 14, 8, 20, 9, 4] * 20
    original = backtest(values, 7)
    start = original["audit_first_target_index"]
    changed = values[:start] + [10000] * (len(values) - start)
    result = backtest(changed, 7)
    assert result["method"] == original["method"]
    assert result["selection_mae"] == original["selection_mae"]
    assert result["audit_mae"]["numerator"] > 0
    assert result["audit_band_coverage"]["numerator"] < result["audit_band_coverage"]["denominator"]


@pytest.mark.parametrize("values,horizon", [([1] * 10, 7), ([1] * 60, 14)])
def test_insufficient_history(values, horizon):
    assert backtest(values, horizon)["status"] == "not_assessed"


@pytest.mark.parametrize("horizon", [0, True, 15, 2.5])
def test_invalid_horizon(horizon):
    with pytest.raises(ValueError, match="horizon"):
        backtest([1] * 100, horizon)


def baseline():
    return {
        "spend_paise": 100001,
        "clicks": 100,
        "sessions": 80,
        "purchasing_sessions": 8,
        "orders": 10,
        "merchandise_receipts_paise": 300001,
        "source_reference": "manual-public-totals",
    }


def test_scenario_is_exact_and_conditional():
    b = baseline()
    value = scenario(b, {"cpc_multiplier": {"numerator": 115, "denominator": 100}})
    receipts = value["estimates"]["merchandise_receipts_paise"]
    assert Fraction(receipts["numerator"], receipts["denominator"]) == Fraction(300001 * 100, 115)
    assert value["incremental_profit_paise"] is None
    assert value["claim_type"] == "conditional_scenario"
    identity = scenario(b, {})
    assert identity["estimates"]["orders"] == {"numerator": 10, "denominator": 1}


@pytest.mark.parametrize(
    "changes",
    [
        {"cpc_multiplier": {"numerator": 0, "denominator": 1}},
        {"cvr_multiplier": {"numerator": 20, "denominator": 1}},
        {"profit": 2},
    ],
)
def test_invalid_scenario(changes):
    with pytest.raises(ValueError):
        scenario(baseline(), changes)


def make_forecast(source):
    make_source(source)
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["dataset_id"] = "manual-weekly"
    manifest["observation_window"]["end_date_exclusive"] = "2025-05-01"
    manifest["forecast_contract"] = {
        "version": "1",
        "daily_coverage_complete": True,
        "coverage_end_exclusive": "2025-05-01",
    }
    manifest.pop("economics_contract")
    manifest["tables"] = {}
    (source / "manifest.json").write_text(json.dumps(manifest))
    tables = {
        "customers": [{"customer_id": "c", "first_seen_at": "2025-01-01T00:00:00Z"}],
        "campaigns": [{"campaign_id": "a", "name": "Manual", "channel": "paid_social"}],
        "sessions": [],
        "orders": [],
        "ad_performance": [],
    }
    start = date(2025, 1, 1)
    for i in range(120):
        day = (start + timedelta(days=i)).isoformat()
        tables["ad_performance"].append(
            {
                "business_date": day,
                "campaign_id": "a",
                "device": "tablet",
                "impressions": 1000,
                "clicks": 50,
                "spend_paise": 100001,
            }
        )
        for j in range([10, 12, 14, 8, 20, 9, 4][i % 7]):
            key = f"s{i}-{j}"
            tables["sessions"].append(
                {
                    "session_id": key,
                    "customer_id": "c",
                    "started_at": day + "T00:00:00Z",
                    "channel": "direct",
                    "campaign_id": None,
                    "device": "tablet",
                }
            )
            tables["orders"].append(
                {
                    "order_id": key,
                    "session_id": key,
                    "customer_id": "c",
                    "paid_at": day + "T00:05:00Z",
                    "amount_paise": 10001,
                }
            )
    for table, rows in tables.items():
        rewrite(source, table, rows)
    return source


@pytest.fixture(scope="module")
def manual(tmp_path_factory):
    root = tmp_path_factory.mktemp("forecast")
    source = make_forecast(root / "observations")
    db = root / "verified.duckdb"
    build_warehouse(source, db)
    return source, db


def test_canonical_warehouse_forecast(manual, tmp_path):
    source, db = manual
    result = report(db, source, metric="revenue", horizon=7)
    assert result["analysis"]["status"] == "estimated"
    assert result["analysis"]["audit_mae"]["numerator"] == 0
    assert result["unit"] == "tax_exclusive_merchandise_paise"
    assert result["analysis"]["forecast"][0]["business_date"] == "2025-05-01"
    historical = report(db, source, cutoff=date(2025, 4, 1))
    assert historical["analysis"]["forecast"][0]["business_date"] == "2025-04-01"
    args = [
        "--warehouse",
        str(db),
        "--observations",
        str(source),
        "--output",
        str(tmp_path / "f.json"),
    ]
    assert main(args) == 0
    assert main(args) == 1


def test_missing_coverage_is_unknown(tmp_path):
    source = make_source(tmp_path / "source")
    db = tmp_path / "warehouse.duckdb"
    build_warehouse(source, db)
    assert report(db, source)["analysis"]["status"] == "not_assessed"
