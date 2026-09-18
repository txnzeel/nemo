"""Fixed-horizon customer ITT analysis from canonical observations, never private truth."""

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from fractions import Fraction
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.economics_inputs import load_inputs, read_table
from nemo.experiment_design import METRICS, boundary, digest, encode, planning, timestamp, validate
from nemo.warehouse import open_warehouse, project_hash


def rational(value):
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def tail_bound(exponent):
    """Keep tiny numerical upper bounds positive rather than reporting impossible zero."""
    return min(1, max(sys.float_info.min, 2 * math.exp(exponent)))


def compare(control, treatment, bounds, alpha, eligible):
    if control is None or treatment is None or not control or not treatment:
        return {"status": "unknown", "incremental_in_treated": None, "interval": None}
    nc, nt = len(control), len(treatment)
    mc, mt = Fraction(sum(control), nc), Fraction(sum(treatment), nt)
    delta = mt - mc
    result = {
        "status": "assessed" if eligible else "descriptive_only",
        "control": {"units": nc, "sum": sum(control), "mean": rational(mc)},
        "treatment": {"units": nt, "sum": sum(treatment), "mean": rational(mt)},
        "absolute_lift": rational(delta),
        "relative_lift": rational(delta / mc) if mc > 0 else None,
        "interval": None,
        "p_value_upper_bound": None,
        "adjusted_p_upper_bound": None,
        "statistically_significant": None,
        "incremental_in_treated": None,
    }
    if eligible:
        width = bounds[1] - bounds[0]
        scale = 1 / nc + 1 / nt
        radius = math.sqrt(0.5 * scale * math.log(2 / (alpha / len(METRICS))))
        center = float(delta / width)
        low, high = max(-1, center - radius) * width, min(1, center + radius) * width
        p_bound = tail_bound(-2 * center**2 / scale)
        result.update(
            interval={
                "lower": low,
                "upper": high,
                "family_confidence": 1 - alpha,
                "method": "Hoeffding_Bonferroni_fixed_family_3",
                "numeric_bounds_are_approximate": True,
            },
            p_value_upper_bound=p_bound,
            adjusted_p_upper_bound=min(1, p_bound * len(METRICS)),
            statistically_significant=p_bound < alpha / len(METRICS),
            incremental_in_treated={
                "point": rational(delta * nt),
                "lower": low * nt,
                "upper": high * nt,
            },
        )
    return result


