"""Manually authored canonical journeys; no reference generator required."""

import json
import subprocess
import sys

import pytest
from test_economics import make_source, rewrite

from nemo.journeys import main, report
from nemo.warehouse import build_warehouse


@pytest.fixture(scope="module")
def journey_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("journeys")
    source = make_source(root / "source")
    sessions = []
    for sid, customer, stamp, channel in (
        ("a", "c1", "2025-01-10T00:00:00Z", "paid_social"),
        ("b", "c1", "2025-01-11T00:00:00Z", "direct"),
        ("c", "c1", "2025-01-12T00:00:00Z", "paid_social"),
        ("d", "c1", "2025-01-12T00:00:00Z", "direct"),
        ("future", "c1", "2025-01-14T00:00:00Z", "direct"),
        ("old", "c2", "2025-01-01T00:00:00Z", "direct"),
        ("nonbuyer", "visitor", "2025-01-11T00:00:00Z", "paid_social"),
    ):
        sessions.append(
            {
                "session_id": sid,
                "customer_id": customer,
                "started_at": stamp,
                "channel": channel,
                "campaign_id": "a1" if channel == "paid_social" else None,
                "device": "tablet",
            }
        )
    rewrite(source, "sessions", sessions)
    rewrite(
        source,
        "orders",
        [
            {
                "order_id": oid,
                "customer_id": customer,
                "session_id": sid,
                "paid_at": stamp,
                "amount_paise": 9007199254740993,
            }
            for oid, customer, sid, stamp in (
                ("o1", "c1", "d", "2025-01-12T00:00:00Z"),
                ("o2", "c1", "d", "2025-01-13T00:00:00.000001Z"),
                ("o3", "c2", "old", "2025-03-10T00:00:00Z"),
            )
        ],
    )
    # Keep only the canonical warehouse boundary; no optional event/economics feeds.
    manifest = json.loads((source / "manifest.json").read_text())
    manifest.pop("economics_contract")
    for name in ("order_items", "refunds", "order_variable_costs"):
        manifest["tables"].pop(name)
        (source / f"{name}.jsonl").unlink()
    (source / "manifest.json").write_text(json.dumps(manifest))
    database = root / "nemo.duckdb"
    build_warehouse(source, database)
    return source, database


def test_hand_calculated_path_time_and_repeated_channels(journey_source):
    result = report(journey_source[1], lookback_days=2)
    first, second, empty = result["journeys"]
    assert first["channel_path"] == ["paid_social", "direct", "paid_social", "direct"]
    assert first["time_to_purchase_microseconds"] == 2 * 86400 * 1000000
    assert first["touch_count"] == first["journey_length_sessions"] == 4
    assert first["prior_channels"] == ["direct", "paid_social"]
    assert first["channel_combination"] == ["direct", "paid_social"]
    assert first["touches"][0]["campaign_id"] == "a1"
    assert first["touches"][0]["device"] == "tablet"
    assert second["channel_path"] == ["paid_social", "direct"]
    assert second["time_to_purchase_microseconds"] == 86400 * 1000000 + 1
    assert empty["touch_count"] == 0
    assert empty["time_to_purchase_microseconds"] is None
    assert not empty["purchase_session_in_window"]


def test_boundaries_identity_and_future_exclusion(journey_source):
    result = report(journey_source[1], lookback_days=2)
    assert result["total"]["paid_orders"] == 3
    assert result["total"]["zero_touch_orders"] == 1
    assert result["total"]["timestamp_tie_orders"] == 2
    assert not any(j["history_boundary_limited"] for j in result["journeys"])
    assert all(
        t["session_id"] not in ("future", "nonbuyer")
        for j in result["journeys"]
        for t in j["touches"]
    )
    assert result["journeys"][0]["purchase_session_in_window"]
    assert result["source_mode"] == "production"


def test_reconciliation_assists_and_censoring(journey_source):
    result = report(journey_source[1])
    assert sum(p["orders"] for p in result["path_frequency"]) == 3
    assert sum(p["orders"] for p in result["channel_combinations"]) == 3
    assert result["total"]["history_boundary_limited_orders"] == 2
    assert result["prior_channel_appearances"] == [
        {"channel": "direct", "orders": 2},
        {"channel": "paid_social", "orders": 2},
    ]
    assert report(journey_source[1]) == result


@pytest.mark.parametrize("value", [0, -1, 3651, True, 1.5, "30"])
def test_invalid_lookback(journey_source, value):
    with pytest.raises(ValueError, match="lookback_days"):
        report(journey_source[1], lookback_days=value)


def test_cli_output_and_no_overwrite(journey_source, tmp_path, capsys):
    target = tmp_path / "journeys.json"
    args = ["--warehouse", str(journey_source[1]), "--output", str(target)]
    assert main(args) == 0
    original = target.read_bytes()
    assert json.loads(original)["total"]["paid_orders"] == 3
    assert main(args) == 1
    assert target.read_bytes() == original
    assert '"status": "error"' in capsys.readouterr().err


def test_no_generator_or_source_files_required(journey_source):
    source, database = journey_source
    code = """import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('nemo.simulation','nemo.contracts','nemo.artifacts',
                        'nemo.lab_economics','nemo.lab_payment','nemo.lab_tracking'):
            raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
def guard(event,args):
    if event == 'open' and isinstance(args[0],str):
        if any(x in args[0] for x in ('private', 'run.json', '.jsonl', 'manifest.json')):
            raise AssertionError(args[0])
sys.addaudithook(guard)
from pathlib import Path
from nemo.journeys import report
assert report(Path(sys.argv[1]))['total']['paid_orders'] == 3
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(database)], cwd=source, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
