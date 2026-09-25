"""Bounded observational saturation curves with holdout gates."""

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path

from nemo.economics_inputs import COST_COMPONENTS, read_table
from nemo.experiment_design import digest, encode
from nemo.observations import _integer, _text, open_snapshot


def fit(points):
    """Fit ordered exact observations; fitted parameters are numerical estimates."""

    def blocked(reason):
        return {"status": "not_assessed", "reason": reason}

    if len(points) < 24:
        return blocked("need_24_complete_weeks")
    if any(
        type(p["spend_paise"]) is not int
        or p["spend_paise"] < 0
        or type(p["contribution_before_media_paise"]) is not int
        for p in points
    ):
        raise ValueError("response observations require exact integer money")
    split = len(points) * 2 // 3
    train, audit = points[:split], points[split:]
    xs = [p["spend_paise"] for p in train]
    ys = [p["contribution_before_media_paise"] for p in train]
    positive = [x for x in xs if x > 0]
    if len(set(xs)) < 8 or not positive or max(positive) < 3 * min(positive):
        return blocked("insufficient_training_spend_variation")
    if any(not min(xs) <= p["spend_paise"] <= max(xs) for p in audit):
        return blocked("audit_spend_outside_training_support")
    candidates = []
    for i in range(41):
        b = max(xs) * 2 ** (-5 + i / 4)
        zs = [x / (b + x) for x in xs]
        a = max(0.0, sum(z * y for z, y in zip(zs, ys, strict=True)) / sum(z * z for z in zs))
        loss = sum((a * z - y) ** 2 for z, y in zip(zs, ys, strict=True))
        candidates.append((loss, i, a, b))
    _, index, a, b = min(candidates)
    if not a or index in (0, 40):
        return blocked("saturation_not_identified_within_grid")
    mean = sum(ys) / len(ys)
    errors = [
        abs(a * p["spend_paise"] / (b + p["spend_paise"]) - p["contribution_before_media_paise"])
        for p in audit
    ]
    mae = sum(errors) / len(errors)
    naive = sum(abs(p["contribution_before_media_paise"] - mean) for p in audit) / len(audit)
    if naive == 0 or mae >= naive * 0.95:
        return blocked("does_not_improve_constant_holdout_mae_by_5_percent")
    width = sorted(errors)[math.ceil(0.9 * len(errors)) - 1]
    return {
        "status": "estimated",
        "claim_type": "observational_response_model",
        "family": "a_times_spend_over_b_plus_spend",
        "a_paise": a,
        "b_paise": b,
        "support_paise": [min(xs), max(xs)],
        "training_weeks": len(train),
        "audit_weeks": len(audit),
        "audit_mae_paise": mae,
        "constant_audit_mae_paise": naive,
        "error_half_width_paise": width,
        "uncertainty": "90th_percentile_absolute_holdout_error_not_causal_interval",
        "action_eligibility": "scenario_only",
        "limitations": [
            "Spend may follow demand; this fit does not identify incremental contribution.",
            "Empirical bands do not guarantee future coverage or parameter certainty.",
            "A fixed family can miss promotions, seasonality and nonmonotone responses.",
        ],
    }


def evaluate(curve, spend_paise):
    if curve.get("status") != "estimated":
        raise ValueError("no eligible estimated curve")
    if (
        type(spend_paise) is not int
        or not curve["support_paise"][0] <= spend_paise <= curve["support_paise"][1]
    ):
        raise ValueError("spend outside supported range")
    a, b = curve["a_paise"], curve["b_paise"]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (a, b)):
        raise ValueError("invalid response parameters")
    if (
        type(curve["error_half_width_paise"]) not in (int, float)
        or not math.isfinite(curve["error_half_width_paise"])
        or curve["error_half_width_paise"] < 0
    ):
        raise ValueError("invalid response uncertainty")
    point = a * spend_paise / (b + spend_paise)
    width = curve["error_half_width_paise"]
    return {
        "spend_paise": spend_paise,
        "modelled_contribution_before_media_paise": point,
        "lower_paise": point - width,
        "upper_paise": point + width,
        "marginal_response": a * b / (b + spend_paise) ** 2,
        "claim_type": "conditional_scenario",
    }


def report(observations):
    source = Path(observations)
    with open_snapshot(source) as snapshot:
        payload = (source / "manifest.json").read_bytes()
        if digest(payload) != snapshot.manifest_sha256:
            raise ValueError("snapshot changed during response read")
        manifest = json.loads(payload)
        rows = read_table(source, manifest, "response_observations")
        contract = manifest.get("response_contract")
        groups = defaultdict(list)
        if rows is not None:
            if not isinstance(contract, dict) or contract.get("version") != "1":
                raise ValueError("response contract version 1 required")
            if (
                contract.get("cost_provenance") != "observed"
                or contract.get("weeks_complete") is not True
                or contract.get("variable_cost_components") != list(COST_COMPONENTS)
                or contract.get("outcome") != "contribution_before_media"
            ):
                raise ValueError("complete observed weekly economic components required")
            for key in ("scope", "lineage_reference"):
                _text(contract, key)
            seen = set()
            for row in rows:
                channel = _text(row, "channel")
                day = date.fromisoformat(_text(row, "week_start"))
                if not snapshot.contract.channels.get(channel):
                    raise ValueError("response channel must be declared paid media")
                if (
                    day.weekday() != 0
                    or not snapshot.start <= day
                    or day + timedelta(days=7) > snapshot.end
                ):
                    raise ValueError("response requires full Monday-start weeks in snapshot")
                if (day, channel) in seen:
                    raise ValueError("duplicate response week/channel")
                seen.add((day, channel))
                spend = _integer(row, "spend_paise")
                receipts = _integer(row, "merchandise_receipts_paise")
                refunds = _integer(row, "merchandise_refunds_paise")
                costs = sum(_integer(row, k) for k in COST_COMPONENTS)
                groups[channel].append(
                    {
                        "week_start": day.isoformat(),
                        "spend_paise": spend,
                        "contribution_before_media_paise": receipts - refunds - costs,
                    }
                )
        elif contract is not None:
            raise ValueError("declared response contract requires observations")
        analyses = []
        for channel, points in sorted(groups.items()):
            points.sort(key=lambda p: p["week_start"])
            if any(
                date.fromisoformat(b["week_start"]) - date.fromisoformat(a["week_start"])
                != timedelta(days=7)
                for a, b in zip(points, points[1:], strict=False)
            ):
                curve = {"status": "not_assessed", "reason": "incomplete_weekly_series"}
            else:
                curve = fit(points)
            analyses.append({"channel": channel, "observations": points, "curve": curve})
        result = {
            "schema_version": "1",
            "claim_type": "observational_response_analysis",
            "status": "assessed" if rows else "not_assessed",
            "scope": {"dataset_id": snapshot.contract.dataset_id, "mode": snapshot.contract.mode},
            "contract": contract,
            "channels": analyses,
            "provenance": {
                "manifest_sha256": snapshot.manifest_sha256,
                "code_sha256": digest(files("nemo").joinpath("response_curves.py").read_bytes()),
            },
            "limitations": [
                "Weekly aggregates are source assertions, not reconciled order economics.",
                "Observed contributions and fitted responses are not profit or causal effects.",
                "Production intervention recommendations require stronger evidence and validation.",
            ],
        }
        result["revision_id"] = digest(encode(result))
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = report(args.observations)
        with args.output.open("xb") as stream:
            stream.write(encode(result))
        return 0
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
