"""Deterministic snapshots with public observations and private reproducibility metadata."""

import hashlib
import json
import platform
import shutil
import tempfile
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from nemo import __version__
from nemo.contracts import SCHEMA_VERSION, TABLES, World
from nemo.simulation import GENERATOR_VERSION


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            default=_json_default,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_world(world: World, destination: Path, *, lockfile: Path | None = None) -> dict:
    """Publish a complete snapshot to a new path. Existing outputs are never overwritten."""
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Cooperating NEMO writers cannot publish the same destination concurrently.
    lock_path = destination.with_name(f".{destination.name}.lock")
    lock = lock_path.open("xb")
    temporary: Path | None = None
    try:
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Output already exists: {destination}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
        observations = temporary / "observations"
        observations.mkdir()
        tables = {}
        for name in TABLES:
            path = observations / f"{name}.jsonl"
            rows = getattr(world, name)
            with path.open("wb") as stream:
                for row in rows:
                    stream.write(canonical_json(asdict(row)))
            tables[name] = {"rows": len(rows), "sha256": file_hash(path)}
        manifest = {
            "mode": "synthetic",
            "schema_version": SCHEMA_VERSION,
            "currency": "INR",
            "money_unit": "paise",
            "amount_basis": "tax_exclusive_merchandise",
            "business_timezone": "Asia/Kolkata",
            "timestamp_timezone": "UTC",
            "observation_window": {
                "start_date_inclusive": world.config.start_date.isoformat(),
                "end_date_exclusive": world.config.end_date.isoformat(),
            },
            "tables": tables,
        }
        (observations / "manifest.json").write_bytes(canonical_json(manifest))
        source_files = sorted(Path(__file__).parent.glob("*.py"))
        provenance = {
            "config": asdict(world.config),
            "generator_version": GENERATOR_VERSION,
            "package_version": __version__,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "source_sha256": {path.name: file_hash(path) for path in source_files},
            "lockfile_sha256": file_hash(lockfile) if lockfile is not None else None,
            "observation_manifest_sha256": file_hash(observations / "manifest.json"),
        }
        (temporary / "private").mkdir()
        (temporary / "private" / "run.json").write_bytes(canonical_json(provenance))
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Output already exists: {destination}")
        temporary.rename(destination)
        temporary = None
        return manifest
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
        lock.close()
        lock_path.unlink()
