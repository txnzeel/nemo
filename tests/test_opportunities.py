"""Opportunity rules preserve canonical evidence, upstream gates and unknown forward value."""

import copy
import json
import shutil
import subprocess
import sys
from datetime import date

import pytest
from test_decision_case import scenarios as scenarios
from test_experiments import manual as manual
from test_journeys import journey_source as journey_source

from nemo import opportunities
from nemo.experiments import report as experiment_report
from nemo.opportunities import _experiment_candidate, main, report, save_report
from nemo.warehouse import build_warehouse


def case_report(scenarios, kind, **kwargs):
    source, database, _ = scenarios[kind]
    return report(
        database, source, baseline_start=date(2025, 1, 1), current_start=date(2025, 1, 2), **kwargs
    )


def test_healthy_control_has_no_invented_opportunity(scenarios):
    value = case_report(scenarios, "healthy")
    assert value["opportunities"] == []
    assert value["summary"] == {"proposed": 0, "blocked": 0}


def test_payment_hypothesis_has_bounded_next_step(scenarios):
    value = case_report(scenarios, "business")
    (item,) = value["opportunities"]
    assert item["type"] == "INVESTIGATE"
    assert item["status"] == "proposed"
    assert item["decision_case_id"] == scenarios["business"][2]["case_id"]
    assert item["evidence_strength"] == "observational_hypothesis"
    assert item["execution"] == "manual_review_only"
    assert item["estimated_value"] is None and item["value_range"] is None
    assert item["historical_effect"] is None
    assert item["confidence"]["calibrated_probability"] is None
    assert item["effort"]["hours"] is None
    assert "tablet" in item["evidence"]["supported_devices"]
    assert item["recommended_next_step"]


def test_tracking_issue_never_becomes_a_business_fix(scenarios):
    value = case_report(scenarios, "tracking")
    assert [c["type"] for c in value["opportunities"]] == ["MEASUREMENT"]
    assert value["opportunities"][0]["evidence_strength"] == "measurement_assessment"


def test_payment_suppression_is_preserved(scenarios, monkeypatch):
    original = opportunities.build_case

    def blocked(*args, **kwargs):
        value = original(*args, **kwargs)
        candidate = value["recommendations"]["measurement_eligible"].pop()
        value["recommendations"]["suppressed"].append(
            {"candidate": candidate, "reasons": ["payment_funnel:not_assessed"]}
        )
        return value

    monkeypatch.setattr(opportunities, "build_case", blocked)
    (item,) = case_report(scenarios, "business")["opportunities"]
    assert item["status"] == "blocked"
    assert item["blockers"] == ["payment_funnel:not_assessed"]


def test_experiment_history_is_not_forecast_and_needs_no_optional_event_feed(manual):
    source, plan, database = manual
    value = report(database, source, experiment_plan=plan)
    (item,) = value["opportunities"]
    assert item["rule"] == "experiment_review"
    assert item["type"] == "INVESTIGATE"
    assert item["historical_effect"]["not_forward_opportunity_value"]
    assert item["historical_effect"]["scope"] == "completed_experiment_treated_cohort_only"
    assert item["estimated_value"] is None and item["value_range"] is None
    assert item["evidence_strength"] == "conditional_randomized_experiment"
    assert "uncapped" in item["recommended_next_step"]
    assert value["summary"] == {"proposed": 1, "blocked": 0}


@pytest.mark.parametrize(
    "state,rule,kind,priority",
    [
        ("harm_detected", "experiment_harm", "INVESTIGATE", 20),
        ("inconclusive", "experiment_followup", "EXPERIMENT", 60),
        ("benefit_guardrails_unresolved", "experiment_review", "INVESTIGATE", 40),
    ],
)
def test_experiment_state_mapping_preserves_scope(manual, state, rule, kind, priority):
    source, plan, database = manual
    evidence = experiment_report(database, source, plan)
    evidence["result"] = state
    item = _experiment_candidate("manual", evidence, {"sha256": "test-reference"})
    assert (item["rule"], item["type"], item["review_priority"]) == (rule, kind, priority)
    assert item["execution"] == "manual_review_only"
    assert item["estimated_value"] is None


def test_not_ready_experiment_cannot_supply_incremental_opportunity_value(manual):
    source, plan, database = manual
    value = experiment_report(database, source, plan)
    value["readiness"] = {"eligible": False, "reasons": ["sample_ratio_mismatch"]}
    value["result"] = "not_ready"
    item = _experiment_candidate("manual", value, {})
    assert item["type"] == "MEASUREMENT"
    assert item["historical_effect"] is None
    assert item["evidence_strength"] == "observed_association"
    value["readiness"]["eligible"] = True
    value["result"] = "unsupported"
    with pytest.raises(ValueError, match="unsupported"):
        _experiment_candidate("manual", value, {})


