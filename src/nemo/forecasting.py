"""Chronological naive forecasts and explicitly conditional traffic scenarios."""

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta
from fractions import Fraction
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.experiment_design import digest, encode
from nemo.metrics import REGISTRY
from nemo.observations import BUSINESS_ZONE
from nemo.warehouse import open_warehouse


def exact(value):
    value = Fraction(value)
    return {"numerator": value.numerator, "denominator": value.denominator}


def _predict(history, horizon, method):
    return [history[-1] if method == "last_value" else history[-7 + i % 7] for i in range(horizon)]


def backtest(values, horizon=7):
    if type(horizon) is not int or not 1 <= horizon <= 14:
        raise ValueError("horizon must be an integer from 1 to 14")
    if any(type(v) is not int or v < 0 for v in values):
        raise ValueError("daily observations must be nonnegative integers")
    origins = list(range(14, len(values) - horizon + 1))
    if len(origins) < 40 + 2 * (horizon - 1):
        return {
            "status": "not_assessed",
            "reason": "need_20_selection_and_20_audit_origins_plus_horizon_gap",
        }
    split = len(origins) // 2
    selection, audit = origins[:split], origins[split + horizon - 1 :]
    candidates = {}
    for method in ("last_value", "weekly_seasonal_naive"):
        errors = []
        for origin in selection:
            errors.extend(
                p - y
                for p, y in zip(
                    _predict(values[:origin], horizon, method),
                    values[origin : origin + horizon],
                    strict=True,
                )
            )
        candidates[method] = Fraction(sum(abs(e) for e in errors), len(errors))
    winner = min(candidates, key=lambda m: (candidates[m], m))
    by_horizon = [[] for _ in range(horizon)]
    audit_errors, covered = [], 0
    for h in range(horizon):
        for origin in selection:
            by_horizon[h].append(
                abs(_predict(values[:origin], horizon, winner)[h] - values[origin + h])
            )
    widths = [sorted(es)[math.ceil(0.9 * len(es)) - 1] for es in by_horizon]
    for origin in audit:
        predicted = _predict(values[:origin], horizon, winner)
        for h, (p, y) in enumerate(zip(predicted, values[origin : origin + horizon], strict=True)):
            error = p - y
            audit_errors.append(error)
            covered += abs(error) <= widths[h]
    forecast = _predict(values, horizon, winner)
    return {
        "status": "estimated",
        "method": winner,
        "selection_origins": len(selection),
        "audit_origins": len(audit),
        "selection_last_target_index": selection[-1] + horizon - 1,
        "audit_first_target_index": audit[0],
        "selection_mae": {k: exact(v) for k, v in candidates.items()},
        "audit_mae": exact(Fraction(sum(abs(e) for e in audit_errors), len(audit_errors))),
        "audit_bias": exact(Fraction(sum(audit_errors), len(audit_errors))),
        "audit_band_coverage": exact(Fraction(covered, len(audit_errors))),
        "interval_method": "90th_percentile_selection_absolute_error_by_horizon",
        "forecast": [
            {
                "horizon_day": i + 1,
                "point": p,
                "lower": max(0, p - widths[i]),
                "upper": p + widths[i],
            }
            for i, p in enumerate(forecast)
        ],
        "limitations": [
            "Bands summarize selection-period errors; future coverage is not guaranteed.",
            "Audit errors are chronological and overlapping, not independent trials.",
            "No structural-break, holiday or causal response model is claimed.",
        ],
    }


def report(warehouse, observations, *, metric="orders", horizon=7, cutoff=None):
    if type(horizon) is not int or not 1 <= horizon <= 14:
        raise ValueError("horizon must be an integer from 1 to 14")
    if metric not in ("orders", "sessions", "revenue"):
        raise ValueError("supported forecast metrics: orders, sessions, revenue")
    source = Path(observations)
    with open_warehouse(Path(warehouse)) as snapshot:
        payload = (source / "manifest.json").read_bytes()
        if digest(payload) != snapshot.manifest_sha256:
            raise ValueError("observations do not match warehouse")
        manifest = json.loads(payload)
        cutoff = snapshot.end if cutoff is None else cutoff
        if type(cutoff) is not date or not snapshot.start < cutoff <= snapshot.end:
            raise ValueError("forecast cutoff outside snapshot")
        if cutoff > datetime.now(BUSINESS_ZONE).date():
            raise ValueError("forecast cutoff is in future")
        contract = manifest.get("forecast_contract")
        if contract != {
            "version": "1",
            "daily_coverage_complete": True,
            "coverage_end_exclusive": snapshot.end.isoformat(),
        }:
            analysis = {"status": "not_assessed", "reason": "complete_daily_coverage_not_declared"}
        else:
            # Canonical SQL facts; no generator or metric alias inference.
            sql = files("nemo").joinpath("forecast_daily.sql").read_text()
            rows = snapshot.connection.execute(sql, [snapshot.start, cutoff]).fetchall()
            column = {"sessions": 1, "orders": 2, "revenue": 3}[metric]
            analysis = backtest([int(row[column]) for row in rows], horizon)
            if analysis["status"] == "estimated":
                for point in analysis["forecast"]:
                    point["business_date"] = (
                        cutoff + timedelta(days=point["horizon_day"] - 1)
                    ).isoformat()
        result = {
            "schema_version": "1",
            "claim_type": "predictive_estimate",
            "scope": {
                "dataset_id": snapshot.contract.dataset_id,
                "mode": snapshot.contract.mode,
                "metric": metric,
                "start": snapshot.start.isoformat(),
                "cutoff_exclusive": cutoff.isoformat(),
                "horizon_days": horizon,
            },
            "unit": "tax_exclusive_merchandise_paise" if metric == "revenue" else "count",
            "analysis": analysis,
            "contract": contract,
            "metric_definition": next(m.definition() for m in REGISTRY if m.name == metric),
            "provenance": {
                "manifest_sha256": snapshot.manifest_sha256,
                "code_sha256": digest(files("nemo").joinpath("forecasting.py").read_bytes()),
                "sql_sha256": digest(files("nemo").joinpath("forecast_daily.sql").read_bytes()),
            },
            "limitations": [
                "Coverage is a source assertion, not an external audit.",
                "Merchandise receipt forecasts are not profit forecasts.",
            ],
        }
        result["revision_id"] = digest(encode(result))
        return json.loads(encode(result))


