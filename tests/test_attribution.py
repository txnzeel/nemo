"""Hand-calculated attribution, exact money, comparison and canonical boundary checks."""

import copy
import json
import subprocess
import sys
from fractions import Fraction

import pytest
from test_journeys import journey_source as journey_source

from nemo import attribution
from nemo.attribution import MODELS, WARNING, allocate, main, render_html, report, weights


def touches(days):
    return [{"started_at": f"2025-01-{day:02d}T00:00:00Z"} for day in days]


@pytest.mark.parametrize(
    "model,expected",
    [
        ("first_touch", [1, 0, 0]),
        ("last_touch", [0, 0, 1]),
        ("linear", [Fraction(1, 3)] * 3),
        ("position_based", [Fraction(2, 5), Fraction(1, 5), Fraction(2, 5)]),
        ("time_decay", [Fraction(1, 7), Fraction(2, 7), Fraction(4, 7)]),
    ],
)
def test_hand_calculated_weights(model, expected):
    actual = weights(model, touches([1, 8, 15]))
    if model == "time_decay":
        assert all(abs(a - b) < Fraction(1, 10**24) for a, b in zip(actual, expected, strict=True))
        assert sum(actual) == 1
        assert all(10**24 % a.denominator == 0 for a in actual)
    else:
        assert actual == expected


def test_short_paths_and_position_interior():
    for model in MODELS:
        assert weights(model, []) == []
        assert weights(model, touches([1])) == [1]
    assert weights("position_based", touches([1, 2])) == [Fraction(1, 2)] * 2
    assert weights("position_based", touches([1, 2, 3, 4])) == [
        Fraction(2, 5),
        Fraction(1, 10),
        Fraction(1, 10),
        Fraction(2, 5),
    ]
    assert weights("time_decay", touches([1, 1])) == [Fraction(1, 2)] * 2


def test_decay_precision_and_half_life_sensitivity():
    path = [{"started_at": "2010-01-01T00:00:00Z"}, {"started_at": "2025-01-01T00:00:00Z"}]
    assert weights("time_decay", path, 1) == [0, 1]
    fast = weights("time_decay", touches([1, 8]), 1)
    slow = weights("time_decay", touches([1, 8]), 7)
    assert abs(fast[0] - Fraction(1, 129)) < Fraction(1, 10**24)
    assert abs(slow[0] - Fraction(1, 3)) < Fraction(1, 10**24)
    assert fast[1] > slow[1]


def test_largest_remainder_and_large_exact_amounts():
    assert allocate(101, weights("linear", touches([1, 2, 3]))) == [34, 34, 33]
    assert allocate(101, weights("position_based", touches([1, 2, 3]))) == [41, 20, 40]
    for amount in (0, 1, 2, 101, 9007199254740993, 2**63 - 1):
        for model in MODELS:
            shares = weights(model, touches([1, 2, 3, 4]))
            credited = allocate(amount, shares)
            assert sum(credited) == amount
            assert all(type(x) is int and x >= 0 for x in credited)
            assert all(
                abs(Fraction(x) - amount * share) < 1
                for x, share in zip(credited, shares, strict=True)
            )


@pytest.mark.parametrize("value", [0, -1, 3651, True, 1.5, "7"])
def test_invalid_half_life(value):
    with pytest.raises(ValueError, match="half_life"):
        weights("linear", [], value)


def test_invalid_model_or_allocation():
    with pytest.raises(ValueError, match="model"):
        weights("invented", [])
    for amount, shares in (
        (True, [Fraction(1)]),
        (-1, [Fraction(1)]),
        (1, []),
        (1, [Fraction(-1), Fraction(2)]),
        (1, [Fraction(1, 2)]),
    ):
        with pytest.raises(ValueError):
            allocate(amount, shares)


def fraction(row):
    return Fraction(row["numerator"], row["denominator"])


