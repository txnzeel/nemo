"""Hand-authored fixed-cohort experiments, inference gates and exact outcome arithmetic."""

import json
import math
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest
from test_economics import rewrite

from nemo.economics_inputs import COST_COMPONENTS
from nemo.experiment_design import METRICS, assign, digest, encode, planning, register, validate
from nemo.experiments import compare, report, save_result, tail_bound
from nemo.warehouse import build_warehouse


def plan_spec():
    return {
        "version": "1",
        "experiment_id": "manual-checkout",
        "hypothesis": "Checkout changes buying probability",
        "population": "Pre-enrolled customers",
        "treatment": "New checkout",
        "control": "Current checkout",
        "randomization": "bernoulli_customer_1_to_1",
        "allocation": {"control": 0.5, "treatment": 0.5},
        "primary_metric": METRICS[0],
        "registered_at": "2024-12-31T00:00:00Z",
        "start_date": "2025-01-02",
        "end_date": "2025-01-09",
        "alpha": 0.05,
        "power": 0.8,
        "mde_absolute": 0.2,
        "practical_threshold_absolute": 0.05,
        "gross_cap_paise": 100000,
        "contribution_bounds_paise": [-50000, 50000],
        "guardrails": [
            {"metric": METRICS[1], "max_decline_paise": 5000},
            {"metric": METRICS[2], "max_decline_paise": 5000},
        ],
    }


def make_manual(root):
    source = root / "observations"
    source.mkdir(parents=True)
    plan = root / "plan.json"
    plan.write_bytes(encode(plan_spec()))
    manifest = {
        "schema_version": "2",
        "mode": "production",
        "dataset_id": "manual-experiment",
        "channels": {"direct": False},
        "devices": ["tablet"],
        "currency": "INR",
        "money_unit": "paise",
        "amount_basis": "tax_exclusive_merchandise",
        "business_timezone": "Asia/Kolkata",
        "timestamp_timezone": "UTC",
        "observation_window": {
            "start_date_inclusive": "2025-01-01",
            "end_date_exclusive": "2025-01-09",
        },
        "experiment_contract": {
            "version": "1",
            "plan_sha256": digest(plan.read_bytes()),
            "randomization_attested": True,
            "outcomes_complete": True,
            "assignment_roster_complete": True,
        },
        "economics_contract": {
            "version": "1",
            "refunds": {
                "basis": "tax_exclusive_merchandise",
                "coverage_end_exclusive": "2025-01-09",
            },
            "variable_costs": {
                "basis": "order_costs_net_of_recoveries",
                "coverage_end_exclusive": "2025-01-09",
                "components": list(COST_COMPONENTS),
                "provenance": "observed",
            },
        },
        "tables": {},
    }
    (source / "manifest.json").write_bytes(encode(manifest))
    tables = {
        name: []
        for name in (
            "customers",
            "campaigns",
            "ad_performance",
            "sessions",
            "orders",
            "order_items",
            "refunds",
            "order_variable_costs",
            "experiment_population",
            "experiment_assignments",
        )
    }
    for arm, buyers in (("control", 90), ("treatment", 240)):
        for i in range(600):
            key = f"{arm}-{i:03d}"
            tables["customers"].append(
                {"customer_id": key, "first_seen_at": "2025-01-01T00:00:00Z"}
            )
            tables["experiment_population"].append({"customer_id": key})
            tables["experiment_assignments"].append(
                {
                    "experiment_id": "manual-checkout",
                    "customer_id": key,
                    "arm": arm,
                    "assigned_at": "2025-01-01T06:00:00Z",
                }
            )
            if i >= buyers:
                continue
            tables["sessions"].append(
                {
                    "session_id": key,
                    "customer_id": key,
                    "started_at": "2025-01-03T00:00:00Z",
                    "channel": "direct",
                    "campaign_id": None,
                    "device": "tablet",
                }
            )
            tables["orders"].append(
                {
                    "order_id": key,
                    "customer_id": key,
                    "session_id": key,
                    "paid_at": "2025-01-03T00:05:00Z",
                    "amount_paise": 100000,
                }
            )
            tables["order_items"].append(
                {
                    "order_item_id": key,
                    "order_id": key,
                    "product_id": "sku",
                    "quantity": 1,
                    "unit_price_paise": 100000,
                    "amount_paise": 100000,
                }
            )
            tables["order_variable_costs"].append(
                {
                    "order_id": key,
                    **{c: 50000 if c == "net_cogs_paise" else 0 for c in COST_COMPONENTS},
                }
            )
    for name, rows in tables.items():
        rewrite(source, name, rows)
    return source, plan


