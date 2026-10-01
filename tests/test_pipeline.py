"""Manual canonical pipeline publication and recovery, without generator state."""

import json
from pathlib import Path

import pytest
from test_experiments import make_manual

from nemo import pipeline


@pytest.fixture
def config(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    make_manual(source)
    return {
        "observations": str(source / "observations"),
        "output": str(tmp_path / "published"),
        "baseline_start": "2025-01-01",
        "current_start": "2025-01-05",
    }


def test_publish_replay_verify_and_corruption(config, tmp_path, capsys):
    first = pipeline.run(config)
    assert first["status"] == "published"
    result = pipeline.run(config)
    assert result == {"status": "unchanged", "run_id": first["run_id"]}
    output = Path(config["output"]) / result["run_id"]
    assert pipeline.verify(output)["action_authorization"] is False
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    assert pipeline.main(["--config", str(path), "--verify", result["run_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified"
    (output / "analyst.json").write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        pipeline.run(config)
    assert not (Path(config["output"]) / ".pipeline.lock").exists()


def test_failure_never_publishes_partial_and_retry_recovers(config, monkeypatch):
    with monkeypatch.context() as patch:

        def fail(*args, **kwargs):
            raise ValueError("injected explanation failure")

        patch.setattr(pipeline, "explain", fail)
        with pytest.raises(ValueError, match="injected"):
            pipeline.run(config)
    root = Path(config["output"])
    assert not [p for p in root.iterdir() if p.is_dir() and len(p.name) == 64]
    assert not list(root.glob(".pending-*"))
    assert not (root / ".pipeline.lock").exists()
    result = pipeline.run(config)
    assert result["status"] == "published"
    pipeline.verify(root / result["run_id"])


def test_existing_lock_and_changed_source_fail_closed(config):
    root = Path(config["output"])
    root.mkdir()
    lock = root / ".pipeline.lock"
    lock.write_text("other process")
    with pytest.raises(FileExistsError):
        pipeline.run(config)
    assert lock.read_text() == "other process"
    lock.unlink()
    source = Path(config["observations"]) / "orders.jsonl"
    source.write_bytes(source.read_bytes() + b"{}\n")
    with pytest.raises(ValueError, match="checksum"):
        pipeline.run(config)
    assert not (root / "warehouse.duckdb").exists()


def test_cli_rejects_path_in_run_identity(tmp_path, capsys):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output": str(tmp_path)}))
    assert pipeline.main(["--config", str(config), "--verify", "../private"]) == 1
    assert "../private" not in capsys.readouterr().err


@pytest.mark.parametrize("value", [{}, {"observations": "relative"}, []])
def test_configuration_fails_closed(value):
    with pytest.raises(ValueError):
        pipeline.run(value)