def test_manual_canonical_credit_conservation_and_unassigned(journey_source):
    result = report(journey_source[1], lookback_days=2)
    amount = 9007199254740993
    assert result["claim_type"] == "attribution_result"
    assert result["source_mode"] == "production"
    assert result["total"] == {"paid_orders": 3, "gross_merchandise_paise": 3 * amount}
    for model in result["models"].values():
        assert fraction(model["total_conversion_credit"]) == 3
        assert model["total_gross_merchandise_credit_paise"] == 3 * amount
        for dimension in ("channels", "campaigns"):
            assert sum(fraction(row["conversion_credit"]) for row in model[dimension]) == 3
            assert (
                sum(row["gross_merchandise_credit_paise"] for row in model[dimension]) == 3 * amount
            )
        for order in model["orders"]:
            assert sum(fraction(row["conversion_credit"]) for row in order["allocations"]) == 1
            assert (
                sum(row["gross_merchandise_credit_paise"] for row in order["allocations"]) == amount
            )
            assert not any(
                row["session_id"] in ("future", "nonbuyer") for row in order["allocations"]
            )
        empty = model["orders"][2]
        assert empty["status"] == "unassigned_no_eligible_touch"
        assert empty["allocations"] == [
            {
                "session_id": None,
                "channel": None,
                "campaign_id": None,
                "conversion_credit": {"numerator": 1, "denominator": 1},
                "gross_merchandise_credit_paise": amount,
            }
        ]
    assert report(journey_source[1], lookback_days=2) == result


def test_channel_disagreement_and_repeated_channel_credit(journey_source):
    result = report(journey_source[1], lookback_days=2)
    amount = 9007199254740993
    rows = {r["channel"]: r for r in result["channel_comparison"]}
    social = rows["paid_social"]
    assert social["gross_merchandise_credit_paise"]["first_touch"] == 2 * amount
    assert social["gross_merchandise_credit_paise"]["last_touch"] == 0
    assert social["model_range_paise"] == 2 * amount
    assert social["delta_from_last_touch_paise"]["first_touch"] == 2 * amount
    assert rows[None]["model_range_paise"] == 0
    linear = result["models"]["linear"]["channels"]
    assert (
        next(fraction(r["conversion_credit"]) for r in linear if r["channel"] == "paid_social") == 1
    )
    assert result["coverage"]["timestamp_tie_orders"] == 2


def test_source_binding(journey_source, monkeypatch):
    original = attribution.journey_report

    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        value["provenance"]["manifest_sha256"] = "different"
        return value

    monkeypatch.setattr(attribution, "journey_report", changed)
    with pytest.raises(ValueError, match="changed"):
        report(journey_source[1])


def test_comparison_html_escapes_source_labels(journey_source):
    result = copy.deepcopy(report(journey_source[1]))
    result["dataset_id"] = '<script>alert("dataset")</script>'
    result["channel_comparison"][0]["channel"] = '<img src=x onerror="alert(1)">'
    html = render_html(result)
    assert WARNING in html
    assert "Model range" in html
    assert "<script>" not in html and "<img " not in html
    assert "&lt;script&gt;" in html and "&lt;img " in html
    assert "not a confidence interval" in html


def test_cli_report_comparison_and_no_overwrite(journey_source, tmp_path, capsys):
    output, html = tmp_path / "report.json", tmp_path / "comparison.html"
    args = [
        "--warehouse",
        str(journey_source[1]),
        "--output",
        str(output),
        "--html",
        str(html),
        "--lookback-days",
        "2",
    ]
    assert main(args) == 0
    original = output.read_bytes(), html.read_bytes()
    assert json.loads(original[0])["total"]["paid_orders"] == 3
    assert main(args) == 1
    assert (output.read_bytes(), html.read_bytes()) == original
    assert '"status": "error"' in capsys.readouterr().err
    same = tmp_path / "same"
    assert (
        main(["--warehouse", str(journey_source[1]), "--output", str(same), "--html", str(same)])
        == 1
    )
    assert not same.exists()


def test_canonical_only_subprocess(journey_source):
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
from nemo.attribution import report
assert report(Path(sys.argv[1]))['total']['paid_orders'] == 3
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(database)], cwd=source, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_many_decay_paths_have_serializable_bounded_credit():
    total = Fraction()
    for day in range(2, 29):
        for half_life in range(1, 31):
            shares = weights("time_decay", touches([1, day]), half_life)
            assert sum(shares) == 1
            total += shares[0]
    assert 10**24 % total.denominator == 0
    json.dumps(attribution.rational(total))
