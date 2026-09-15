"""Lab-only payment deterioration and tracking controls, separated from diagnosis."""

import argparse
import hashlib
import json
from datetime import date, datetime

from nemo.lab_tracking import inject_tracking_loss
from nemo.observations import BUSINESS_ZONE


def plant_payment_problem(source, output, *, device: str, start: date, end: date):
    # Reuse the canonical tracking control producer. Never called by the detector.
    inject_tracking_loss(source, output, device=device, start=start, end=end)
    contract = {
        "version": "1",
        "semantics": "one_payment_attempt_and_terminal_event_per_attempting_session",
    }
    for name in ("healthy", "failure"):
        path = output / name / "observations" / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["funnel_contract"] = contract
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    healthy = output / "healthy" / "observations"
    sessions = {
        row["session_id"]: row
        for row in map(json.loads, (healthy / "sessions.jsonl").read_text().splitlines())
    }
    orders = list(map(json.loads, (healthy / "orders.jsonl").read_text().splitlines()))
    removed = {
        row["order_id"]
        for row in orders
        if sessions[row["session_id"]]["device"] == device
        and start <= datetime.fromisoformat(row["paid_at"]).astimezone(BUSINESS_ZONE).date() < end
        and int(hashlib.sha256(row["order_id"].encode()).hexdigest()[:8], 16) % 4 != 0
    }
    if not removed:
        raise ValueError("no paid orders selected for deterioration")
    # This reference world has one attempt per session. Replace the successful terminal
    # event with a failure and remove its paid order and purchase observation together.
    events = []
    for row in map(json.loads, (healthy / "events.jsonl").read_text().splitlines()):
        if row.get("order_id") in removed:
            if row["name"] == "purchase":
                continue
            if row["name"] == "payment_succeeded":
                row = dict(row, name="payment_failed", order_id=None)
            else:
                raise ValueError("unsupported order-linked event in lab reference")
        events.append(row)
    destination = output / "business" / "observations"
    destination.mkdir(parents=True)
    manifest = json.loads((healthy / "manifest.json").read_text())
    for table, entry in manifest["tables"].items():
        if table in ("orders", "events"):
            rows = (
                events if table == "events" else [r for r in orders if r["order_id"] not in removed]
            )
            payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
            entry.update(rows=len(rows), sha256=hashlib.sha256(payload).hexdigest())
        else:
            payload = (healthy / f"{table}.jsonl").read_bytes()
        (destination / f"{table}.jsonl").write_bytes(payload)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    truth = {
        "condition": "payment_success_replaced_with_failure",
        "device": device,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "removed_orders": sorted(removed),
        "removed_count": len(removed),
        "selection": "sha256(order_id) first 8 hex digits modulo 4 != 0",
        "limitation": "Snapshot perturbation; later customer behavior is not resimulated.",
    }
    (output / "private" / "payment-truth.json").write_text(
        json.dumps(truth, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return {"output": str(output.absolute()), "removed_orders": len(removed)}


def main(argv=None):
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Lab-only payment deterioration controls")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            plant_payment_problem(
                args.observations, args.output, device=args.device, start=args.start, end=args.end
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