def report(warehouse: Path, observations: Path, plan_path: Path):
    payload = plan_path.read_bytes()
    plan = validate(json.loads(payload))
    design = planning(plan)
    start, end = boundary(plan["start_date"]), boundary(plan["end_date"])
    with open_warehouse(warehouse) as snapshot:
        public_bytes = (observations / "manifest.json").read_bytes()
        if digest(public_bytes) != snapshot.manifest_sha256:
            raise ValueError("experiment observations do not match warehouse")
        manifest = json.loads(public_bytes)
        contract = manifest.get("experiment_contract", {})
        if contract.get("version") != "1" or contract.get("plan_sha256") != digest(payload):
            raise ValueError("experiment plan is not bound to canonical manifest")
        for key in ("outcomes_complete", "randomization_attested", "assignment_roster_complete"):
            if type(contract.get(key)) is not bool:
                raise ValueError(f"explicit boolean {key} required")
        population = read_table(observations, manifest, "experiment_population")
        assignments = read_table(observations, manifest, "experiment_assignments")
        if population is None or assignments is None:
            raise ValueError("experiment requires a population roster and assignments")
        customers = {
            key: timestamp(stamp)
            for key, stamp in snapshot.connection.execute(
                "SELECT customer_id, first_seen_at FROM analytics.dim_customer"
            ).fetchall()
        }
        roster = [row.get("customer_id") for row in population]
        if any(not isinstance(key, str) or key not in customers for key in roster) or len(
            set(roster)
        ) != len(roster):
            raise ValueError("unknown or duplicate population customer")
        roster_set = set(roster)
        units = {}
        for row in assignments:
            key = row.get("customer_id")
            arm = row.get("arm")
            assigned = timestamp(row["assigned_at"])
            if (
                key not in customers
                or key in units
                or key not in roster_set
                or arm not in ("control", "treatment")
                or row.get("experiment_id") != plan["experiment_id"]
                or not timestamp(plan["registered_at"]) <= assigned < start
                or assigned < customers[key]
            ):
                raise ValueError("invalid, duplicate or late experiment assignment")
            units[key] = {"arm": arm, "orders": 0, "gross": 0, "contribution": 0}
        if set(units) != set(roster):
            raise ValueError("every population customer must have exactly one assignment")
        economics = load_inputs(snapshot, observations)
        costs = {r["order_id"]: r["variable_cost_paise"] for r in economics["costs"]}
        refunds = Counter()
        for row in economics["refunds"]:
            refunds[row["order_id"]] += row["amount_paise"]
        economic_coverage = (
            economics["refunds_complete"]
            and economics["costs_declared"]
            and snapshot.end.isoformat() == plan["end_date"]
        )
        for oid, customer, paid, amount in snapshot.connection.execute(
            "SELECT order_id, customer_id, paid_at, amount_paise FROM analytics.fct_orders"
        ).fetchall():
            if customer not in units or not start <= timestamp(paid) < end:
                continue
            unit = units[customer]
            unit["orders"] += 1
            unit["gross"] += amount
            if (
                economic_coverage
                and costs.get(oid) is not None
                and unit["contribution"] is not None
            ):
                unit["contribution"] += amount - refunds[oid] - costs[oid]
            else:
                unit["contribution"] = None
        contribution_known = economic_coverage and all(
            unit["contribution"] is not None for unit in units.values()
        )
        counts = Counter(unit["arm"] for unit in units.values())
        total = len(units)
        imbalance_p = (
            tail_bound(-2 * (counts["treatment"] - total / 2) ** 2 / total) if total else None
        )
        reasons = []
        if not contract["randomization_attested"]:
            reasons.append("randomization_not_attested")
        if not contract["assignment_roster_complete"]:
            reasons.append("roster_completeness_not_attested")
        if not contract["outcomes_complete"]:
            reasons.append("outcome_completeness_not_attested")
        if boundary(snapshot.end.isoformat()) < end or datetime.now(UTC) < end:
            reasons.append("fixed_horizon_not_complete")
        if boundary(snapshot.start.isoformat()) > start:
            reasons.append("missing_outcome_history")
        if min(counts["control"], counts["treatment"]) < design["required_per_arm"]:
            reasons.append("planned_sample_not_reached")
        if imbalance_p is not None and imbalance_p < 0.001:
            reasons.append("sample_ratio_mismatch")
        eligible = not reasons
        cap, cbounds = plan["gross_cap_paise"], plan["contribution_bounds_paise"]
        outcomes = {metric: {"control": [], "treatment": []} for metric in METRICS}
        clipping = Counter()
        for unit in units.values():
            arm = unit["arm"]
            outcomes[METRICS[0]][arm].append(int(unit["orders"] > 0))
            outcomes[METRICS[1]][arm].append(min(cap, unit["gross"]))
            clipping[METRICS[1]] += unit["gross"] > cap
            if contribution_known:
                value = max(cbounds[0], min(cbounds[1], unit["contribution"]))
                outcomes[METRICS[2]][arm].append(value)
                clipping[METRICS[2]] += value != unit["contribution"]
        metrics = {}
        for metric, bounds in zip(METRICS, ((0, 1), (0, cap), cbounds), strict=True):
            metric_rows = outcomes[metric]
            metrics[metric] = compare(
                metric_rows["control"], metric_rows["treatment"], bounds, plan["alpha"], eligible
            )
            metrics[metric]["outcome_bounds"] = list(bounds)
            metrics[metric]["clipped_customers"] = clipping[metric]
        primary = metrics[METRICS[0]]
        primary["practically_significant"] = (
            primary["interval"]["lower"] >= plan["practical_threshold_absolute"]
            if primary["interval"]
            else None
        )
        guardrails = []
        for spec in plan["guardrails"]:
            interval = metrics[spec["metric"]]["interval"]
            margin = -spec["max_decline_paise"]
            status = (
                "unknown"
                if interval is None
                else (
                    "pass"
                    if interval["lower"] >= margin
                    else "fail"
                    if interval["upper"] < margin
                    else "inconclusive"
                )
            )
            guardrails.append({**spec, "status": status})
        if not eligible:
            result = "not_ready"
        elif primary["interval"]["upper"] < 0 or any(g["status"] == "fail" for g in guardrails):
            result = "harm_detected"
        elif primary["practically_significant"] and primary["statistically_significant"]:
            result = (
                "positive_with_guardrails"
                if all(g["status"] == "pass" for g in guardrails)
                else "benefit_guardrails_unresolved"
            )
        else:
            result = "inconclusive"
        return {
            "schema_version": "1",
            "experiment_id": plan["experiment_id"],
            "claim_type": "causal_result" if eligible else "observed_association",
            "causal_scope": "conditional_customer_ITT_under_declared_randomization_and_coverage",
            "source_mode": snapshot.contract.mode,
            "dataset_id": snapshot.contract.dataset_id,
            "plan": plan,
            "planning": design,
            "result": result,
            "readiness": {"eligible": eligible, "reasons": reasons},
            "assignment": {
                "control": counts["control"],
                "treatment": counts["treatment"],
                "population": total,
                "srm_p_upper_bound": imbalance_p,
                "srm_threshold": 0.001,
                "method": "Hoeffding_fair_Bernoulli_count",
            },
            "metrics": metrics,
            "guardrails": guardrails,
            "economics": {
                "contribution_known": contribution_known,
                "cost_provenance": economics["cost_provenance"],
                "gross_basis": "capped_customer_tax_exclusive_merchandise_before_refunds",
                "contribution_basis": "capped_customer_net_merchandise_minus_declared_order_costs",
                "uncapped_incremental_revenue": None,
                "uncapped_incremental_contribution": None,
            },
            "provenance": {
                "plan_sha256": digest(payload),
                "manifest_sha256": snapshot.manifest_sha256,
                "tables": {name: row["sha256"] for name, row in manifest["tables"].items()},
                "dbt_project_sha256": project_hash(),
                "code_sha256": {
                    name: digest(files("nemo").joinpath(name).read_bytes())
                    for name in ("experiments.py", "experiment_design.py", "economics_inputs.py")
                },
            },
            "limitations": [
                "Randomization, population completeness and historical registration are asserted.",
                "Hashes bind content; they do not prove preregistration or treatment delivery.",
                "Independent customer units, stable identities and no interference are assumed.",
                "Fixed-horizon analysis only; no optional stopping or post-treatment filtering.",
                "Hoeffding bounds are conservative; non-significance is not proof of no effect.",
                "Capped economic estimands are not uncapped revenue or company profit.",
                "Contribution excludes acquisition and fixed costs; absent coverage stays unknown.",
                "Positive_with_guardrails is a review result, not authorization to deploy.",
                "Synthetic results and assumed costs are not real-company causal evidence.",
            ],
        }


def save_result(value, directory):
    directory.mkdir(parents=True, exist_ok=True)
    payload = encode(value)
    path = directory / (digest(payload) + ".json")
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("result fingerprint collision")
    else:
        with path.open("xb") as stream:
            stream.write(payload)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEMO fixed-horizon customer experiments")
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = report(args.warehouse, args.observations, args.plan)
        path = save_result(result, args.output_directory)
        print(json.dumps({"result": result["result"], "report": str(path)}))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
