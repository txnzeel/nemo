"""Bounded local latency measurement; not a production capacity or causal benchmark."""

import argparse
import json
import math
import platform
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from nemo.analyst import explain
from nemo.decision_case import build_case


def benchmark(warehouse, observations, *, baseline_start, current_start, repetitions=5):
    if type(repetitions) is not int or not 3 <= repetitions <= 20:
        raise ValueError("use 3 to 20 repetitions")
    case = build_case(
        warehouse, observations, baseline_start=baseline_start, current_start=current_start
    )
    measurements = {}
    operations = {
        "decision_case": lambda: build_case(
            warehouse, observations, baseline_start=baseline_start, current_start=current_start
        ),
        "analyst_no_model": lambda: explain(case),
    }
    for name, operation in operations.items():
        durations = []
        size = None
        for _ in range(repetitions):
            start = time.perf_counter_ns()
            result = operation()
            durations.append((time.perf_counter_ns() - start) / 1_000_000)
            size = len(json.dumps(result, sort_keys=True, allow_nan=False).encode())
        ordered = sorted(durations)
        measurements[name] = {
            "samples_ms": durations,
            "p50_ms": statistics.median(durations),
            "p95_nearest_rank_ms": ordered[math.ceil(0.95 * repetitions) - 1],
            "min_ms": min(durations),
            "max_ms": max(durations),
            "response_bytes": size,
        }
    manifest = json.loads((observations / "manifest.json").read_bytes())
    return {
        "schema_version": "1",
        "case_revision": case["revision_id"],
        "repetitions": repetitions,
        "dataset_rows": {name: details["rows"] for name, details in manifest["tables"].items()},
        "python": platform.python_version(),
        "platform": platform.platform(),
        "measurements": measurements,
        "limits": [
            "One untimed case warms the process. Runs are sequential on this local machine.",
            "Latency excludes HTTP, browser rendering, ingestion and warehouse construction.",
            "Small sample p95 is a descriptive order statistic, not a tail-latency guarantee.",
            "No production scale, throughput, concurrency or SLA claim follows.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--baseline-start", type=date.fromisoformat, required=True)
    parser.add_argument("--current-start", type=date.fromisoformat, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = benchmark(
        args.warehouse,
        args.observations,
        baseline_start=args.baseline_start,
        current_start=args.current_start,
        repetitions=args.repetitions,
    )
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "measured", "repetitions": args.repetitions}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
