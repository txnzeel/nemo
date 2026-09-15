"""Observation-only acquisition reports. No generator imports or private inputs."""

import argparse
import hashlib
import json
import platform
import sys
from datetime import date
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.integrity import assess
from nemo.metrics import DIMENSIONS, FACTS, REGISTRY
from nemo.warehouse import open_warehouse, project_hash, temporary_warehouse


def registry() -> list[dict]:
    return [metric.definition() for metric in REGISTRY]


def measure(
    observations: Path | None = None,
    *,
    warehouse: Path | None = None,
    integrity_observations: Path | None = None,
    start: date | None = None,
    end: date | None = None,
    group_by: tuple[str, ...] = ("channel",),
    channel: str | None = None,
    device: str | None = None,
    campaign_id: str | None = None,
) -> dict:
    if len(set(group_by)) != len(group_by) or any(item not in DIMENSIONS for item in group_by):
        raise ValueError("group_by must contain unique supported dimensions")
    if campaign_id is not None and (not isinstance(campaign_id, str) or not campaign_id):
        raise ValueError("campaign_id must be a nonempty string")
    if observations is not None and integrity_observations is not None:
        raise ValueError("integrity_observations is only used with a warehouse")
    sql = files("nemo").joinpath("acquisition.sql").read_text(encoding="utf-8")
    if (observations is None) == (warehouse is None):
        raise ValueError("supply exactly one observations directory or built warehouse")
    context = (
        open_warehouse(warehouse) if warehouse is not None else temporary_warehouse(observations)
    )
    with context as snapshot:
        integrity_source = observations if observations is not None else integrity_observations
        integrity = assess(integrity_source) if integrity_source is not None else None
        if integrity is not None and integrity["manifest_sha256"] != snapshot.manifest_sha256:
            raise ValueError("integrity observations do not match the built warehouse snapshot")
        if channel is not None and channel not in snapshot.contract.channels:
            raise ValueError("unsupported channel filter")
        if device is not None and device not in snapshot.contract.devices:
            raise ValueError("unsupported device filter")
        start = snapshot.start if start is None else start
        end = snapshot.end if end is None else end
        if type(start) is not date or type(end) is not date:
            raise ValueError("report dates must be dates")
        if not snapshot.start <= start < end <= snapshot.end:
            raise ValueError("report window must be nonempty and inside observation window")
        parameters = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "channel": channel,
            "device": device,
            "campaign_id": campaign_id,
        }
        predicates = [
            f"{key} = ${key}"
            for key in ("channel", "device", "campaign_id")
            if parameters[key] is not None
        ]
        where = " WHERE " + " AND ".join(predicates) if predicates else ""
        aggregates = ", ".join(f"COALESCE(SUM({fact}), 0) AS {fact}" for fact in FACTS)

        def query(dimensions: tuple[str, ...]) -> list[dict]:
            columns = ", ".join(dimensions)
            prefix = columns + ", " if columns else ""
            suffix = f" GROUP BY {columns} ORDER BY {columns}" if columns else ""
            statement = f"SELECT {prefix}{aggregates} FROM ({sql}) AS facts{where}{suffix}"
            results = []
            bindings = {key: value for key, value in parameters.items() if value is not None}
            cursor = snapshot.connection.execute(statement, bindings)
            names = [column[0] for column in cursor.description]
            for values in cursor.fetchall():
                row = dict(zip(names, values, strict=True))
                totals = {fact: row[fact] for fact in FACTS}
                results.append(
                    {
                        "dimensions": {
                            name: row[name].isoformat()
                            if isinstance(row[name], date)
                            else row[name]
                            for name in dimensions
                        },
                        "facts": totals,
                        "metrics": {metric.name: metric.evaluate(totals) for metric in REGISTRY},
                    }
                )
            return results

        code_hashes = {
            name: hashlib.sha256(files("nemo").joinpath(name).read_bytes()).hexdigest()
            for name in (
                "canonical.py",
                "integrity.py",
                "metrics.py",
                "observations.py",
                "measurement.py",
                "warehouse.py",
                "acquisition.sql",
            )
        }
        return {
            "report_version": "1",
            "mode": snapshot.contract.mode,
            "dataset_id": snapshot.contract.dataset_id,
            "measurement_health": (
                integrity["measurement_confidence"] if integrity is not None else "not_assessed"
            ),
            "measurement_integrity": integrity,
            "window": {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()},
            "business_timezone": "Asia/Kolkata",
            "group_by": group_by,
            "filters": {"channel": channel, "device": device, "campaign_id": campaign_id},
            "history_start": snapshot.start.isoformat(),
            "limitations": [
                "First observed buyers may have purchased before the supplied history.",
                "Purchase-session credit is not causal attribution or incrementality.",
                "Revenue excludes refunds and costs; ROAS is not profit.",
                "Session cohorts have unequal follow-up through the report end.",
                "Structural validation does not establish measurement health.",
            ],
            "provenance": {
                "manifest_sha256": snapshot.manifest_sha256,
                "tables": snapshot.table_hashes,
                "code_sha256": code_hashes,
                "python": platform.python_version(),
                "duckdb": duckdb.__version__,
                "dbt_project_sha256": project_hash(),
            },
            "registry": registry(),
            "total": query(())[0],
            "groups": query(group_by) if group_by else [],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEMO observed acquisition measurement")
    parser.add_argument("--observations", type=Path, help="Public observations directory only")
    parser.add_argument("--warehouse", type=Path, help="Built DuckDB warehouse")
    parser.add_argument(
        "--integrity-observations",
        type=Path,
        help="Matching canonical snapshot for warehouse integrity checks",
    )
    parser.add_argument("--registry", action="store_true", help="Export metric definitions only")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat, help="Exclusive business date")
    parser.add_argument(
        "--group-by", default="channel", help="Comma-separated supported dimensions"
    )
    parser.add_argument("--channel")
    parser.add_argument("--device")
    parser.add_argument("--campaign-id")
    parser.add_argument("--output", type=Path, help="New JSON file; defaults to stdout")
    args = parser.parse_args(argv)
    if not args.registry and args.observations is None and args.warehouse is None:
        parser.error("--observations or --warehouse is required unless --registry is used")
    try:
        if args.output is not None and args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}")
        result = (
            registry()
            if args.registry
            else measure(
                args.observations,
                warehouse=args.warehouse,
                integrity_observations=args.integrity_observations,
                start=args.start,
                end=args.end,
                group_by=tuple(part.strip() for part in args.group_by.split(",") if part.strip()),
                channel=args.channel,
                device=args.device,
                campaign_id=args.campaign_id,
            )
        )
        encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output is None:
            sys.stdout.write(encoded)
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
            print(json.dumps({"status": "complete", "output": str(args.output.absolute())}))
        return 0
    except (ValueError, OSError, RuntimeError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
