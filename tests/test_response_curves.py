"""Saturation is screened on chronology, variation, support and holdout error."""

import json
from datetime import date, timedelta

import pytest
from test_economics import make_source, rewrite

from nemo.economics_inputs import COST_COMPONENTS
from nemo.response_curves import evaluate, fit, main, report


def points():
    spends = [
        10000,
        20000,
        40000,
        60000,
        80000,
        100000,
        150000,
        200000,
        250000,
        300000,
        400000,
        500000,
    ] * 2
    return [
        {"spend_paise": x, "contribution_before_media_paise": 3000000 * x // (100000 + x)}
        for x in spends
    ]


def test_saturation_and_supported_marginal_returns():
    curve = fit(points())
    assert curve["status"] == "estimated"
    assert curve["audit_mae_paise"] < curve["constant_audit_mae_paise"] * 0.95
    low, high = evaluate(curve, 100000), evaluate(curve, 200000)
    assert low["marginal_response"] > high["marginal_response"] > 0
    assert (
        high["modelled_contribution_before_media_paise"]
        < 2 * low["modelled_contribution_before_media_paise"]
    )
    assert (
        low["lower_paise"] <= low["modelled_contribution_before_media_paise"] <= low["upper_paise"]
    )
    assert curve["action_eligibility"] == "scenario_only"
    with pytest.raises(ValueError, match="range"):
        evaluate(curve, 500001)


def test_missing_flat_and_nonpredictive_series():
    assert fit(points()[:23])["status"] == "not_assessed"
    flat = [{"spend_paise": 100, "contribution_before_media_paise": 200}] * 24
    assert fit(flat)["reason"] == "insufficient_training_spend_variation"
    data = points()
    for p in data:
        p["contribution_before_media_paise"] = 100000
    assert fit(data)["status"] == "not_assessed"


def test_holdout_not_used_to_fit_and_out_of_support_blocks():
    original = fit(points())
    data = points()
    data[-1]["contribution_before_media_paise"] += 100000
    changed = fit(data)
    assert changed["status"] == "estimated"
    assert changed["a_paise"] == original["a_paise"]
    assert changed["b_paise"] == original["b_paise"]
    data[-1]["spend_paise"] = 500001
    assert fit(data)["reason"] == "audit_spend_outside_training_support"


def make_response(source):
    make_source(source)
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["dataset_id"] = "manual-response"
    manifest.pop("economics_contract")
    manifest["tables"].pop("refunds")
    manifest["tables"].pop("order_variable_costs")
    manifest["observation_window"]["end_date_exclusive"] = "2025-07-01"
    manifest["response_contract"] = {
        "version": "1",
        "cost_provenance": "observed",
        "weeks_complete": True,
        "variable_cost_components": list(COST_COMPONENTS),
        "outcome": "contribution_before_media",
        "scope": "Manual weekly paid-social contribution before media",
        "lineage_reference": "Hand-authored contract example, not a live company source",
    }
    (source / "manifest.json").write_text(json.dumps(manifest))
    rows = []
    for i, p in enumerate(points()):
        rows.append(
            {
                "week_start": (date(2025, 1, 6) + timedelta(days=7 * i)).isoformat(),
                "channel": "paid_social",
                "spend_paise": p["spend_paise"],
                "merchandise_receipts_paise": p["contribution_before_media_paise"] + 10000,
                "merchandise_refunds_paise": 0,
                **{k: 10000 if k == "net_cogs_paise" else 0 for k in COST_COMPONENTS},
            }
        )
    rewrite(source, "response_observations", rows)
    return rows


@pytest.fixture
def source(tmp_path):
    source = tmp_path / "observations"
    make_response(source)
    return source


def test_public_canonical_report(source, tmp_path):
    value = report(source)
    assert value["channels"][0]["curve"]["status"] == "estimated"
    assert (
        value["channels"][0]["observations"][0]["contribution_before_media_paise"]
        == points()[0]["contribution_before_media_paise"]
    )
    assert report(source) == value
    args = ["--observations", str(source), "--output", str(tmp_path / "r.json")]
    assert main(args) == 0
    assert main(args) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("spend_paise", True),
        ("channel", "unknown"),
        ("week_start", "2025-01-07"),
        ("net_cogs_paise", -1),
        ("payment_fees_paise", None),
    ],
)
def test_invalid_canonical_components(source, field, value):
    rows = [
        json.loads(line)
        for line in (source / "response_observations.jsonl").read_text().splitlines()
    ]
    rows[0][field] = value
    rewrite(source, "response_observations", rows)
    with pytest.raises(ValueError):
        report(source)


def test_incomplete_week_series_is_withheld(source):
    rows = [
        json.loads(line)
        for line in (source / "response_observations.jsonl").read_text().splitlines()
    ]
    rewrite(source, "response_observations", rows[:5] + rows[6:])
    assert report(source)["channels"][0]["curve"]["reason"] == "incomplete_weekly_series"


def test_missing_cost_attestation_fails(source):
    path = source / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["response_contract"]["cost_provenance"] = "assumed"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="observed"):
        report(source)


def test_missing_supplement_and_duplicate_rows(tmp_path, source):
    other = tmp_path / "no-response"
    make_source(other)
    assert report(other)["status"] == "not_assessed"
    rows = [
        json.loads(line)
        for line in (source / "response_observations.jsonl").read_text().splitlines()
    ]
    rewrite(source, "response_observations", rows + [rows[0]])
    with pytest.raises(ValueError, match="duplicate"):
        report(source)


def test_declared_supplement_checksum_is_required(source):
    path = source / "response_observations.jsonl"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="checksum"):
        report(source)
