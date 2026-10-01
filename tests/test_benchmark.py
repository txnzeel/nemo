"""Benchmark metadata is explicit; timing values are not performance promises."""

from datetime import date

import pytest
from test_experiments import make_manual

from nemo.benchmark import benchmark
from nemo.warehouse import build_warehouse


def test_manual_fixture_latency_report(tmp_path):
    make_manual(tmp_path)
    observations = tmp_path / "observations"
    warehouse = tmp_path / "warehouse.duckdb"
    build_warehouse(observations, warehouse)
    result = benchmark(
        warehouse,
        observations,
        baseline_start=date(2025, 1, 1),
        current_start=date(2025, 1, 5),
        repetitions=3,
    )
    assert result["dataset_rows"]["orders"] == 330
    assert result["repetitions"] == 3 and result["limits"]
    for measurement in result["measurements"].values():
        assert len(measurement["samples_ms"]) == 3
        assert 0 <= measurement["min_ms"] <= measurement["p50_ms"] <= measurement["max_ms"]
        assert measurement["p95_nearest_rank_ms"] == measurement["max_ms"]
        assert measurement["response_bytes"] > 0
    with pytest.raises(ValueError):
        benchmark(
            warehouse,
            observations,
            baseline_start=date(2025, 1, 1),
            current_start=date(2025, 1, 5),
            repetitions=0,
        )
