"""Controlled experiment demo producer; hidden recipes never enter analytical inputs."""

import argparse
import json
import random
from pathlib import Path

from nemo.economics_inputs import COST_COMPONENTS
from nemo.experiment_design import METRICS, digest, encode


def demo_plan():
    return {
        "version": "1",
        "experiment_id": "checkout-2025-01",
        "hypothesis": "A revised checkout increases customer purchase probability",
        "population": "Pre-enrolled canonical customers, including nonbuyers",
        "treatment": "Revised checkout",
        "control": "Existing checkout",
        "randomization": "bernoulli_customer_1_to_1",
        "allocation": {"control": 0.5, "treatment": 0.5},
        "primary_metric": METRICS[0],
        "mde_absolute": 0.2,
        "practical_threshold_absolute": 0.05,
        "alpha": 0.05,
        "power": 0.8,
        "registered_at": "2024-12-31T00:00:00Z",
        "start_date": "2025-01-02",
        "end_date": "2025-01-09",
        "gross_cap_paise": 100000,
        "contribution_bounds_paise": [-100000, 100000],
        "guardrails": [
            {"metric": METRICS[1], "max_decline_paise": 5000},
            {"metric": METRICS[2], "max_decline_paise": 5000},
        ],
    }


def prepare(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    private = output / "private"
    private.mkdir()
    recipes = {}
    for scenario in ("effect", "no_effect", "allocation_mismatch"):
        source = output / scenario / "observations"
        source.mkdir(parents=True)
        plan = demo_plan()
        (output / scenario / "plan.json").write_bytes(encode(plan))
        assignments_rng, outcomes_rng = random.Random(1051), random.Random(9907)
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
        for i in range(4000):
            customer, session = f"customer-{i:05d}", f"session-{i:05d}"
            arm = (
                "treatment"
                if assignments_rng.random() < (0.9 if scenario == "allocation_mismatch" else 0.5)
                else "control"
            )
            tables["customers"].append(
                {"customer_id": customer, "first_seen_at": "2025-01-01T00:00:00Z"}
            )
            tables["experiment_population"].append({"customer_id": customer})
            tables["experiment_assignments"].append(
                {
                    "experiment_id": plan["experiment_id"],
                    "customer_id": customer,
                    "arm": arm,
                    "assigned_at": "2025-01-01T06:00:00Z",
                }
            )
            tables["sessions"].append(
                {
                    "session_id": session,
                    "customer_id": customer,
                    "started_at": "2025-01-03T00:00:00Z",
                    "channel": "direct",
                    "campaign_id": None,
                    "device": "desktop",
                }
            )
            probability = 0.4 if arm == "treatment" and scenario != "no_effect" else 0.15
            if outcomes_rng.random() >= probability:
                continue
            oid = f"order-{i:05d}"
            tables["orders"].append(
                {
                    "order_id": oid,
                    "session_id": session,
                    "customer_id": customer,
                    "paid_at": "2025-01-03T00:05:00Z",
                    "amount_paise": 100000,
                }
            )
            tables["order_items"].append(
                {
                    "order_item_id": f"item-{i:05d}",
                    "order_id": oid,
                    "product_id": "sku-1",
                    "quantity": 1,
                    "unit_price_paise": 100000,
                    "amount_paise": 100000,
                }
            )
            tables["order_variable_costs"].append(
                {
                    "order_id": oid,
                    **{key: 50000 if key == "net_cogs_paise" else 0 for key in COST_COMPONENTS},
                }
            )
        manifest = {
            "schema_version": "2",
            "mode": "synthetic",
            "dataset_id": f"experiment-{scenario}",
            "channels": {"direct": False},
            "devices": ["desktop"],
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
                "plan_sha256": digest(encode(plan)),
                "outcomes_complete": True,
                "randomization_attested": True,
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
                    "provenance": "synthetic_assumption",
                },
            },
            "tables": {},
        }
        for name, rows in tables.items():
            payload = b"".join((json.dumps(row, sort_keys=True) + "\n").encode() for row in rows)
            (source / f"{name}.jsonl").write_bytes(payload)
            manifest["tables"][name] = {"rows": len(rows), "sha256": digest(payload)}
        (source / "manifest.json").write_bytes(encode(manifest))
        recipes[scenario] = {
            "assignment_seed": 1051,
            "outcome_seed": 9907,
            "control_probability": 0.15,
            "treatment_probability": 0.15 if scenario == "no_effect" else 0.4,
            "actual_treatment_allocation": 0.9 if scenario == "allocation_mismatch" else 0.5,
            "cost_assumption": "50000 paise net COGS per order, other costs zero",
            "warning": "Historical synthetic scenario; no live preregistration or deployment",
        }
    (private / "truth.json").write_bytes(encode(recipes))
    return {"output": str(output), "scenarios": list(recipes)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate isolated canonical experiment lab scenarios"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