@pytest.fixture(scope="module")
def manual(tmp_path_factory):
    root = tmp_path_factory.mktemp("experiment")
    source, plan = make_manual(root)
    database = root / "nemo.duckdb"
    build_warehouse(source, database)
    return source, plan, database


def changed(manual, tmp_path):
    source, plan, _ = manual
    target = tmp_path / "observations"
    shutil.copytree(source, target)
    copied_plan = tmp_path / "plan.json"
    shutil.copyfile(plan, copied_plan)
    return target, copied_plan


def read_rows(source, name):
    return [json.loads(line) for line in (source / f"{name}.jsonl").read_text().splitlines()]


def modify_manifest(source, change):
    path = source / "manifest.json"
    value = json.loads(path.read_bytes())
    change(value)
    path.write_bytes(encode(value))


def build_report(source, plan, tmp_path):
    database = tmp_path / "nemo.duckdb"
    build_warehouse(source, database)
    return report(database, source, plan)


def exact(value):
    return Fraction(value["numerator"], value["denominator"])


def test_hand_calculated_itt_including_nonbuyers(manual):
    source, plan, database = manual
    result = report(database, source, plan)
    primary = result["metrics"][METRICS[0]]
    assert primary["control"]["units"] == primary["treatment"]["units"] == 600
    assert primary["control"]["sum"] == 90
    assert primary["treatment"]["sum"] == 240
    assert exact(primary["absolute_lift"]) == Fraction(1, 4)
    assert exact(primary["relative_lift"]) == Fraction(5, 3)
    assert exact(primary["incremental_in_treated"]["point"]) == 150
    assert result["result"] == "positive_with_guardrails"
    assert primary["statistically_significant"] and primary["practically_significant"]
    assert result["claim_type"] == "causal_result"
    assert exact(result["metrics"][METRICS[1]]["absolute_lift"]) == 25000
    assert exact(result["metrics"][METRICS[2]]["incremental_in_treated"]["point"]) == 7500000
    assert result["economics"]["uncapped_incremental_revenue"] is None


def test_hoeffding_interval_and_conservative_planning():
    plan = plan_spec()
    target = planning(plan)
    required = math.ceil((math.sqrt(math.log(120)) + math.sqrt(math.log(5))) ** 2 / 0.2**2)
    assert target["required_per_arm"] == required
    assert target["duration_days"] == 7
    value = compare([0] * 100, [1] * 100, (0, 1), 0.05, True)
    radius = math.sqrt(math.log(120) / 100)
    assert value["interval"]["lower"] == pytest.approx(1 - radius)
    assert value["interval"]["upper"] == 1
    assert value["p_value_upper_bound"] == pytest.approx(2 * math.exp(-100))
    null = compare([0] * 100, [0] * 100, (0, 1), 0.05, True)
    assert null["relative_lift"] is None and not null["statistically_significant"]
    money = compare([2**63 - 2], [2**63 - 1], (0, 2**63 - 1), 0.05, True)
    assert exact(money["absolute_lift"]) == 1
    assert compare([], [], (0, 1), 0.05, False)["status"] == "unknown"


