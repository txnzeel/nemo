"""Versioned fixed-horizon experiment plans and outcome-independent assignment."""

import argparse
import hashlib
import json
import math
import secrets
from datetime import UTC, date, datetime, time
from pathlib import Path

from nemo.observations import BUSINESS_ZONE

METRICS = ("purchase_probability", "capped_gross_merchandise_paise", "capped_contribution_paise")


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("experiment timestamp must be text")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError("experiment timestamps must be aware UTC")
    return result


def boundary(day):
    return datetime.combine(date.fromisoformat(day), time(), BUSINESS_ZONE).astimezone(UTC)


def validate(plan):
    if not isinstance(plan, dict) or plan.get("version") != "1":
        raise ValueError("unsupported experiment plan")
    for key in ("experiment_id", "hypothesis", "population", "treatment", "control"):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            raise ValueError(f"missing experiment {key}")
    if plan.get("randomization") != "bernoulli_customer_1_to_1" or plan.get("allocation") != {
        "control": 0.5,
        "treatment": 0.5,
    }:
        raise ValueError("only independent customer 50/50 Bernoulli allocation is supported")
    if plan.get("primary_metric") != METRICS[0]:
        raise ValueError("unsupported primary metric")
    for key, low, high in (
        ("alpha", 0, 0.2),
        ("power", 0.5, 1),
        ("mde_absolute", 0.000001, 1),
        ("practical_threshold_absolute", 0, 1),
    ):
        value = plan.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not low < value < high:
            raise ValueError(f"invalid {key}")
    start, end = boundary(plan["start_date"]), boundary(plan["end_date"])
    if not timestamp(plan["registered_at"]) < start < end:
        raise ValueError("registration must precede a nonempty outcome window")
    cap = plan.get("gross_cap_paise")
    bounds = plan.get("contribution_bounds_paise")
    if type(cap) is not int or not 0 < cap <= 2**63 - 1:
        raise ValueError("invalid gross cap")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or any(type(x) is not int or abs(x) > 2**63 - 1 for x in bounds)
        or not bounds[0] < 0 < bounds[1]
    ):
        raise ValueError("contribution bounds must straddle zero")
    guardrails = plan.get("guardrails")
    if not isinstance(guardrails, list) or not guardrails:
        raise ValueError("at least one economic guardrail is required")
    seen = set()
    for guardrail in guardrails:
        if (
            not isinstance(guardrail, dict)
            or guardrail.get("metric") not in METRICS[1:]
            or guardrail["metric"] in seen
            or type(guardrail.get("max_decline_paise")) is not int
            or not 0 <= guardrail["max_decline_paise"] <= 2**63 - 1
        ):
            raise ValueError("invalid or duplicate guardrail")
        seen.add(guardrail["metric"])
    return plan


def planning(plan):
    validate(plan)
    alpha = plan["alpha"] / len(METRICS)
    required = math.ceil(
        (math.sqrt(math.log(2 / alpha)) + math.sqrt(math.log(1 / (1 - plan["power"])))) ** 2
        / plan["mde_absolute"] ** 2
    )
    return {
        "required_per_arm": required,
        "required_total_if_balanced": required * 2,
        "duration_days": (
            date.fromisoformat(plan["end_date"]) - date.fromisoformat(plan["start_date"])
        ).days,
        "method": "Hoeffding_sufficient_positive_MDE_target",
        "family_size": len(METRICS),
        "alpha_per_metric": alpha,
    }


def register(spec, output):
    plan = {**spec, "registered_at": datetime.now(UTC).isoformat()}
    validate(plan)
    with output.open("xb") as stream:
        stream.write(encode(plan))
    return {"plan_sha256": digest(output.read_bytes()), **planning(plan)}


def assign(plan_path, population_path, output):
    plan = validate(json.loads(plan_path.read_bytes()))
    now = datetime.now(UTC)
    if not timestamp(plan["registered_at"]) <= now < boundary(plan["start_date"]):
        raise ValueError("assignment must occur after registration and before the window")
    population = json.loads(population_path.read_bytes())
    if (
        not isinstance(population, list)
        or not population
        or any(not isinstance(x, str) or not x.strip() for x in population)
        or len(set(population)) != len(population)
    ):
        raise ValueError("population must be a nonempty list of unique customer IDs")
    rows = [
        {
            "experiment_id": plan["experiment_id"],
            "customer_id": key,
            "arm": "treatment" if secrets.randbelow(2) else "control",
            "assigned_at": now.isoformat(),
        }
        for key in sorted(population)
    ]
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"plan_sha256": digest(plan_path.read_bytes()), "tables": {}}
    for name, values in (
        ("experiment_population", [{"customer_id": key} for key in sorted(population)]),
        ("experiment_assignments", rows),
    ):
        payload = b"".join((json.dumps(row, sort_keys=True) + "\n").encode() for row in values)
        (output / f"{name}.jsonl").write_bytes(payload)
        receipt["tables"][name] = {"sha256": digest(payload), "rows": len(values)}
    (output / "receipt.json").write_bytes(encode(receipt))
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Register fixed-horizon experiments and assign cohorts"
    )
    parser.add_argument("command", choices=("register", "assign", "plan"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--population", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "plan":
        result = planning(json.loads(args.plan.read_bytes()))
    elif args.command == "register":
        if args.output is None:
            parser.error("register requires --output")
        result = register(json.loads(args.plan.read_bytes()), args.output)
    else:
        if args.output is None or args.population is None:
            parser.error("assign requires --population and --output")
        result = assign(args.plan, args.population, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
