"""Lab-only deterministic observation perturbation; never imported by analytics."""

import argparse
import hashlib
import json
from datetime import UTC, date, datetime, time
from pathlib import Path

from nemo.observations import BUSINESS_ZONE, REQUIRED_TABLES, open_snapshot


def inject_tracking_loss(source: Path, output: Path, *, device: str, start: date, end: date):
    """Create healthy/failure canonical observations and keep injection truth separate."""
    with open_snapshot(source) as snapshot:
        if (
            device not in snapshot.contract.devices
            or not snapshot.start <= start < end <= snapshot.end
        ):
            raise ValueError("invalid incident device or window")
        manifest = json.loads((source / "manifest.json").read_bytes())
        payload = (source / "events.jsonl").read_bytes()
        entry = manifest["tables"].get("events", {})
        if hashlib.sha256(payload).hexdigest() != entry.get("sha256"):
            raise ValueError("event checksum mismatch")
        rows = [json.loads(line) for line in payload.splitlines()]
        if len(rows) != entry.get("rows"):
            raise ValueError("event row count mismatch")
        devices = dict(snapshot.connection.execute("select session_id, device from sessions"))
        retained, removed = [], []
        for row in rows:
            day = datetime.fromisoformat(row["occurred_at"]).astimezone(BUSINESS_ZONE).date()
            if (
                row["name"] == "purchase"
                and devices.get(row["session_id"]) == device
                and start <= day < end
            ):
                removed.append(row["event_id"])
            else:
                retained.append(row)
        if not removed:
            raise ValueError("incident selection contains no purchase events")
        complete = datetime.combine(snapshot.end, time(), BUSINESS_ZONE).astimezone(UTC)
        manifest["measurement_contract"] = {
            "version": "1",
            "purchase_semantics": "one_purchase_event_per_paid_order",
            "max_delay_seconds": 300,
            "complete_through": complete.isoformat(),
        }
        output.mkdir(parents=True, exist_ok=False)
        for name, events in (("healthy", rows), ("failure", retained)):
            destination = output / name / "observations"
            destination.mkdir(parents=True)
            tables = {key: manifest["tables"][key] for key in REQUIRED_TABLES}
            for table in REQUIRED_TABLES:
                (destination / f"{table}.jsonl").write_bytes(
                    (source / f"{table}.jsonl").read_bytes()
                )
            data = "".join(json.dumps(row, sort_keys=True) + "\n" for row in events).encode()
            (destination / "events.jsonl").write_bytes(data)
            tables["events"] = {"rows": len(events), "sha256": hashlib.sha256(data).hexdigest()}
            public = dict(manifest, tables=tables)
            (destination / "manifest.json").write_text(
                json.dumps(public, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
        private = output / "private"
        private.mkdir()
        truth = {
            "condition": "dropped_purchase_events",
            "device": device,
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "removed_count": len(removed),
            "removed_event_ids": removed,
            "source_manifest_sha256": snapshot.manifest_sha256,
        }
        (private / "tracking-truth.json").write_text(
            json.dumps(truth, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        return {"output": str(output.absolute()), "removed_count": len(removed)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lab-only purchase tracking failure injection")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    result = inject_tracking_loss(
        args.observations, args.output, device=args.device, start=args.start, end=args.end
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