@pytest.mark.parametrize(
    "field,value",
    [
        ("mde_absolute", 0),
        ("power", 1),
        ("alpha", float("nan")),
        ("gross_cap_paise", True),
        ("contribution_bounds_paise", [0, 1]),
        ("guardrails", []),
        ("primary_metric", "attributed_revenue"),
        ("randomization", "self_selected"),
        ("registered_at", "2025-01-03T00:00:00Z"),
    ],
)
def test_invalid_design(field, value):
    spec = plan_spec()
    spec[field] = value
    with pytest.raises(ValueError):
        validate(spec)


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("incomplete", "outcome_completeness_not_attested"),
        ("unattested", "randomization_not_attested"),
        ("roster", "roster_completeness_not_attested"),
        ("srm", "sample_ratio_mismatch"),
        ("early", "fixed_horizon_not_complete"),
        ("underpowered", "planned_sample_not_reached"),
    ],
)
def test_inference_readiness_gates(manual, tmp_path, kind, reason):
    source, plan = changed(manual, tmp_path)
    if kind in ("incomplete", "unattested", "roster"):
        key = {
            "incomplete": "outcomes_complete",
            "unattested": "randomization_attested",
            "roster": "assignment_roster_complete",
        }[kind]
        modify_manifest(source, lambda m: m["experiment_contract"].update({key: False}))
    elif kind == "srm":
        rows = read_rows(source, "experiment_assignments")
        for row in rows[:500]:
            row["arm"] = "treatment"
        rewrite(source, "experiment_assignments", rows)
    else:
        spec = json.loads(plan.read_bytes())
        if kind == "early":
            spec["end_date"] = "2025-01-10"
        else:
            spec["mde_absolute"] = 0.01
        plan.write_bytes(encode(spec))
        modify_manifest(
            source, lambda m: m["experiment_contract"].update(plan_sha256=digest(plan.read_bytes()))
        )
    result = build_report(source, plan, tmp_path)
    assert reason in result["readiness"]["reasons"]
    assert result["result"] == "not_ready"
    assert result["claim_type"] == "observed_association"
    assert result["metrics"][METRICS[0]]["incremental_in_treated"] is None
    assert result["metrics"][METRICS[0]]["interval"] is None


@pytest.mark.parametrize("kind", ["duplicate", "missing", "late", "unknown"])
def test_assignment_integrity(manual, tmp_path, kind):
    source, plan = changed(manual, tmp_path)
    rows = read_rows(source, "experiment_assignments")
    if kind == "duplicate":
        rows.append(rows[0])
    elif kind == "missing":
        rows.pop()
    elif kind == "late":
        rows[0]["assigned_at"] = "2025-01-03T00:00:00Z"
    else:
        rows[0]["customer_id"] = "absent"
    rewrite(source, "experiment_assignments", rows)
    with pytest.raises(ValueError, match="assignment"):
        build_report(source, plan, tmp_path)


def test_missing_costs_remain_unknown(manual, tmp_path):
    source, plan = changed(manual, tmp_path)
    rows = read_rows(source, "order_variable_costs")
    rows[0]["net_cogs_paise"] = None
    rewrite(source, "order_variable_costs", rows)
    result = build_report(source, plan, tmp_path)
    assert result["metrics"][METRICS[2]]["status"] == "unknown"
    assert result["result"] == "benefit_guardrails_unresolved"


def test_caps_are_explicit_estimands(manual, tmp_path):
    source, plan = changed(manual, tmp_path)
    spec = json.loads(plan.read_bytes())
    spec["gross_cap_paise"] = 50000
    spec["contribution_bounds_paise"] = [-10000, 10000]
    plan.write_bytes(encode(spec))
    modify_manifest(
        source, lambda m: m["experiment_contract"].update(plan_sha256=digest(plan.read_bytes()))
    )
    result = build_report(source, plan, tmp_path)
    assert result["metrics"][METRICS[1]]["clipped_customers"] == 330
    assert exact(result["metrics"][METRICS[1]]["absolute_lift"]) == 12500
    assert exact(result["metrics"][METRICS[2]]["absolute_lift"]) == 2500


