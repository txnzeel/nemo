"""Canonical refund and variable-cost normalization; no generator dependency."""

import hashlib
import json
from datetime import datetime

from nemo.observations import _integer, _text, _timestamp

COST_COMPONENTS = (
    "net_cogs_paise",
    "fulfillment_paise",
    "payment_fees_paise",
    "refund_handling_paise",
    "other_variable_costs_paise",
)


def read_table(source, manifest, name):
    entry = manifest["tables"].get(name)
    if entry is None:
        return None
    payload = (source / f"{name}.jsonl").read_bytes()
    if (
        not isinstance(entry, dict)
        or type(entry.get("rows")) is not int
        or entry["rows"] != len(payload.splitlines())
        or hashlib.sha256(payload).hexdigest() != entry.get("sha256")
    ):
        raise ValueError(f"invalid {name} checksum or row count")
    rows = [json.loads(line) for line in payload.splitlines()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{name} must contain JSON objects")
    return rows


def load_inputs(snapshot, source):
    payload = (source / "manifest.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != snapshot.manifest_sha256:
        raise ValueError("economics observations do not match warehouse snapshot")
    manifest = json.loads(payload)
    contract = manifest.get("economics_contract")
    if contract is not None and (not isinstance(contract, dict) or contract.get("version") != "1"):
        raise ValueError("unsupported economics contract")
    contract = contract or {}
    cursor = snapshot.connection.execute(
        "select order_id, amount_paise, paid_at from analytics.fct_orders"
    )
    orders = {
        row[0]: {"amount": row[1], "paid_at": datetime.fromisoformat(row[2])}
        for row in cursor.fetchall()
    }
    result = {
        "refunds": [],
        "costs": [],
        "refunds_complete": False,
        "costs_declared": False,
        "cost_provenance": None,
        "source_hashes": {},
        "contract": contract,
    }
    refund_contract = contract.get("refunds")
    if refund_contract is not None:
        if refund_contract != {
            "coverage_end_exclusive": snapshot.end.isoformat(),
            "basis": "tax_exclusive_merchandise",
        }:
            raise ValueError("refund coverage/basis must match the full snapshot")
        item_rows = read_table(source, manifest, "order_items")
        refund_rows = read_table(source, manifest, "refunds")
        if item_rows is None or refund_rows is None:
            raise ValueError("declared refund coverage requires order_items and refunds")
        items, sums = {}, {}
        for row in item_rows:
            item_id, order_id = _text(row, "order_item_id"), _text(row, "order_id")
            quantity, price, amount = (
                _integer(row, key) for key in ("quantity", "unit_price_paise", "amount_paise")
            )
            if item_id in items or order_id not in orders or quantity == 0 or price == 0:
                raise ValueError("invalid item identity, order or quantity")
            if quantity * price != amount:
                raise ValueError("item money does not reconcile")
            items[item_id] = {**row, "used_quantity": 0}
            sums[order_id] = sums.get(order_id, 0) + amount
        if set(sums) != set(orders) or any(
            sums[key] != order["amount"] for key, order in orders.items()
        ):
            raise ValueError("order items must completely reconcile to paid orders")
        refund_ids = set()
        for row in refund_rows:
            refund_id, item_id = _text(row, "refund_id"), _text(row, "order_item_id")
            quantity, amount = _integer(row, "quantity"), _integer(row, "amount_paise")
            stamp, _ = _timestamp(row, "refunded_at", snapshot.start, snapshot.end)
            if refund_id in refund_ids or item_id not in items or quantity == 0:
                raise ValueError("invalid refund identity or quantity")
            item = items[item_id]
            if amount != quantity * item["unit_price_paise"]:
                raise ValueError("refund amount must match refunded units")
            item["used_quantity"] += quantity
            if item["used_quantity"] > item["quantity"]:
                raise ValueError("refund quantity exceeds purchased quantity")
            order_id = item["order_id"]
            if datetime.fromisoformat(stamp) < orders[order_id]["paid_at"]:
                raise ValueError("refund cannot precede payment")
            refund_ids.add(refund_id)
            result["refunds"].append({"order_id": order_id, "amount_paise": amount})
        result["refunds_complete"] = True
        for table in ("order_items", "refunds"):
            result["source_hashes"][table] = manifest["tables"][table]["sha256"]
    cost_contract = contract.get("variable_costs")
    if cost_contract is not None:
        if (
            not isinstance(cost_contract, dict)
            or cost_contract.get("coverage_end_exclusive") != snapshot.end.isoformat()
            or cost_contract.get("basis") != "order_costs_net_of_recoveries"
            or cost_contract.get("components") != list(COST_COMPONENTS)
            or cost_contract.get("provenance") not in ("observed", "synthetic_assumption")
        ):
            raise ValueError("unsupported variable-cost scope, cutoff or provenance")
        rows = read_table(source, manifest, "order_variable_costs")
        if rows is None:
            raise ValueError("declared cost feed is missing")
        seen = set()
        for row in rows:
            order_id = _text(row, "order_id")
            if order_id not in orders or order_id in seen:
                raise ValueError("unknown or duplicate cost order")
            seen.add(order_id)
            components = []
            for key in COST_COMPONENTS:
                if key not in row:
                    raise ValueError("cost components must be explicit, including nulls")
                components.append(None if row[key] is None else _integer(row, key))
            total = None if None in components else sum(components)
            result["costs"].append({"order_id": order_id, "variable_cost_paise": total})
        result["costs_declared"] = True
        result["cost_provenance"] = cost_contract["provenance"]
        result["source_hashes"]["order_variable_costs"] = manifest["tables"][
            "order_variable_costs"
        ]["sha256"]
    return result
