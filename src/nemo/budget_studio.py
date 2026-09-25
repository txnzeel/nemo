"""Exact-grid, scenario-only allocation over separable concave response models."""

import argparse
import heapq
import json
import sys
from fractions import Fraction
from importlib.resources import files
from pathlib import Path

from nemo.experiment_design import digest, encode
from nemo.forecasting import exact
from nemo.observations import _integer
from nemo.response_curves import evaluate


def _value(model, spend):
    a, b = Fraction(str(model["a_paise"])), Fraction(str(model["b_paise"]))
    return a * spend / (b + spend)


def _solve(models, bounds, budget, step, scales=None):
    scales = scales or {}
    values = {key: low for key, (low, _) in bounds.items()}
    remaining = budget - sum(values.values())
    if remaining < 0 or remaining > sum(high - values[k] for k, (_, high) in bounds.items()):
        raise ValueError("infeasible budget within effective constraints")
    queue = []

    def push(key):
        current = values[key]
        if current + step <= bounds[key][1]:
            gain = (
                _value(models[key], current + step) - _value(models[key], current)
            ) * scales.get(key, Fraction(1))
            heapq.heappush(queue, (-gain, key))

    for key in sorted(values):
        push(key)
    for _ in range(remaining // step):
        if not queue:
            raise ValueError("infeasible remaining budget")
        _, key = heapq.heappop(queue)
        values[key] += step
        push(key)
    return values


def _estimate(values, models):
    gross = sum((_value(models[k], v) for k, v in values.items()), Fraction(0))
    width = sum((Fraction(str(models[k]["error_half_width_paise"])) for k in values), Fraction(0))
    net = gross - sum(values.values())
    return {
        "modelled_contribution_before_media_paise": exact(gross),
        "modelled_channels_net_contribution_paise": exact(net),
        "stress_lower_net_paise": exact(net - width),
        "stress_upper_net_paise": exact(net + width),
        "uncertainty": "sum_of_empirical_error_widths_not_joint_confidence_interval",
    }


def allocate(response, spec):
    if not isinstance(response, dict):
        raise ValueError("response evidence must be an object")
    if response.get("claim_type") != "observational_response_analysis" or response.get(
        "revision_id"
    ) != digest(encode({k: v for k, v in response.items() if k != "revision_id"})):
        raise ValueError("invalid response evidence revision")
    if not isinstance(spec, dict) or set(spec) != {
        "period_days",
        "total_budget_paise",
        "step_paise",
        "experiment_reserve_paise",
        "channels",
    }:
        raise ValueError("invalid budget specification fields")
    if type(spec["period_days"]) is not int or spec["period_days"] != 7:
        raise ValueError("response curves support weekly budgets only")
    total, step, reserve = (
        _integer(spec, k) for k in ("total_budget_paise", "step_paise", "experiment_reserve_paise")
    )
    if (
        not step
        or not total
        or reserve > total
        or (total - reserve) % step
        or (total - reserve) // step > 10000
    ):
        raise ValueError("invalid budget/reserve/grid or more than 10000 spend steps")
    channels = spec["channels"]
    if not isinstance(channels, list) or not 1 <= len(channels) <= 12:
        raise ValueError("budget requires 1 to 12 channels")
    rows = response.get("channels")
    if not isinstance(rows, list) or any(
        not isinstance(r, dict)
        or not isinstance(r.get("channel"), str)
        or not isinstance(r.get("curve"), dict)
        for r in rows
    ):
        raise ValueError("invalid response channels")
    available = {r["channel"]: r["curve"] for r in rows}
    if len(available) != len(response["channels"]):
        raise ValueError("duplicate response channels")
    bounds, models, current = {}, {}, {}
    for row in channels:
        if not isinstance(row, dict) or set(row) != {
            "channel",
            "current_spend_paise",
            "min_spend_paise",
            "max_spend_paise",
            "min_share_bps",
            "max_share_bps",
            "max_change_bps",
        }:
            raise ValueError("invalid channel constraints")
        key = row["channel"]
        if not isinstance(key, str) or key in models or key not in available:
            raise ValueError("unknown or duplicate channel")
        model = available[key]
        if model.get("status") != "estimated":
            raise ValueError("no eligible estimated curve")
        if (
            model.get("family") != "a_times_spend_over_b_plus_spend"
            or model.get("action_eligibility") != "scenario_only"
        ):
            raise ValueError("unsupported response family or evidence level")
        cur, low, high = (
            _integer(row, k) for k in ("current_spend_paise", "min_spend_paise", "max_spend_paise")
        )
        minimum, maximum, change = (
            _integer(row, k) for k in ("min_share_bps", "max_share_bps", "max_change_bps")
        )
        if not 0 <= minimum <= maximum <= 10000 or change > 10000 or low > high:
            raise ValueError("invalid share/change bounds")
        support = model["support_paise"]
        if (
            not isinstance(support, list)
            or len(support) != 2
            or any(type(v) is not int or v < 0 for v in support)
            or support[0] > support[1]
        ):
            raise ValueError("invalid response support")
        evaluate(model, cur)
        low = max(
            low,
            support[0],
            (total * minimum + 9999) // 10000,
            (cur * (10000 - change) + 9999) // 10000,
        )
        high = min(high, support[1], total * maximum // 10000, cur * (10000 + change) // 10000)
        low = ((low + step - 1) // step) * step
        high = (high // step) * step
        if low > high:
            raise ValueError("empty effective channel bounds")
        bounds[key] = (low, high)
        models[key] = model
        current[key] = cur
    selected = _solve(models, bounds, total - reserve, step)
    sensitivity = []
    for channel in sorted(models):
        for factor in (Fraction(4, 5), Fraction(6, 5)):
            sensitivity.append(
                {
                    "channel": channel,
                    "response_scale": exact(factor),
                    "allocation_paise": _solve(
                        models, bounds, total - reserve, step, {channel: factor}
                    ),
                }
            )
    allocation = [
        {
            "channel": k,
            "current_spend_paise": current[k],
            "selected_spend_paise": v,
            "effective_min_paise": bounds[k][0],
            "effective_max_paise": bounds[k][1],
            "binding_min": v == bounds[k][0],
            "binding_max": v == bounds[k][1],
            "marginal_response": evaluate(models[k], v)["marginal_response"],
        }
        for k, v in sorted(selected.items())
    ]
    result = {
        "schema_version": "1",
        "claim_type": "conditional_optimization_scenario",
        "action_eligibility": "controlled_review_only",
        "scope": response["scope"],
        "response_revision_id": response["revision_id"],
        "specification": spec,
        "allocation": allocation,
        "experiment_reserve_paise": reserve,
        "total_spend_paise": sum(selected.values()) + reserve,
        "current_model": _estimate(current, models),
        "selected_model": _estimate(selected, models),
        "total_expected_contribution_paise": None,
        "sensitivity": sensitivity,
        "provenance": {
            "code_sha256": digest(files("nemo").joinpath("budget_studio.py").read_bytes())
        },
        "limitations": [
            "Optimum is conditional on separable concave observational models and this spend grid.",
            "Response perturbations are sensitivity scenarios, not calibrated probabilities.",
            "No extrapolation; omitted channel interactions and demand confounding remain.",
            "Experiment reserve has unknown return and is never assigned a fabricated curve.",
            "No external execution or causal economic recommendation is authorized.",
        ],
    }
    result["revision_id"] = digest(encode(result))
    return json.loads(encode(result))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = allocate(
            json.loads(args.response.read_bytes()), json.loads(args.spec.read_bytes())
        )
        with args.output.open("xb") as stream:
            stream.write(encode(result))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