def scenario(baseline, changes):
    """Exact rational scenario from explicitly supplied observed totals; no causal claim."""
    required = {
        "spend_paise",
        "clicks",
        "sessions",
        "purchasing_sessions",
        "orders",
        "merchandise_receipts_paise",
        "source_reference",
    }
    if not isinstance(baseline, dict) or set(baseline) != required:
        raise ValueError("scenario requires exact baseline fields")
    if (
        not isinstance(baseline["source_reference"], str)
        or not baseline["source_reference"].strip()
    ):
        raise ValueError("source_reference required")
    for k in required - {"source_reference"}:
        if type(baseline[k]) is not int or baseline[k] <= 0:
            raise ValueError("scenario baseline totals must be positive integers")
    if (
        baseline["purchasing_sessions"] > baseline["sessions"]
        or baseline["purchasing_sessions"] > baseline["orders"]
    ):
        raise ValueError("inconsistent purchasing-session counts")
    if not isinstance(changes, dict) or set(changes) - {
        "spend_multiplier",
        "cpc_multiplier",
        "cvr_multiplier",
    }:
        raise ValueError("unsupported scenario changes")
    factors = {}
    for key in ("spend_multiplier", "cpc_multiplier", "cvr_multiplier"):
        raw = changes.get(key, {"numerator": 1, "denominator": 1})
        if (
            not isinstance(raw, dict)
            or set(raw) != {"numerator", "denominator"}
            or any(type(raw[k]) is not int or raw[k] <= 0 for k in raw)
        ):
            raise ValueError("multipliers must be positive exact fractions")
        factors[key] = Fraction(raw["numerator"], raw["denominator"])
    b = baseline
    cpc = Fraction(b["spend_paise"], b["clicks"]) * factors["cpc_multiplier"]
    spend = b["spend_paise"] * factors["spend_multiplier"]
    cvr = Fraction(b["purchasing_sessions"], b["sessions"]) * factors["cvr_multiplier"]
    if cvr > 1:
        raise ValueError("scenario conversion probability exceeds one")
    clicks = spend / cpc
    sessions = clicks * Fraction(b["sessions"], b["clicks"])
    orders = sessions * cvr * Fraction(b["orders"], b["purchasing_sessions"])
    receipts = orders * Fraction(b["merchandise_receipts_paise"], b["orders"])
    result = {
        "schema_version": "1",
        "claim_type": "conditional_scenario",
        "baseline": baseline,
        "changes": changes,
        "estimates": {
            k: exact(v)
            for k, v in {
                "spend_paise": spend,
                "clicks": clicks,
                "sessions": sessions,
                "orders": orders,
                "merchandise_receipts_paise": receipts,
            }.items()
        },
        "assumptions": [
            "Fixed landing sessions per click, orders per purchasing session and order value.",
            "Supplied multipliers are assumptions, not estimated intervention effects.",
            "No auction, mix, refund, cost or saturation response is modelled.",
        ],
        "incremental_profit_paise": None,
        "provenance": {
            "code_sha256": digest(files("nemo").joinpath("forecasting.py").read_bytes()),
            "baseline_status": "caller_supplied_observed_totals_not_independently_verified",
        },
    }
    result["revision_id"] = digest(encode(result))
    return json.loads(encode(result))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--metric", choices=("orders", "sessions", "revenue"), default="orders")
    parser.add_argument("--horizon", type=int, default=7)
    parser.add_argument("--cutoff", type=date.fromisoformat)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = report(
            args.warehouse,
            args.observations,
            metric=args.metric,
            horizon=args.horizon,
            cutoff=args.cutoff,
        )
        with args.output.open("xb") as stream:
            stream.write(encode(result))
        return 0
    except (ValueError, TypeError, KeyError, OSError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
