"""Observed retention states and adequately followed product sequence review."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.economics_inputs import read_table
from nemo.experiment_design import digest, encode
from nemo.observations import BUSINESS_ZONE, _integer, _text
from nemo.search_intelligence import ratio
from nemo.warehouse import open_warehouse

POLICY = {
    "version": "1",
    "at_risk_days": 90,
    "dormant_days": 180,
    "recent_days": 30,
    "loyal_orders": 3,
    "loyal_span_days": 60,
    "sequence_followup_days": 30,
}


def state(orders, cutoff):
    """Orders contain public paid_at, business_date, amount_paise; cutoff is exclusive."""
    visible = sorted(
        (o for o in orders if o["day"] < cutoff), key=lambda o: (o["paid_at"], o["order_id"])
    )
    if not visible:
        return {
            "state": "NO_OBSERVED_PURCHASE",
            "paid_orders": 0,
            "merchandise_receipts_paise": 0,
            "recency_days": None,
        }
    last = visible[-1]["day"]
    recency = (cutoff - last).days
    span = (last - visible[0]["day"]).days
    if recency >= POLICY["dormant_days"]:
        label = "DORMANT"
    elif recency >= POLICY["at_risk_days"]:
        label = "AT_RISK"
    elif (
        len(visible) >= 2
        and recency <= POLICY["recent_days"]
        and (last - visible[-2]["day"]).days >= POLICY["dormant_days"]
    ):
        label = "REACTIVATED"
    elif len(visible) == 1 and recency <= POLICY["recent_days"]:
        label = "NEW"
    elif len(visible) >= POLICY["loyal_orders"] and span >= POLICY["loyal_span_days"]:
        label = "LOYAL"
    elif len(visible) >= 2:
        label = "REPEAT"
    else:
        label = "ACTIVE"
    return {
        "state": label,
        "paid_orders": len(visible),
        "merchandise_receipts_paise": sum(o["amount_paise"] for o in visible),
        "recency_days": recency,
    }


def sequences(orders, items, cutoff, min_customers):
    if items is None:
        return {"status": "not_assessed", "reason": "missing_order_items", "pairs": []}
    by_id = {o["order_id"]: o for o in orders}
    totals, seen = Counter(), set()
    purchases = defaultdict(dict)
    for item in items:
        key, order_id = _text(item, "order_item_id"), _text(item, "order_id")
        product = _text(item, "product_id")
        qty, price, amount = (
            _integer(item, k) for k in ("quantity", "unit_price_paise", "amount_paise")
        )
        if key in seen or order_id not in by_id or not qty or not price or qty * price != amount:
            raise ValueError("invalid order item identity/amount")
        seen.add(key)
        totals[order_id] += amount
        order = by_id[order_id]
        if order["day"] < cutoff:
            first = purchases[order["customer_id"]].get(product)
            if first is None or order["paid_at"] < first:
                purchases[order["customer_id"]][product] = order["paid_at"]
    if set(totals) != set(by_id) or any(totals[k] != o["amount_paise"] for k, o in by_id.items()):
        raise ValueError("order items must completely reconcile")
    products = sorted({p for history in purchases.values() for p in history})
    if len(products) > 500:
        raise ValueError("sequence product cardinality exceeds bounded local analysis limit")
    pairs = []
    boundary = datetime.combine(cutoff, datetime.min.time(), BUSINESS_ZONE)
    followup = timedelta(days=POLICY["sequence_followup_days"])
    for a in products:
        for b in products:
            if a == b:
                continue
            eligible = success = 0
            for history in purchases.values():
                first_a, first_b = history.get(a), history.get(b)
                if first_a is None or first_a + followup > boundary:
                    continue
                if first_b is not None and first_b <= first_a:
                    continue
                eligible += 1
                success += first_b is not None and first_b < first_a + followup
            if eligible:
                pairs.append(
                    {
                        "from_product": a,
                        "to_product": b,
                        "eligible_customers": eligible,
                        "sequential_customers": success,
                        "sequence_rate": ratio(success, eligible),
                        "review_eligible": success >= min_customers and eligible >= min_customers,
                        "claim_type": "descriptive_association",
                        "incremental_value_paise": None,
                    }
                )
    pairs.sort(key=lambda p: (-p["sequential_customers"], p["from_product"], p["to_product"]))
    return {"status": "measured", "pairs": pairs}


def report(warehouse, observations, *, baseline, as_of, min_customers=20):
    if type(baseline) is not date or type(as_of) is not date:
        raise ValueError("cutoffs must be dates")
    if type(min_customers) is not int or min_customers < 2:
        raise ValueError("min_customers must be an integer >=2")
    source = Path(observations)
    with open_warehouse(Path(warehouse)) as snapshot:
        if not snapshot.start <= baseline < as_of <= snapshot.end:
            raise ValueError("cutoffs outside warehouse or not increasing")
        if as_of > datetime.now(BUSINESS_ZONE).date():
            raise ValueError("future cutoff")
        payload = (source / "manifest.json").read_bytes()
        if digest(payload) != snapshot.manifest_sha256:
            raise ValueError("observations do not match warehouse")
        manifest = json.loads(payload)
        cursor = snapshot.connection.execute(
            "select order_id, customer_id, paid_at, business_date, amount_paise "
            "from analytics.fct_orders"
        )
        orders = [
            {
                "order_id": row[0],
                "customer_id": row[1],
                "paid_at": datetime.fromisoformat(row[2]),
                "day": date.fromisoformat(str(row[3])),
                "amount_paise": row[4],
            }
            for row in cursor.fetchall()
        ]
        by_customer = defaultdict(list)
        for order in orders:
            by_customer[order["customer_id"]].append(order)
        customers, transitions, cases = [], Counter(), []
        for key, first in snapshot.connection.execute(
            "select customer_id, first_seen_at from analytics.dim_customer order by customer_id"
        ).fetchall():
            first_day = datetime.fromisoformat(first).astimezone(BUSINESS_ZONE).date()
            if first_day >= as_of:
                continue
            previous = (
                state(by_customer[key], baseline)
                if first_day < baseline
                else {
                    "state": "NOT_YET_OBSERVED",
                    "paid_orders": 0,
                    "merchandise_receipts_paise": 0,
                    "recency_days": None,
                }
            )
            current = state(by_customer[key], as_of)
            transitions[(previous["state"], current["state"])] += 1
            customers.append(
                {
                    "customer_id": key,
                    "baseline": previous,
                    "current": current,
                    "forward_value_at_risk_paise": None,
                }
            )
        counts = Counter(c["current"]["state"] for c in customers)
        for label, action in (
            ("AT_RISK", "review_retention_and_measurement"),
            ("DORMANT", "design_consented_reactivation_experiment"),
        ):
            members = [c for c in customers if c["current"]["state"] == label]
            if members:
                cases.append(
                    {
                        "kind": "retention" if label == "AT_RISK" else "reactivation",
                        "state": label,
                        "customer_count": len(members),
                        "observed_merchandise_receipts_paise": sum(
                            c["current"]["merchandise_receipts_paise"] for c in members
                        ),
                        "claim_type": "diagnostic_hypothesis",
                        "action": action,
                        "execution": "manual_review_only",
                        "incremental_value_paise": None,
                    }
                )
        expansion = sequences(
            orders, read_table(source, manifest, "order_items"), as_of, min_customers
        )
        for pair in expansion["pairs"]:
            if pair["review_eligible"]:
                cases.append(
                    {
                        "kind": "cross_sell",
                        "evidence": pair,
                        "claim_type": "diagnostic_hypothesis",
                        "action": "review_stock_consent_and_design_controlled_offer_test",
                        "execution": "manual_review_only",
                        "incremental_value_paise": None,
                    }
                )
        for case in cases:
            identity = {
                "dataset_id": snapshot.contract.dataset_id,
                "mode": snapshot.contract.mode,
                "kind": case["kind"],
                "state": case.get("state"),
                "pair": {
                    k: case.get("evidence", {}).get(k) for k in ("from_product", "to_product")
                },
            }
            case["case_id"] = "RC-" + digest(encode(identity))[:20]
            case["prerequisites"] = [
                "Verify coverage, identity, refunds and measurement.",
                "Review consent, stock, costs and operational feasibility.",
                "Use controlled evidence before claiming incremental value.",
            ]
            case["source_manifest_sha256"] = snapshot.manifest_sha256
            case["revision_id"] = digest(
                encode({**case, "baseline": baseline.isoformat(), "as_of": as_of.isoformat()})
            )
        result = {
            "schema_version": "1",
            "claim_type": "descriptive_customer_history",
            "scope": {
                "dataset_id": snapshot.contract.dataset_id,
                "mode": snapshot.contract.mode,
                "baseline": baseline.isoformat(),
                "as_of_exclusive": as_of.isoformat(),
            },
            "policy": dict(POLICY),
            "min_customers": min_customers,
            "customers": customers,
            "state_counts": dict(sorted(counts.items())),
            "transitions": [
                {"from": a, "to": b, "customers": n} for (a, b), n in sorted(transitions.items())
            ],
            "expansion": expansion,
            "cases": cases,
            "economic_ranking": "not_assessed",
            "provenance": {
                "manifest_sha256": snapshot.manifest_sha256,
                "code_sha256": digest(files("nemo").joinpath("retention.py").read_bytes()),
            },
            "limitations": [
                "States describe observed history; left truncation may hide earlier purchases.",
                "CHURNED requires an explicit termination contract and is not inferred.",
                "Historical merchandise receipts are not profit or forward value at risk.",
                "Sequences are associations, not calibrated propensity or causal effects.",
                "Refunded purchases are not removed; purchases do not imply ownership.",
                "Minimum support is a review screen, not statistical significance.",
                "No outreach; consent, costs and experimental validation remain required.",
            ],
        }
        result["revision_id"] = digest(encode(result))
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--baseline", type=date.fromisoformat, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--min-customers", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = report(
            args.warehouse,
            args.observations,
            baseline=args.baseline,
            as_of=args.as_of,
            min_customers=args.min_customers,
        )
        with args.output.open("xb") as stream:
            stream.write(encode(result))
        print(json.dumps({"output": str(args.output), "cases": len(result["cases"])}))
        return 0
    except (ValueError, KeyError, TypeError, OSError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
