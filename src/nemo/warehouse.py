"""Canonical ingestion and dbt execution for one dataset per local DuckDB warehouse."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.canonical import SourceContract
from nemo.observations import REQUIRED_TABLES, open_snapshot

KEYS = {
    "customers": ("customer_id",),
    "campaigns": ("campaign_id",),
    "ad_performance": ("business_date", "campaign_id", "device"),
    "sessions": ("session_id",),
    "orders": ("order_id",),
}
INTEGERS = {"impressions", "clicks", "spend_paise", "amount_paise", "is_paid"}


def project_path() -> Path:
    return Path(str(files("nemo").joinpath("dbt")))


def project_hash() -> str:
    digest = hashlib.sha256()
    root = project_path()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".sql", ".yml"):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _state(connection) -> dict:
    return json.loads(connection.execute("select payload from meta.state").fetchone()[0])


def _save_state(connection, state: dict) -> None:
    connection.execute("delete from meta.state")
    connection.execute("insert into meta.state values (?)", [json.dumps(state, sort_keys=True)])


def load_observations(observations: Path, database: Path) -> dict:
    """Validate, then upsert a complete canonical snapshot without shrinking history."""
    with open_snapshot(observations) as snapshot:
        database.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(database)) as connection:
            connection.execute("begin transaction")
            try:
                connection.execute("create schema if not exists raw")
                connection.execute("create schema if not exists meta")
                connection.execute("create table if not exists meta.state(payload varchar)")
                connection.execute("""create table if not exists meta.loads(
                    batch_id bigint, manifest_sha256 varchar, loaded_at timestamptz,
                    changes_json varchar)""")
                prior_row = connection.execute("select payload from meta.state").fetchone()
                prior = json.loads(prior_row[0]) if prior_row else None
                if prior:
                    if (
                        prior["contract"]["dataset_id"] != snapshot.contract.dataset_id
                        or prior["contract"]["mode"] != snapshot.contract.mode
                    ):
                        raise ValueError("database belongs to a different dataset or source mode")
                    if (
                        prior["start"] != snapshot.start.isoformat()
                        or prior["end"] > snapshot.end.isoformat()
                    ):
                        raise ValueError(
                            "complete snapshot history cannot shrink or change its start"
                        )
                    if prior["manifest_sha256"] == snapshot.manifest_sha256:
                        connection.execute("commit")
                        return {"status": "unchanged", "batch_id": prior["batch_id"], "changes": {}}
                batch = prior["batch_id"] + 1 if prior else 1
                loaded_at = datetime.now(UTC)
                changes = {}
                for table in REQUIRED_TABLES:
                    cursor = snapshot.connection.execute(f"select * from {table}")
                    columns = [item[0] for item in cursor.description]
                    definitions = ", ".join(
                        f"{column} {'bigint' if column in INTEGERS else 'varchar'}"
                        for column in columns
                    )
                    connection.execute(f"""create table if not exists raw.{table}(
                        {definitions}, _row_hash varchar, _batch_id bigint,
                        _loaded_at timestamptz)""")
                    records = []
                    for row in cursor:
                        record = dict(zip(columns, tuple(row), strict=True))
                        encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
                        record.update(
                            _row_hash=hashlib.sha256(encoded).hexdigest(),
                            _batch_id=batch,
                            _loaded_at=loaded_at,
                        )
                        records.append(record)
                    connection.execute(
                        f"create or replace temp table incoming as "
                        f"select * from raw.{table} where false"
                    )
                    if records:
                        types = {
                            column: "BIGINT" if column in INTEGERS else "VARCHAR"
                            for column in columns
                        }
                        types.update(
                            _row_hash="VARCHAR", _batch_id="BIGINT", _loaded_at="TIMESTAMPTZ"
                        )
                        with tempfile.TemporaryDirectory(prefix="nemo-load-") as directory:
                            bulk = Path(directory) / "normalized.jsonl"
                            with bulk.open("w", encoding="utf-8", newline="\n") as stream:
                                for record in records:
                                    stream.write(
                                        json.dumps(record, default=lambda value: value.isoformat())
                                        + "\n"
                                    )
                            connection.execute(
                                "insert into incoming select * from read_json(?, columns=?)",
                                [str(bulk), types],
                            )
                    match = " and ".join(f"old.{key} = inc.{key}" for key in KEYS[table])
                    deleted = connection.execute(f"""
                        select count(*) from raw.{table} old
                        where not exists (select 1 from incoming inc where {match})
                    """).fetchone()[0]
                    if deleted:
                        raise ValueError(
                            f"snapshot removes {deleted} {table} keys; deletions are not supported"
                        )
                    connection.execute(f"""create or replace temp table changed as
                        select inc.* from incoming inc
                        where not exists (select 1 from raw.{table} old
                                          where {match} and old._row_hash = inc._row_hash)""")
                    changes[table] = connection.execute("select count(*) from changed").fetchone()[
                        0
                    ]
                    change_match = " and ".join(f"old.{key} = inc.{key}" for key in KEYS[table])
                    connection.execute(
                        f"delete from raw.{table} old using changed inc where {change_match}"
                    )
                    connection.execute(f"insert into raw.{table} select * from changed")
                state = {
                    "contract": asdict(snapshot.contract),
                    "start": snapshot.start.isoformat(),
                    "end": snapshot.end.isoformat(),
                    "manifest_sha256": snapshot.manifest_sha256,
                    "table_hashes": snapshot.table_hashes,
                    "batch_id": batch,
                    "built_batch": None,
                    "project_hash": None,
                }
                _save_state(connection, state)
                connection.execute(
                    "insert into meta.loads values (?, ?, ?, ?)",
                    [batch, snapshot.manifest_sha256, loaded_at, json.dumps(changes)],
                )
                connection.execute("commit")
                return {"status": "loaded", "batch_id": batch, "changes": changes}
            except BaseException:
                connection.execute("rollback")
                raise


def run_dbt(database: Path, command: str, *, full_refresh: bool = False) -> Path:
    if command not in ("build", "compile", "source freshness", "docs generate"):
        raise ValueError("unsupported dbt operation")
    artifacts = database.parent / (database.stem + "-dbt")
    artifacts.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        NEMO_DUCKDB_PATH=str(database.absolute()),
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
        DBT_LOG_PATH=str((artifacts / "logs").absolute()),
    )
    args = [
        sys.executable,
        "-c",
        "from dbt.cli.main import cli; cli()",
        *command.split(),
        "--project-dir",
        str(project_path()),
        "--profiles-dir",
        str(project_path()),
        "--target",
        "local",
        "--target-path",
        str((artifacts / "target").absolute()),
    ]
    if full_refresh:
        args.append("--full-refresh")
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=180)
    (artifacts / (command.replace(" ", "-") + ".log")).write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(f"dbt {command} failed; see {artifacts}: {result.stdout[-2200:]}")
    return artifacts


def build_warehouse(observations: Path, database: Path, *, full_refresh: bool = False) -> dict:
    database = database.absolute()
    database.parent.mkdir(parents=True, exist_ok=True)
    lock_path = database.with_suffix(database.suffix + ".lock")
    lock = lock_path.open("x")
    try:
        result = load_observations(observations, database)
        with duckdb.connect(str(database)) as connection:
            state = _state(connection)
            state["built_batch"] = None
            _save_state(connection, state)
        artifacts = run_dbt(database, "build", full_refresh=full_refresh)
        with duckdb.connect(str(database)) as connection:
            state = _state(connection)
            state.update(built_batch=state["batch_id"], project_hash=project_hash())
            _save_state(connection, state)
        return {**result, "database": str(database), "dbt_artifacts": str(artifacts)}
    finally:
        lock.close()
        lock_path.unlink()


@dataclass
class WarehouseSnapshot:
    connection: object
    start: date
    end: date
    manifest_sha256: str
    table_hashes: dict[str, str]
    contract: SourceContract


@contextmanager
def open_warehouse(database: Path):
    with duckdb.connect(str(database), read_only=True) as connection:
        state = _state(connection)
        if state["built_batch"] != state["batch_id"] or state["project_hash"] != project_hash():
            raise ValueError("warehouse is unbuilt, failed, or stale; run nemo-warehouse build")
        yield WarehouseSnapshot(
            connection,
            date.fromisoformat(state["start"]),
            date.fromisoformat(state["end"]),
            state["manifest_sha256"],
            state["table_hashes"],
            SourceContract(**state["contract"]),
        )


@contextmanager
def temporary_warehouse(observations: Path):
    """M2 compatibility path using the same real dbt models."""
    with tempfile.TemporaryDirectory(prefix="nemo-warehouse-") as directory:
        database = Path(directory) / "nemo.duckdb"
        build_warehouse(observations, database)
        with open_warehouse(database) as snapshot:
            yield snapshot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="NEMO canonical local warehouse")
    parser.add_argument("command", choices=("build", "freshness", "docs", "compile"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--full-refresh", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            if args.observations is None:
                parser.error("build requires --observations")
            result = build_warehouse(
                args.observations, args.database, full_refresh=args.full_refresh
            )
        else:
            command = {
                "freshness": "source freshness",
                "docs": "docs generate",
                "compile": "compile",
            }[args.command]
            result = {"dbt_artifacts": str(run_dbt(args.database, command))}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, RuntimeError, duckdb.Error, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
