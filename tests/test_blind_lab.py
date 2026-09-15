"""Blind evaluation scoring, sealing, worker isolation and cutoff checks."""

import json
import shutil
import subprocess
import sys
from datetime import date

import pytest
from test_decision_case import write_source

from nemo.blind_lab import (
    crop_snapshot,
    digest,
    encode,
    method_fingerprint,
    predict,
    score,
    score_cases,
    write_new,
)


def example(
    expected,
    found,
    *,
    device="tablet",
    predicted=None,
    onset="2025-01-02",
    cutoff="2025-01-03",
    scenario="scenario",
):
    case = {
        "finding": found,
        "supported_devices": predicted if predicted is not None else ["tablet"],
        "recommendations": {"measurement_eligible": []},
    }
    truth = {
        "expected": expected,
        "device": device,
        "onset": onset,
        "cutoff": cutoff,
        "scenario": scenario,
        "world": "manual",
        "condition": "business",
    }
    return case, truth


def test_confusion_denominators_localization_and_misses():
    examples = [
        example("payment_stage_hypothesis", "payment_stage_hypothesis"),
        example("payment_stage_hypothesis", "payment_stage_hypothesis", predicted=["desktop"]),
        example("payment_stage_hypothesis", "insufficient_data"),
        example("no_signal", "payment_stage_hypothesis", onset=None, scenario="control"),
        example("no_signal", "no_signal", onset=None, scenario="control2"),
        example("measurement_issue", "measurement_issue", scenario="tracking"),
    ]
    cases = {str(i): item[0] for i, item in enumerate(examples)}
    truths = {str(i): item[1] for i, item in enumerate(examples)}
    result = score_cases(cases, truths)
    assert result["payment_detection_recall"]["numerator"] == 2
    assert result["payment_detection_recall"]["denominator"] == 3
    assert result["exact_device_localization"]["numerator"] == 1
    assert result["healthy_false_positive_rate"]["value"] == 0.5
    assert result["tracking_routing_recall"]["value"] == 1
    assert result["independent_worlds"] == 1


def test_zero_denominator_is_unknown():
    case, truth = example("no_signal", "no_signal", onset=None)
    result = score_cases({"one": case}, {"one": truth})
    assert result["payment_detection_recall"]["value"] is None


def test_delay_is_first_correct_checkpoint_and_misses_are_censored():
    pairs = [
        example("payment_stage_hypothesis", "no_signal", cutoff="2025-01-09"),
        example("payment_stage_hypothesis", "payment_stage_hypothesis", cutoff="2025-01-16"),
        example("payment_stage_hypothesis", "no_signal", cutoff="2025-01-16", scenario="missed"),
    ]
    result = score_cases(
        {str(i): p[0] for i, p in enumerate(pairs)}, {str(i): p[1] for i, p in enumerate(pairs)}
    )
    delays = {row["scenario"]: row for row in result["detection_lag"]}
    assert delays["scenario"]["lag_days"] == 14
    assert delays["missed"]["lag_days"] is None
    assert delays["missed"]["right_censored"] is True


def test_missing_trial_not_silently_discarded():
    with pytest.raises(ValueError, match="every trial"):
        score_cases({}, {"one": {}})


def test_crop_excludes_future_customer_session_order_and_event_rows(tmp_path):
    source = write_source(tmp_path / "source", "business")
    destination = tmp_path / "cropped"
    crop_snapshot(source, destination, date(2025, 1, 2))
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["tables"]["sessions"]["rows"] == 200
    assert manifest["tables"]["orders"]["rows"] == 40
    assert manifest["observation_window"]["end_date_exclusive"] == "2025-01-02"
    assert all(
        "2025-01-02" not in row for row in (destination / "events.jsonl").read_text().splitlines()
    )
    with pytest.raises(FileExistsError):
        crop_snapshot(source, destination, date(2025, 1, 2))


@pytest.fixture(scope="module")
def sealed_manual(tmp_path_factory):
    root = tmp_path_factory.mktemp("blind-manual")
    source = root / "inputs" / "t0001" / "observations"
    source.parent.mkdir(parents=True)
    write_source(source, "healthy")
    truth = {
        "version": "1",
        "trials": {
            "t0001": {
                "expected": "no_signal",
                "device": None,
                "onset": None,
                "cutoff": "2025-01-03",
                "scenario": "manual-control",
                "world": "manual",
                "condition": "healthy",
            }
        },
    }
    write_new(root / "private" / "truth.json", truth)
    spec = {
        "version": "1",
        "method": method_fingerprint(),
        "truth_sha256": digest(encode(truth)),
        "trials": [
            {
                "trial_id": "t0001",
                "split": "development",
                "baseline_start": "2025-01-01",
                "current_start": "2025-01-02",
                "cutoff": "2025-01-03",
                "manifest_sha256": digest((source / "manifest.json").read_bytes()),
            }
        ],
    }
    write_new(root / "protocol.json", spec)
    predict(root, "development")
    return root


@pytest.fixture
def bundle(sealed_manual, tmp_path):
    root = tmp_path / "copy"
    shutil.copytree(sealed_manual, root)
    return root


def test_real_worker_can_predict_manual_canonical_data_and_replay(bundle):
    assert score(bundle, "development")["exact_diagnosis"]["value"] == 1
    assert predict(bundle, "development")["status"] == "already_sealed"


@pytest.mark.parametrize("target", ["case", "truth", "protocol", "seal", "dbt"])
def test_tampered_benchmark_is_rejected(bundle, target):
    paths = {
        "case": bundle / "predictions/development/t0001.json",
        "dbt": bundle / "predictions/development/t0001.dbt.json",
        "truth": bundle / "private/truth.json",
        "protocol": bundle / "protocol.json",
        "seal": bundle / "predictions/development/seal.json",
    }
    path = paths[target]
    value = json.loads(path.read_text())
    if target == "seal":
        value["entries"] = []
    else:
        value["tampered"] = True
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        score(bundle, "development")


def test_score_requires_seal_before_truth_access(bundle):
    (bundle / "predictions/development/seal.json").unlink()
    (bundle / "private/truth.json").write_text("unreadable truth")
    with pytest.raises(FileNotFoundError):
        score(bundle, "development")


def test_changed_detector_cannot_predict_under_old_freeze(bundle, monkeypatch):
    monkeypatch.setattr("nemo.blind_lab.method_fingerprint", lambda: {"changed": True})
    with pytest.raises(ValueError, match="changed after freeze"):
        predict(bundle, "development")


def test_worker_blocks_private_reads_and_lab_imports(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    (private / "truth.json").write_text("{}")
    code = """from pathlib import Path
import sys
from nemo.blind_worker import install_guard
root=Path(sys.argv[1])
install_guard(root)
for action in (lambda: (root/'private/truth.json').read_text(),
               lambda: __import__('nemo.lab_payment'),
               lambda: __import__('nemo.blind_lab')):
    try:
        action()
    except PermissionError:
        pass
    else:
        raise AssertionError('boundary bypass')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_prediction_does_not_read_truth(bundle):
    before = (bundle / "predictions/development/t0001.json").read_bytes()
    (bundle / "predictions/development/seal.json").unlink()
    (bundle / "predictions/development/t0001.json").unlink()
    (bundle / "predictions/development/t0001.dbt.json").unlink()
    (bundle / "private/truth.json").write_text("invalid private truth")
    predict(bundle, "development")
    assert (bundle / "predictions/development/t0001.json").read_bytes() == before
