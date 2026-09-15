"""A manually authored canonical fixture proves producer-independent measurement."""

import hashlib
import json
import subprocess
import sys

import pytest

from nemo.measurement import measure


@pytest.fixture
def canonical_source(tmp_path):
    tables = {
        "customers": [
            {"customer_id": "company:customer:17", "first_seen_at": "2025-01-01T00:00:00Z"}
        ],
        "campaigns": [
            {"campaign_id": "company:campaign:9", "name": "Prospecting", "channel": "paid_social"}
        ],
        "ad_performance": [
            {
                "business_date": "2025-01-01",
                "campaign_id": "company:campaign:9",
                "device": "tablet",
                "impressions": 100,
                "clicks": 10,
                "spend_paise": 10000,
            }
        ],
        "sessions": [
            {
                "session_id": "company:session:8",
                "customer_id": "company:customer:17",
                "started_at": "2025-01-01T00:00:00Z",
                "channel": "paid_social",
                "campaign_id": "company:campaign:9",
                "device": "tablet",
            }
        ],
        "orders": [
            {
                "order_id": "company:order:4",
                "session_id": "company:session:8",
                "customer_id": "company:customer:17",
                "paid_at": "2025-01-01T00:01:00Z",
                "amount_paise": 50000,
            }
        ],
    }
    directory = tmp_path / "canonical"
    directory.mkdir()
    entries = {}
    for name, rows in tables.items():
        data = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (directory / f"{name}.jsonl").write_bytes(data)
        entries[name] = {"rows": len(rows), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {
        "schema_version": "2",
        "mode": "production",
        "dataset_id": "manual-contract-test",
        "channels": {"paid_social": True, "organic_search": False},
        "devices": ["tablet"],
        "currency": "INR",
        "money_unit": "paise",
        "amount_basis": "tax_exclusive_merchandise",
        "business_timezone": "Asia/Kolkata",
        "timestamp_timezone": "UTC",
        "observation_window": {
            "start_date_inclusive": "2025-01-01",
            "end_date_exclusive": "2025-01-02",
        },
        "tables": entries,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


def test_manual_canonical_source_without_generator(canonical_source):
    result = measure(canonical_source, channel="paid_social", device="tablet")
    assert result["mode"] == "production"  # provenance label; not a connector verification
    assert result["dataset_id"] == "manual-contract-test"
    assert result["total"]["metrics"]["orders"]["value"] == 1
    assert result["total"]["metrics"]["roas"]["value"] == "5.000000"
    assert result["total"]["metrics"]["media_cac"]["value"] == "10000.000000"
    assert result["measurement_health"] == "not_assessed"
    assert all(m["claim_type"] == "descriptive_metric" for m in result["registry"])


def test_generator_imports_are_forbidden_in_fresh_process(canonical_source):
    code = """import importlib.abc, sys
class BlockGenerator(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('nemo.simulation', 'nemo.contracts', 'nemo.artifacts'):
            raise AssertionError('Downstream attempted generator import')
sys.meta_path.insert(0, BlockGenerator())
from pathlib import Path
from nemo.measurement import measure
assert measure(Path(sys.argv[1]))['total']['metrics']['orders']['value'] == 1
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(canonical_source)],
        cwd=canonical_source,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "change",
    [{"channels": {"paid_social": "true"}}, {"dataset_id": ""}, {"devices": ["tablet", "tablet"]}],
)
def test_incomplete_canonical_metadata_is_rejected(canonical_source, change):
    path = canonical_source / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(change)
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        measure(canonical_source)