def test_source_and_plan_binding_and_memory(manual, tmp_path):
    source, plan, database = manual
    result = report(database, source, plan)
    first = save_result(result, tmp_path / "results")
    assert save_result(result, tmp_path / "results") == first
    revised = {**result, "result": "revised"}
    assert save_result(revised, tmp_path / "results") != first
    wrong = tmp_path / "wrong-plan.json"
    wrong.write_bytes(plan.read_bytes() + b" ")
    with pytest.raises(ValueError, match="bound"):
        report(database, source, wrong)
    copied, _ = changed(manual, tmp_path)
    (copied / "manifest.json").write_bytes((copied / "manifest.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="match"):
        report(database, copied, plan)


def test_prospective_registration_and_saved_random_assignment(tmp_path):
    spec = plan_spec()
    spec["start_date"] = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    spec["end_date"] = (datetime.now(UTC) + timedelta(days=9)).date().isoformat()
    plan = tmp_path / "plan.json"
    register(spec, plan)
    population = tmp_path / "population.json"
    population.write_bytes(encode([f"customer-{i}" for i in range(100)]))
    output = tmp_path / "ledger"
    receipt = assign(plan, population, output)
    rows = read_rows(output, "experiment_assignments")
    assert len(rows) == len({r["customer_id"] for r in rows}) == 100
    assert all(r["arm"] in ("control", "treatment") for r in rows)
    assert receipt["plan_sha256"] == digest(plan.read_bytes())
    with pytest.raises(FileExistsError):
        assign(plan, population, output)
    with pytest.raises(FileExistsError):
        register(spec, plan)


def test_no_generator_or_private_state(manual):
    source, plan, database = manual
    code = """import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('nemo.simulation','nemo.contracts','nemo.artifacts',
                        'nemo.lab_experiments','nemo.lab_economics'):
            raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
def guard(event,args):
    if event == 'open' and isinstance(args[0],str):
        if 'private' in args[0] or 'run.json' in args[0]:
            raise AssertionError(args[0])
sys.addaudithook(guard)
from pathlib import Path
from nemo.experiments import report
result=report(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
assert result['result']=='positive_with_guardrails'
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(database), str(source), str(plan)],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("field,value", [("start_date", "2025-01-04"), ("end_date", "2025-01-03")])
def test_outside_window_orders_are_excluded(manual, tmp_path, field, value):
    source, plan = changed(manual, tmp_path)
    spec = json.loads(plan.read_bytes())
    spec[field] = value
    plan.write_bytes(encode(spec))
    modify_manifest(
        source, lambda m: m["experiment_contract"].update(plan_sha256=digest(plan.read_bytes()))
    )
    result = build_report(source, plan, tmp_path)
    primary = result["metrics"][METRICS[0]]
    assert primary["control"]["sum"] == primary["treatment"]["sum"] == 0
    assert primary["control"]["units"] == primary["treatment"]["units"] == 600
    assert primary["relative_lift"] is None
    assert not primary["statistically_significant"]


def test_harm_is_distinct_from_inconclusive(manual, tmp_path):
    source, plan = changed(manual, tmp_path)
    rows = read_rows(source, "experiment_assignments")
    for row in rows:
        row["arm"] = "treatment" if row["arm"] == "control" else "control"
    rewrite(source, "experiment_assignments", rows)
    result = build_report(source, plan, tmp_path)
    assert result["result"] == "harm_detected"
    assert result["metrics"][METRICS[0]]["interval"]["upper"] < 0
    assert any(g["status"] == "fail" for g in result["guardrails"])


def test_tiny_tail_bounds_remain_positive():
    assert tail_bound(-10000) == sys.float_info.min
    assert tail_bound(0) == 1
