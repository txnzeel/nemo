"""Lab-only, explicitly assumed cost observations. Never imported by customer analytics."""

import argparse
import hashlib
import json
from pathlib import Path

from nemo.economics_inputs import COST_COMPONENTS, read_table
from nemo.observations import open_snapshot


def prepare_economics(source: Path, output: Path):
    with open_snapshot(source) as snapshot:
        manifest = json.loads((source / "manifest.json").read_bytes())
        items = read_table(source, manifest, "order_items")
        refunds = read_table(source, manifest, "refunds")
        if items is None or refunds is None:
            raise ValueError("lab source requires order items and refunds")
        item_orders = {r["order_item_id"]: r["order_id"] for r in items}
        refunded = {}
        for refund in refunds:
            order_id = item_orders[refund["order_item_id"]]
            refunded[order_id] = refunded.get(order_id, 0) + refund["amount_paise"]
        rows = snapshot.connection.execute("select order_id, amount_paise from orders").fetchall()
        costs = []
        for order in rows:
            amount = order["amount_paise"]
            refund = refunded.get(order["order_id"], 0)
            costs.append(
                {
                    "order_id": order["order_id"],
                    "net_cogs_paise": (amount - refund) // 2,
                    "fulfillment_paise": 10000,
                    "payment_fees_paise": amount * 2 // 100,
                    "refund_handling_paise": 2000 if refund else 0,
                    "other_variable_costs_paise": 0,
                }
            )
        output.mkdir(parents=True, exist_ok=False)
        for name in ("refunds_only", "assumed_costs"):
            destination = output / name / "observations"
            destination.mkdir(parents=True)
            public = json.loads(json.dumps(manifest))
            public["economics_contract"] = {
                "version": "1",
                "refunds": {
                    "coverage_end_exclusive": snapshot.end.isoformat(),
                    "basis": "tax_exclusive_merchandise",
                },
            }
            for table in manifest["tables"]:
                if not table.isidentifier():
                    raise ValueError("invalid canonical table name")
                read_table(source, manifest, table)
                (destination / f"{table}.jsonl").write_bytes(
                    (source / f"{table}.jsonl").read_bytes()
                )
            if name == "assumed_costs":
                public["economics_contract"]["variable_costs"] = {
                    "coverage_end_exclusive": snapshot.end.isoformat(),
                    "basis": "order_costs_net_of_recoveries",
                    "components": list(COST_COMPONENTS),
                    "provenance": "synthetic_assumption",
                }
                payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in costs).encode()
                (destination / "order_variable_costs.jsonl").write_bytes(payload)
                public["tables"]["order_variable_costs"] = {
                    "rows": len(costs),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            (destination / "manifest.json").write_text(
                json.dumps(public, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
        private = output / "private"
        private.mkdir()
        (private / "cost-assumptions.json").write_text(
            json.dumps(
                {
                    "warning": "Illustrative assumptions, not estimated or observed company costs.",
                    "net_cogs": "50% of merchandise remaining after refunds, floor paise",
                    "fulfillment": "10000 paise/order",
                    "payment_fees": "2% of gross, floor paise",
                    "refund_handling": "2000 paise per refunded order",
                    "other_variable": "explicit zero",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {"output": str(output.absolute()), "orders": len(costs)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare refund-only and assumed-cost lab sources")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(prepare_economics(args.observations, args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
