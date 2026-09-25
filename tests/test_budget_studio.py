"""Compare concave-grid allocation with exhaustive feasible enumeration."""

import copy
from fractions import Fraction

import pytest

from nemo.budget_studio import allocate
from nemo.experiment_design import digest, encode


def evidence():
    base = {
        "status": "estimated",
        "claim_type": "observational_response_model",
        "family": "a_times_spend_over_b_plus_spend",
        "a_paise": 3000000.0,
        "b_paise": 100000.0,
        "support_paise": [10000, 500000],
        "error_half_width_paise": 10000.0,
        "action_eligibility": "scenario_only",
    }
    value = {
        "schema_version": "1",
        "claim_type": "observational_response_analysis",
        "scope": {"dataset_id": "manual-budget", "mode": "production"},
        "channels": [
            {"channel": "search", "curve": base},
            {"channel": "social", "curve": {**base, "a_paise": 2500000.0, "b_paise": 200000.0}},
        ],
    }
    return signed(value)


def signed(value):
    value.pop("revision_id", None)
    value["revision_id"] = digest(encode(value))
    return value


def specification():
    return {
        "period_days": 7,
        "total_budget_paise": 450000,
        "step_paise": 10000,
        "experiment_reserve_paise": 50000,
        "channels": [
            {
                "channel": channel,
                "current_spend_paise": 200000,
                "min_spend_paise": 10000,
                "max_spend_paise": 500000,
                "min_share_bps": 0,
                "max_share_bps": 10000,
                "max_change_bps": 5000,
            }
            for channel in ("search", "social")
        ],
    }


def response(x, a, b):
    return Fraction(a * x, b + x)


def test_optimum_matches_brute_force_and_budget_exact():
    result = allocate(evidence(), specification())
    values = {r["channel"]: r["selected_spend_paise"] for r in result["allocation"]}
    possible = [
        response(x, 3000000, 100000) + response(400000 - x, 2500000, 200000)
        for x in range(100000, 300001, 10000)
    ]
    actual = response(values["search"], 3000000, 100000) + response(
        values["social"], 2500000, 200000
    )
    assert actual == max(possible)
    assert sum(values.values()) + result["experiment_reserve_paise"] == 450000
    assert result["total_spend_paise"] == 450000
    assert result["total_expected_contribution_paise"] is None
    assert result["claim_type"] == "conditional_optimization_scenario"
    assert result["action_eligibility"] == "controlled_review_only"
    for s in result["sensitivity"]:
        assert sum(s["allocation_paise"].values()) == 400000
        assert all(100000 <= v <= 300000 and v % 10000 == 0 for v in s["allocation_paise"].values())
    assert allocate(evidence(), specification()) == result


def test_share_constraints_are_enforced():
    spec = specification()
    spec["channels"][0]["min_share_bps"] = 5000
    result = allocate(evidence(), spec)
    row = next(r for r in result["allocation"] if r["channel"] == "search")
    assert row["effective_min_paise"] == 230000
    assert row["selected_spend_paise"] >= 230000


@pytest.mark.parametrize(
    "kind", ["too_small", "too_large", "off_grid", "unknown", "period", "reserve", "duplicates"]
)
def test_infeasible_or_invalid_never_silently_relaxed(kind):
    spec = specification()
    if kind == "too_small":
        spec["total_budget_paise"] = 100000
    elif kind == "too_large":
        spec["total_budget_paise"] = 1000000
    elif kind == "off_grid":
        spec["total_budget_paise"] += 1
    elif kind == "unknown":
        spec["channels"][0]["channel"] = "unknown"
    elif kind == "period":
        spec["period_days"] = 30
    elif kind == "reserve":
        spec["experiment_reserve_paise"] = 500000
    else:
        spec["channels"].append(copy.deepcopy(spec["channels"][0]))
    with pytest.raises(ValueError):
        allocate(evidence(), spec)


def test_invalid_evidence_and_withheld_curve():
    value = evidence()
    value["scope"]["dataset_id"] = "tampered"
    with pytest.raises(ValueError, match="revision"):
        allocate(value, specification())
    value = evidence()
    value["channels"][0]["curve"] = {"status": "not_assessed"}
    with pytest.raises(ValueError, match="curve"):
        allocate(signed(value), specification())


def test_current_outside_support_fails():
    spec = specification()
    spec["channels"][0]["current_spend_paise"] = 0
    with pytest.raises(ValueError, match="range"):
        allocate(evidence(), spec)


def test_cli_protects_files_and_invalid_evidence(tmp_path):
    from nemo.budget_studio import main

    response_file, spec_file = tmp_path / "response.json", tmp_path / "spec.json"
    response_file.write_bytes(encode(evidence()))
    spec_file.write_bytes(encode(specification()))
    args = [
        "--response",
        str(response_file),
        "--spec",
        str(spec_file),
        "--output",
        str(tmp_path / "allocation.json"),
    ]
    assert main(args) == 0
    assert main(args) == 1
    response_file.write_text("[]")
    assert main(args) == 1
