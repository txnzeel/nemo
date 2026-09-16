"""Descriptive multi-touch conversion windows over canonical warehouse observations."""

import argparse
import hashlib
import json
import sys
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import UTC, datetime, time, timedelta
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.observations import BUSINESS_ZONE
from nemo.warehouse import open_warehouse, project_hash


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def elapsed_us(delta):
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def report(warehouse: Path, *, lookback_days: int = 30):
    if type(lookback_days) is not int or not 1 <= lookback_days <= 3650:
        raise ValueError("lookback_days must be an integer from 1 through 3650")
    with open_warehouse(warehouse) as snapshot:
        sessions = defaultdict(list)
        for sid, customer, started, channel, campaign, device in snapshot.connection.execute(
            "SELECT session_id, customer_id, started_at, channel, campaign_id, device "
            "FROM analytics.fct_sessions ORDER BY started_at, session_id"
        ).fetchall():
            sessions[customer].append(
                (
                    instant(started),
                    {
                        "session_id": sid,
                        "started_at": started,
                        "channel": channel,
                        "campaign_id": campaign,
                        "device": device,
                    },
                )
            )
        stamps = {key: [item[0] for item in values] for key, values in sessions.items()}
        coverage_start = datetime.combine(snapshot.start, time(), BUSINESS_ZONE).astimezone(UTC)
        journeys = []
        paths, combinations, assists = Counter(), Counter(), Counter()
        for oid, customer, sid, paid in snapshot.connection.execute(
            "SELECT order_id, customer_id, session_id, paid_at "
            "FROM analytics.fct_orders ORDER BY paid_at, order_id"
        ).fetchall():
            end = instant(paid)
            start = end - timedelta(days=lookback_days)
            times = stamps[customer]
            selected = sessions[customer][bisect_left(times, start) : bisect_right(times, end)]
            touches = [item[1] for item in selected]
            path = tuple(t["channel"] for t in touches)
            combination = tuple(sorted(set(path)))
            prior_channels = sorted(set(path[:-1]))
            paths[path] += 1
            combinations[combination] += 1
            assists.update(prior_channels)
            journeys.append(
                {
                    "order_id": oid,
                    "customer_id": customer,
                    "paid_at": paid,
                    "purchase_session_id": sid,
                    "window_start_inclusive": start.isoformat(),
                    "touches": touches,
                    "channel_path": list(path),
                    "touch_count": len(touches),
                    "journey_length_sessions": len(touches),
                    "time_to_purchase_microseconds": (
                        elapsed_us(end - selected[0][0]) if selected else None
                    ),
                    "prior_channels": prior_channels,
                    "channel_combination": list(combination),
                    "history_boundary_limited": start < coverage_start,
                    "purchase_session_in_window": any(t["session_id"] == sid for t in touches),
                    "timestamp_ties": len({item[0] for item in selected}) != len(selected),
                }
            )
        return {
            "schema_version": "1",
            "claim_type": "descriptive_metric",
            "dataset_id": snapshot.contract.dataset_id,
            "source_mode": snapshot.contract.mode,
            "window": {
                "start_inclusive": snapshot.start.isoformat(),
                "end_exclusive": snapshot.end.isoformat(),
            },
            "contract": {
                "version": "1",
                "lookback_days": lookback_days,
                "identity": "canonical_customer_id_only",
                "touch": "observed_session_start",
                "conversion": "paid_order",
                "bounds": "payment_time_minus_lookback_inclusive_through_payment_inclusive",
                "repeat_orders": "independent_overlapping_conversion_windows",
                "tie_break": "timestamp_then_session_id_not_inferred_temporal_order",
                "population": "all_paid_orders_in_snapshot_including_zero_touch_windows",
            },
            "metric_contracts": [
                {
                    "name": name,
                    "version": "1",
                    "claim_type": "descriptive_metric",
                    "formula": formula,
                    "unit": unit,
                }
                for name, formula, unit in (
                    ("touch_count", "count of selected session starts per order", "sessions"),
                    ("journey_length_sessions", "same as touch_count", "sessions"),
                    (
                        "time_to_purchase_microseconds",
                        "payment minus earliest selected start; null if empty",
                        "microseconds",
                    ),
                    ("path_frequency", "orders with identical ordered channel paths", "orders"),
                    (
                        "channel_combinations",
                        "orders with identical distinct channel sets",
                        "orders",
                    ),
                    (
                        "prior_channel_appearances",
                        "orders with channel before final selected touch; once per order",
                        "orders",
                    ),
                )
            ],
            "total": {
                "paid_orders": len(journeys),
                "zero_touch_orders": sum(j["touch_count"] == 0 for j in journeys),
                "history_boundary_limited_orders": sum(
                    j["history_boundary_limited"] for j in journeys
                ),
                "timestamp_tie_orders": sum(j["timestamp_ties"] for j in journeys),
            },
            "journeys": journeys,
            "path_frequency": [
                {"channels": list(key), "orders": count} for key, count in sorted(paths.items())
            ],
            "channel_combinations": [
                {"channels": list(key), "orders": count}
                for key, count in sorted(combinations.items())
            ],
            "prior_channel_appearances": [
                {"channel": key, "orders": count} for key, count in sorted(assists.items())
            ],
            "provenance": {
                "manifest_sha256": snapshot.manifest_sha256,
                "tables": snapshot.table_hashes,
                "dbt_project_sha256": project_hash(),
                "code_sha256": hashlib.sha256(
                    files("nemo").joinpath("journeys.py").read_bytes()
                ).hexdigest(),
            },
            "limitations": [
                "Identity is supplied, not resolved; cross-device and offline gaps remain.",
                "Observed paths are not guaranteed complete, even within snapshot coverage.",
                "Buyer-only windows cannot estimate nonbuyer behavior or conversion propensity.",
                "Prior channels are descriptive appearances, not attributed or causal credit.",
                "Windows can reuse touches across orders; touch counts are not unique traffic.",
                "Equal-time ordering is deterministic only; relative chronology is unknown.",
                "Session starts are not ad impressions, clicks or event-level interactions.",
                "Corrections restate snapshots; no arrival-as-of reconstruction.",
            ],
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEMO observed multi-touch journeys")
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        encoded = (
            json.dumps(
                report(args.warehouse, lookback_days=args.lookback_days),
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
        else:
            sys.stdout.write(encoded)
        return 0
    except (ValueError, OSError, RuntimeError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
