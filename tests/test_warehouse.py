"""Warehouse contracts: actual dbt builds, correction replay, and fail-closed serving."""

import hashlib
import json

import duckdb
import pytest
from test_source_boundary import canonical_source as canonical_source

from nemo.measurement import measure
from nemo.warehouse import build_warehouse, load_observations, open_warehouse, run_dbt


def rewrite(source, table, rows):
    payload = "".join(json.dumps(row) + "\n" for row in rows).encode()
    (source / f"{table}.jsonl").write_bytes(payload)
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["tables"][table] = {"rows": len(rows), "sha256": hashlib.sha256(payload).hexdigest()}
    path.write_text(json.dumps(manifest))


@pytest.fixture
def built(canonical_source, tmp_path):
    database = tmp_path / "warehouse.duckdb"
    result = build_warehouse(canonical_source, database)
    return canonical_source, database, result


def test_idempotent_replay_and_old_date_correction(built):
    source, database, _ = built
    with duckdb.connect(str(database), read_only=True) as connection:
        original_order_load = connection.execute("select _loaded_at from raw.orders").fetchone()
    replay = build_warehouse(source, database)
    assert replay["status"] == "unchanged" and replay["batch_id"] == 1
    ads = [json.loads(line) for line in (source / "ad_performance.jsonl").read_text().splitlines()]
    ads[0]["spend_paise"] = 20000
    rewrite(source, "ad_performance", ads)
    corrected = build_warehouse(source, database)
    assert corrected["changes"]["ad_performance"] == 1
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "select count(*),sum(spend_paise) from analytics.fct_ad_performance"
        ).fetchone() == (1, 20000)
        assert (
            connection.execute("select _loaded_at from raw.orders").fetchone()
            == original_order_load
        )
        assert connection.execute("select count(*) from meta.loads").fetchone()[0] == 2
    assert measure(warehouse=database)["total"]["metrics"]["roas"]["value"] == "2.500000"
    assert not database.with_suffix(".duckdb.lock").exists()


def test_late_earlier_purchase_recomputes_history(built):
    source, database, _ = built
    orders = [json.loads(line) for line in (source / "orders.jsonl").read_text().splitlines()]
    earlier = dict(
        orders[0],
        order_id="company:order:earlier",
        paid_at="2025-01-01T00:00:30Z",
        amount_paise=10000,
    )
    rewrite(source, "orders", orders + [earlier])
    build_warehouse(source, database)
    with duckdb.connect(str(database), read_only=True) as connection:
        assert (
            connection.execute(
                "select purchase_rank from analytics.fct_orders where order_id='company:order:4'"
            ).fetchone()[0]
            == 2
        )
    metrics = measure(warehouse=database)["total"]["metrics"]
    assert metrics["new_customers"]["value"] == 1
    assert metrics["orders"]["value"] == 2
    assert metrics["purchasing_sessions"]["value"] == 1


def test_partial_load_is_rolled_back_when_deletion_is_rejected(built):
    source, database, _ = built
    ads = [json.loads(line) for line in (source / "ad_performance.jsonl").read_text().splitlines()]
    ads[0]["spend_paise"] = 999
    rewrite(source, "ad_performance", ads)
    rewrite(source, "orders", [])
    with pytest.raises(ValueError, match="deletions"):
        load_observations(source, database)
    with duckdb.connect(str(database), read_only=True) as connection:
        assert (
            connection.execute("select spend_paise from raw.ad_performance").fetchone()[0] == 10000
        )
    assert measure(warehouse=database)["total"]["metrics"]["orders"]["value"] == 1


def test_database_cannot_mix_datasets(built):
    source, database, _ = built
    path = source / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["dataset_id"] = "another-company"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="different dataset"):
        build_warehouse(source, database)
    assert measure(warehouse=database)["dataset_id"] == "manual-contract-test"


def test_actual_dbt_failure_blocks_reports_then_full_refresh_recovers(built):
    source, database, _ = built
    with duckdb.connect(str(database)) as connection:
        connection.execute("update analytics.fct_ad_performance set spend_paise = -1")
    with pytest.raises(RuntimeError, match="dbt build failed"):
        build_warehouse(source, database)
    with pytest.raises(ValueError, match="unbuilt, failed, or stale"):
        measure(warehouse=database)
    assert not database.with_suffix(".duckdb.lock").exists()
    build_warehouse(source, database, full_refresh=True)
    assert measure(warehouse=database)["total"]["metrics"]["spend"]["value"] == 10000


def test_read_connection_is_read_only_and_artifacts_are_real(built):
    _, database, result = built
    with open_warehouse(database) as snapshot:
        with pytest.raises(duckdb.Error):
            snapshot.connection.execute("delete from analytics.fct_orders")
    from pathlib import Path

    target = Path(result["dbt_artifacts"]) / "target"
    manifest = json.loads((target / "manifest.json").read_text())
    model = manifest["nodes"]["model.nemo.fct_ad_performance"]
    assert model["config"]["materialized"] == "incremental"
    assert model["config"]["unique_key"] == ["business_date", "campaign_id", "device"]
    run = json.loads((target / "run_results.json").read_text())
    assert any(row["unique_id"].startswith("test.") for row in run["results"])
    assert all(row["status"] in ("success", "pass") for row in run["results"])


def test_source_freshness_detects_stale_loads(built):
    _, database, _ = built
    run_dbt(database, "source freshness")
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "update raw.orders set _loaded_at = current_timestamp - interval '3 days'"
        )
    with pytest.raises(RuntimeError, match="source freshness failed"):
        run_dbt(database, "source freshness")


def test_stale_model_definition_is_rejected(built, monkeypatch):
    _, database, _ = built
    monkeypatch.setattr("nemo.warehouse.project_hash", lambda: "changed-model-definition")
    with pytest.raises(ValueError, match="stale"):
        measure(warehouse=database)