def test_attribution_disagreement_retains_gate_and_threshold(journey_source):
    source, database = journey_source
    value = report(database, source, include_attribution=True)
    (item,) = value["opportunities"]
    assert item["type"] == "EXPERIMENT"
    assert item["status"] == "blocked"
    assert "purchase_tracking:not_assessed" in item["blockers"]
    assert "attribution_contract:not_assessed" in item["blockers"]
    assert item["evidence_strength"] == "model_dependence_not_causal"
    assert item["estimated_value"] is None
    quiet = report(
        database, source, include_attribution=True, minimum_attribution_range_paise=10**30
    )
    assert not quiet["opportunities"]


def test_priority_order_and_deterministic_replay(manual):
    source, plan, database = manual
    kwargs = {
        "baseline_start": date(2025, 1, 1),
        "current_start": date(2025, 1, 5),
        "experiment_plan": plan,
    }
    value = report(database, source, **kwargs)
    assert value == report(database, source, **kwargs)
    items = value["opportunities"]
    assert len(items) >= 2
    assert items[0]["review_priority"] == 10
    assert [c["rank"] for c in items] == list(range(1, len(items) + 1))
    assert items[-1]["rule"] == "experiment_review"


def test_stable_identity_revision_and_immutable_storage(scenarios, tmp_path):
    first = case_report(scenarios, "business")
    second = case_report(scenarios, "business", minimum_attribution_range_paise=200000)
    assert (
        first["opportunities"][0]["opportunity_id"] == second["opportunities"][0]["opportunity_id"]
    )
    assert first["revision_id"] != second["revision_id"]
    path = save_report(first, tmp_path)
    assert save_report(first, tmp_path) == path
    assert save_report(second, tmp_path) != path
    corrupt = copy.deepcopy(first)
    corrupt["summary"]["proposed"] = 100
    with pytest.raises(ValueError, match="revision"):
        save_report(corrupt, tmp_path)
    assert json.loads(path.read_bytes()) == first


@pytest.mark.parametrize(
    "kwargs",
    [
        {"baseline_start": date(2025, 1, 1)},
        {"minimum_attribution_range_paise": 0},
        {"minimum_attribution_range_paise": True},
        {"include_attribution": "yes"},
    ],
)
def test_invalid_parameters(scenarios, kwargs):
    source, database, _ = scenarios["healthy"]
    with pytest.raises(ValueError):
        report(database, source, **kwargs)


def test_wrong_source_and_mid_analysis_change_fail_closed(scenarios, monkeypatch):
    source, database, _ = scenarios["business"]
    with pytest.raises(ValueError, match="match"):
        report(database, scenarios["healthy"][0])
    original = opportunities.assess

    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        value["manifest_sha256"] = "different"
        return value

    monkeypatch.setattr(opportunities, "assess", changed)
    with pytest.raises(ValueError, match="source changed"):
        report(database, source)


def test_cli_roundtrip_and_private_boundary(scenarios, tmp_path):
    source, database, _ = scenarios["business"]
    assert (
        main(
            [
                "--warehouse",
                str(database),
                "--observations",
                str(source),
                "--baseline-start",
                "2025-01-01",
                "--current-start",
                "2025-01-02",
                "--output-directory",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert len(list(tmp_path.glob("*.json"))) == 1
    code = """import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('nemo.simulation','nemo.contracts','nemo.artifacts',
                        'nemo.lab_experiments','nemo.lab_payment','nemo.lab_tracking'):
            raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
def guard(event,args):
    if event == 'open' and isinstance(args[0],str):
        if 'private' in args[0] or 'run.json' in args[0]:
            raise AssertionError(args[0])
sys.addaudithook(guard)
from datetime import date
from pathlib import Path
from nemo.opportunities import report
v=report(Path(sys.argv[1]),Path(sys.argv[2]),
         baseline_start=date(2025,1,1),current_start=date(2025,1,2))
assert v['summary']=={'proposed':1,'blocked':0}
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(database), str(source)],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_missing_funnel_contract_with_healthy_purchase_tracking(scenarios, tmp_path):
    source = tmp_path / "observations"
    shutil.copytree(scenarios["healthy"][0], source)
    path = source / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest.pop("funnel_contract")
    path.write_text(json.dumps(manifest))
    database = tmp_path / "nemo.duckdb"
    build_warehouse(source, database)
    value = report(
        database, source, baseline_start=date(2025, 1, 1), current_start=date(2025, 1, 2)
    )
    (item,) = value["opportunities"]
    assert item["rule"] == "funnel_measurement"
    assert item["type"] == "MEASUREMENT"
    assert item["evidence"]["dependencies"]["purchase_tracking"] == "high"
    assert item["evidence"]["dependencies"]["payment_funnel"] == "not_assessed"
