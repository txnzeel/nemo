"""Manual canonical query rows exercise search contracts independently of M1."""

import json

import pytest
from test_economics import make_source, rewrite

from nemo.search_intelligence import main, normalize, report


def make_search(source):
    make_source(source)
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["search_contract"] = {
        "version": "1",
        "scope": "One search account/property, INR, India, web search",
        "brand_classification": "Manually classified literal brand vocabulary",
        "coverage": "returned_queries",
        "conversions_complete": True,
        "conversion_definition": "Source-reported lead submissions",
        "conversion_window": "7 day click; finalized after reporting delay",
    }
    (source / "manifest.json").write_text(json.dumps(manifest))
    rows = [
        {
            "business_date": "2025-02-01",
            "surface": "paid",
            "query": "soap",
            "device": "tablet",
            "brand_segment": "nonbrand",
            "impressions": 1000,
            "clicks": 50,
            "spend_paise": 100001,
            "reported_conversions": 0,
            "position_sum_micros": None,
            "campaign_ids": ["a1"],
            "keywords": ["soap"],
            "landing_pages": ["/soap"],
        },
        {
            "business_date": "2025-02-01",
            "surface": "organic",
            "query": "soap",
            "device": "tablet",
            "brand_segment": "nonbrand",
            "impressions": 1000,
            "clicks": 10,
            "spend_paise": None,
            "reported_conversions": None,
            "position_sum_micros": 3000000000,
            "campaign_ids": [],
            "keywords": [],
            "landing_pages": ["/soap"],
        },
        {
            "business_date": "2025-02-02",
            "surface": "organic",
            "query": "soap",
            "device": "tablet",
            "brand_segment": "nonbrand",
            "impressions": 100,
            "clicks": 10,
            "spend_paise": None,
            "reported_conversions": None,
            "position_sum_micros": 1000000000,
            "campaign_ids": [],
            "keywords": [],
            "landing_pages": ["/soap"],
        },
    ]
    rewrite(source, "search_performance", rows)
    return rows


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "observations"
    make_search(path)
    return path


def test_exact_metrics_and_hypotheses(source):
    result = report(source)
    (query,) = result["queries"]
    assert query["paid"]["cpc_paise"] == {"numerator": 100001, "denominator": 50}
    assert query["organic"]["mean_position"] == {"numerator": 4000000000, "denominator": 1100000000}
    assert query["overlap_dates"] == ["2025-02-01"]
    assert len(result["reviews"][0]["reasons"]) == 3
    assert result["reviews"][0]["incremental_value_paise"] is None
    assert report(source) == result
    assert not (source.parent / "private").exists()


def test_unknown_conversions_withhold_waste_review(source):
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["search_contract"]["conversions_complete"] = False
    (source / "manifest.json").write_text(json.dumps(manifest))
    rows = [
        json.loads(line) for line in (source / "search_performance.jsonl").read_text().splitlines()
    ]
    rows[0]["reported_conversions"] = None
    rows[0]["business_date"] = "2025-02-03"
    rewrite(source, "search_performance", rows)
    result = report(source)
    assert result["queries"][0]["paid"]["reported_conversions"] is None
    assert result["queries"][0]["overlap_dates"] == []
    assert result["reviews"][0]["reasons"] == ["review_organic_intent_snippet_and_rank"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("spend_paise", 1.5),
        ("clicks", True),
        ("impressions", -1),
        ("clicks", 1001),
        ("device", "missing"),
        ("query", " SOAP "),
        ("business_date", "2030-01-01"),
        ("campaign_ids", ["unknown"]),
        ("keywords", "soap"),
        ("brand_segment", "brandish"),
        ("position_sum_micros", 2),
    ],
)
def test_reject_invalid_rows(source, key, value):
    rows = [
        json.loads(line) for line in (source / "search_performance.jsonl").read_text().splitlines()
    ]
    rows[0][key] = value
    rewrite(source, "search_performance", rows)
    with pytest.raises(ValueError):
        report(source)


def test_duplicate_and_checksum(source):
    rows = [
        json.loads(line) for line in (source / "search_performance.jsonl").read_text().splitlines()
    ]
    rewrite(source, "search_performance", rows + [rows[0]])
    with pytest.raises(ValueError, match="duplicate"):
        report(source)
    (source / "search_performance.jsonl").write_text("")
    with pytest.raises(ValueError, match="checksum"):
        report(source)


def test_missing_is_not_zero(tmp_path):
    source = tmp_path / "source"
    make_source(source)
    result = report(source)
    assert result["status"] == "not_assessed"
    assert result["queries"] == []


def test_cli_and_normalization(source, tmp_path):
    assert normalize("  ＳＯＡＰ\tBar ") == "soap bar"
    args = ["--observations", str(source), "--output", str(tmp_path / "report.json")]
    assert main(args) == 0
    assert main(args) == 1
    with pytest.raises(ValueError, match="positive"):
        report(source, min_paid_clicks=0)
