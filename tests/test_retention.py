"""Observed state boundaries, full follow-up and manual warehouse integration."""

import json
from datetime import date, datetime, timedelta

import pytest
from test_economics import make_source

from nemo.retention import main, report, sequences, state
from nemo.warehouse import build_warehouse


def order(day, key="o", customer="c", amount=101):
    return {
        "order_id": key,
        "customer_id": customer,
        "day": date.fromisoformat(day),
        "paid_at": datetime.fromisoformat(day + "T00:00:00+00:00"),
        "amount_paise": amount,
    }


@pytest.mark.parametrize(
    "days,label",
    [
        ([], "NO_OBSERVED_PURCHASE"),
        (["2025-06-15"], "NEW"),
        (["2025-05-01"], "ACTIVE"),
        (["2025-03-01"], "AT_RISK"),
        (["2025-01-01"], "DORMANT"),
        (["2025-06-01", "2025-06-15"], "REPEAT"),
        (["2025-01-01", "2025-04-01", "2025-06-15"], "LOYAL"),
        (["2024-10-01", "2025-06-15"], "REACTIVATED"),
    ],
)
def test_states(days, label):
    orders = [order(day, str(i)) for i, day in enumerate(days)]
    result = state(orders, date(2025, 7, 1))
    assert result["state"] == label
    assert result["merchandise_receipts_paise"] == 101 * len(days)
    assert state(orders + [order("2025-07-01", "future")], date(2025, 7, 1)) == result


@pytest.mark.parametrize(
    "gap,label", [(89, "ACTIVE"), (90, "AT_RISK"), (179, "AT_RISK"), (180, "DORMANT")]
)
def test_recency_boundaries(gap, label):
    cutoff = date(2025, 7, 1)
    assert state([order((cutoff - timedelta(days=gap)).isoformat())], cutoff)["state"] == label


def item(o, product):
    return {
        "order_item_id": o["order_id"],
        "order_id": o["order_id"],
        "product_id": product,
        "quantity": 1,
        "unit_price_paise": 101,
        "amount_paise": 101,
    }


def test_sequence_followup_prior_and_simultaneous_purchase():
    orders, items = [], []
    specs = [
        ("good1", "2025-01-01", "2025-01-10"),
        ("good2", "2025-01-01", "2025-01-10"),
        ("censored", "2025-02-01", None),
        ("prior", "2025-01-02", "2025-01-01"),
        ("same", "2025-01-01", "2025-01-01"),
        ("never", "2025-01-01", None),
        ("late", "2025-01-01", "2025-02-02"),
    ]
    for customer, a, b in specs:
        for product, day in (("A", a), ("B", b)):
            if day:
                o = order(day, customer + product, customer)
                orders.append(o)
                items.append(item(o, product))
    result = sequences(orders, items, date(2025, 2, 15), 2)
    pair = next(p for p in result["pairs"] if p["from_product"] == "A")
    assert pair["eligible_customers"] == 4
    assert pair["sequential_customers"] == 2
    assert pair["review_eligible"]
    assert not next(
        p
        for p in sequences(orders, items, date(2025, 2, 15), 3)["pairs"]
        if p["from_product"] == "A"
    )["review_eligible"]
    assert sequences(orders, None, date(2025, 2, 15), 2)["status"] == "not_assessed"
    items[0]["amount_paise"] += 1
    with pytest.raises(ValueError, match="amount"):
        sequences(orders, items, date(2025, 2, 15), 2)


@pytest.fixture(scope="module")
def manual(tmp_path_factory):
    root = tmp_path_factory.mktemp("retention")
    source = root / "observations"
    make_source(source)
    db = root / "verified.duckdb"
    build_warehouse(source, db)
    return source, db


def test_manual_source_and_exact_history(manual):
    source, db = manual
    result = report(db, source, baseline=date(2025, 2, 1), as_of=date(2025, 4, 15), min_customers=2)
    customers = {c["customer_id"]: c for c in result["customers"]}
    assert customers["c1"]["current"]["paid_orders"] == 2
    assert customers["c1"]["current"]["merchandise_receipts_paise"] == 150000
    assert customers["c1"]["baseline"]["paid_orders"] == 1
    assert customers["visitor"]["current"]["state"] == "NO_OBSERVED_PURCHASE"
    assert all(c["forward_value_at_risk_paise"] is None for c in result["customers"])
    assert result["economic_ranking"] == "not_assessed"
    assert sum(t["customers"] for t in result["transitions"]) == 4
    assert (
        report(db, source, baseline=date(2025, 2, 1), as_of=date(2025, 4, 15), min_customers=2)
        == result
    )


def test_invalid_cutoffs_and_cli(manual, tmp_path):
    source, db = manual
    with pytest.raises(ValueError, match="cutoffs"):
        report(db, source, baseline=date(2025, 4, 15), as_of=date(2025, 4, 15))
    with pytest.raises(ValueError, match="min_customers"):
        report(db, source, baseline=date(2025, 2, 1), as_of=date(2025, 4, 15), min_customers=True)
    args = [
        "--warehouse",
        str(db),
        "--observations",
        str(source),
        "--baseline",
        "2025-02-01",
        "--as-of",
        "2025-04-15",
        "--output",
        str(tmp_path / "result.json"),
    ]
    assert main(args) == 0
    assert main(args) == 1


def test_reject_mismatched_source(manual, tmp_path):
    source, db = manual
    other = tmp_path / "other"
    other.mkdir()
    value = json.loads((source / "manifest.json").read_bytes())
    value["dataset_id"] = "another"
    (other / "manifest.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="match"):
        report(db, other, baseline=date(2025, 2, 1), as_of=date(2025, 4, 15))


def make_retention(source):
    from test_economics import rewrite

    make_source(source)
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["dataset_id"] = "manual-retention"
    manifest["observation_window"] = {
        "start_date_inclusive": "2024-01-01",
        "end_date_exclusive": "2025-07-01",
    }
    manifest.pop("economics_contract")
    manifest["tables"].pop("refunds")
    manifest["tables"].pop("order_variable_costs")
    (source / "manifest.json").write_text(json.dumps(manifest))
    specs = {
        "new": ["2025-06-15"],
        "active": ["2025-05-01"],
        "risk": ["2025-03-01"],
        "dormant": ["2025-01-01"],
        "repeat": ["2025-06-01", "2025-06-15"],
        "loyal": ["2025-01-01", "2025-04-01", "2025-06-15"],
        "reactivated": ["2024-10-01", "2025-06-15"],
        "sequence1": ["2025-01-01", "2025-01-10"],
        "sequence2": ["2025-01-01", "2025-01-10"],
        "visitor": [],
    }
    tables = {
        "customers": [{"customer_id": c, "first_seen_at": "2024-01-01T00:00:00Z"} for c in specs],
        "sessions": [],
        "orders": [],
        "order_items": [],
    }
    for customer, days in specs.items():
        for i, day in enumerate(days):
            key = f"{customer}-{i}"
            tables["sessions"].append(
                {
                    "session_id": key,
                    "customer_id": customer,
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
                    "customer_id": customer,
                    "paid_at": day + "T00:05:00Z",
                    "amount_paise": 10001,
                }
            )
            tables["order_items"].append(
                {
                    "order_item_id": key,
                    "order_id": key,
                    "quantity": 1,
                    "unit_price_paise": 10001,
                    "amount_paise": 10001,
                    "product_id": "A" if i == 0 else "B",
                }
            )
    for table, rows in tables.items():
        rewrite(source, table, rows)
    return source
