import hashlib
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from nemo import artifacts
from nemo.artifacts import write_world
from nemo.contracts import TABLES, SimulationConfig
from nemo.simulation import generate


@pytest.fixture
def small_world():
    return generate(SimulationConfig(end_date=date(2025, 1, 3)))


def test_artifact_counts_hashes_and_private_boundary(tmp_path, small_world):
    lockfile = tmp_path / "uv.lock"
    lockfile.write_bytes(b"test dependency fingerprint")
    output = tmp_path / "run"
    manifest = write_world(small_world, output, lockfile=lockfile)
    assert manifest["mode"] == "synthetic"
    assert manifest["money_unit"] == "paise"
    assert manifest["observation_window"] == {
        "start_date_inclusive": "2025-01-01",
        "end_date_exclusive": "2025-01-03",
    }
    assert set(manifest["tables"]) == set(TABLES)
    public = output / "observations"
    for name, details in manifest["tables"].items():
        data = (public / f"{name}.jsonl").read_bytes()
        assert b"\r\n" not in data
        assert len(data.splitlines()) == details["rows"] == len(getattr(small_world, name))
        assert hashlib.sha256(data).hexdigest() == details["sha256"]
        assert all(isinstance(json.loads(line), dict) for line in data.splitlines())
    provenance = json.loads((output / "private" / "run.json").read_bytes())
    assert provenance["config"]["seed"] == 42
    assert provenance["lockfile_sha256"] == hashlib.sha256(lockfile.read_bytes()).hexdigest()
    assert (
        provenance["observation_manifest_sha256"]
        == hashlib.sha256((public / "manifest.json").read_bytes()).hexdigest()
    )
    for path in public.iterdir():
        text = path.read_text(encoding="utf-8")
        assert '"seed"' not in text
        assert '"payment_success_probability"' not in text
        assert '"refund_probability"' not in text
    assert set(provenance["source_sha256"]) >= {"simulation.py", "contracts.py"}


@pytest.mark.parametrize("existing", ["empty_directory", "populated_directory", "file"])
def test_existing_output_is_never_overwritten(tmp_path, small_world, existing):
    output = tmp_path / "run"
    if existing == "file":
        output.write_text("keep")
    else:
        output.mkdir()
        if existing == "populated_directory":
            (output / "keep.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        write_world(small_world, output)
    if existing == "file":
        assert output.read_text() == "keep"
    elif existing == "populated_directory":
        assert (output / "keep.txt").read_text() == "keep"
    else:
        assert list(output.iterdir()) == []


def test_failed_write_does_not_publish_or_leave_temporary_files(tmp_path, small_world, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(artifacts, "canonical_json", fail)
    with pytest.raises(OSError, match="simulated disk failure"):
        write_world(small_world, tmp_path / "run")
    assert list(tmp_path.iterdir()) == []


def test_concurrent_writer_lock_is_respected(tmp_path, small_world):
    lock = tmp_path / ".run.lock"
    lock.write_bytes(b"another writer owns this")
    with pytest.raises(FileExistsError):
        write_world(small_world, tmp_path / "run")
    assert lock.read_bytes() == b"another writer owns this"
    assert not (tmp_path / "run").exists()


def test_cli_is_reproducible_in_separate_processes(tmp_path):
    def run(destination, hashseed):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "nemo.cli",
                "--start",
                "2025-01-01",
                "--end",
                "2025-01-04",
                "--output",
                str(destination),
            ],
            cwd=tmp_path,
            env={**os.environ, "PYTHONHASHSEED": hashseed},
            capture_output=True,
            text=True,
            check=False,
        )

    first, second = tmp_path / "first", tmp_path / "second"
    a, b = run(first, "1"), run(second, "77")
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert json.loads(a.stdout)["status"] == "complete"
    assert json.loads(a.stdout)["rows"]["orders"] > 0
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()
    refused = run(first, "1")
    assert refused.returncode == 1
    assert json.loads(refused.stderr)["status"] == "error"


@pytest.mark.parametrize(
    "extra",
    [
        ["--end", "2024-01-01"],
        ["--seed", "-2"],
        ["--start", "not-a-date"],
        ["--lockfile", "does-not-exist.lock"],
    ],
)
def test_cli_rejects_invalid_inputs_without_outputs(tmp_path, extra):
    result = subprocess.run(
        [sys.executable, "-m", "nemo.cli", "--output", str(tmp_path / "run"), *extra],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not (tmp_path / "run").exists()
    assert "Traceback" not in result.stderr


def test_source_change_changes_private_fingerprint(tmp_path, small_world):
    manifest = write_world(small_world, tmp_path / "run")
    provenance = json.loads((tmp_path / "run" / "private" / "run.json").read_bytes())
    source = Path(artifacts.__file__).with_name("simulation.py").read_bytes()
    assert provenance["source_sha256"]["simulation.py"] == hashlib.sha256(source).hexdigest()
    assert (
        provenance["source_sha256"]["simulation.py"] != hashlib.sha256(source + b"\n").hexdigest()
    )
    assert manifest["schema_version"] == "1"
