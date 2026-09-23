"""Version-one descriptive outcome plans and replayable report validation."""

from datetime import datetime
from fractions import Fraction
from zoneinfo import ZoneInfo

from nemo.experiment_design import digest, encode
from nemo.metrics import REGISTRY

SUPPORTED = {m.name: m for m in REGISTRY if m.name in {"sessions", "orders", "revenue", "cvr"}}


def utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError("explicit UTC timestamp required")
    return result


def fraction(value):
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        raise ValueError("target requires exact numerator and denominator")
    if any(type(value[k]) is not int for k in value) or value["denominator"] <= 0:
        raise ValueError("fraction requires integer numerator and positive denominator")
    return Fraction(value["numerator"], value["denominator"])


def ratio(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def business_window(window):
    bounds = []
    for key in ("start_inclusive", "end_exclusive"):
        local = utc(window[key]).astimezone(ZoneInfo("Asia/Kolkata"))
        if any((local.hour, local.minute, local.second, local.microsecond)):
            raise ValueError("outcome window must align with Asia/Kolkata midnight")
        bounds.append(local.date())
    if bounds[0] >= bounds[1]:
        raise ValueError("outcome window must be nonempty")
    return bounds


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {
        "version",
        "metric",
        "filters",
        "comparator",
        "target",
    }:
        raise ValueError("invalid outcome plan fields")
    if plan["version"] != "1" or plan["metric"] not in SUPPORTED:
        raise ValueError("unsupported outcome metric or version")
    if plan["comparator"] not in {"at_least", "at_most"}:
        raise ValueError("unsupported target comparator")
    filters = plan["filters"]
    if not isinstance(filters, dict) or set(filters) != {"channel", "device", "campaign_id"}:
        raise ValueError("explicit channel, device and campaign filters required")
    if any(v is not None and (not isinstance(v, str) or not v.strip()) for v in filters.values()):
        raise ValueError("filters must be nonempty text or null")
    target = fraction(plan["target"])
    if target < 0 or (plan["metric"] == "cvr" and target > 1):
        raise ValueError("target is outside metric domain")
    if plan["metric"] != "cvr" and target.denominator != 1:
        raise ValueError("count and paise targets must be integers")
    return plan


def readiness(state, source, measured_at):
    """Return explicit blockers before any warehouse measurement is requested."""
    moment = utc(measured_at)
    board_scope = state["evidence_available"]["scope"]
    if (
        source["dataset_id"] != board_scope["dataset_id"]
        or source["mode"] != board_scope["source_mode"]
    ):
        raise ValueError("outcome source does not match decision dataset and mode")
    blockers = []
    plan = state.get("outcome_plan")
    window = state["measurement_window"]
    if state["status"] != "implemented":
        blockers.append("decision_not_implemented")
    if plan is None:
        blockers.append("missing_outcome_plan")
    if window is None:
        blockers.append("missing_measurement_window")
    if window and utc(window["end_exclusive"]) > moment:
        blockers.append("window_not_elapsed")
    if (
        window
        and state["actual_action"]
        and utc(state["actual_action"]["occurred_at"]) > utc(window["start_inclusive"])
    ):
        blockers.append("window_precedes_reported_action")
    dates = None
    if plan is not None:
        validate_plan(plan["spec"])
        dates = business_window(window)
        if encode(plan["metric_definition"]) != encode(
            SUPPORTED[plan["spec"]["metric"]].definition()
        ):
            raise ValueError("metric definition changed since planning")
        if not (
            source["start_inclusive"]
            <= dates[0].isoformat()
            < dates[1].isoformat()
            <= source["end_exclusive"]
        ):
            blockers.append("source_does_not_cover_window")
    return blockers, dates


def build_result(state, source, evidence, measured_at, code_sha256):
    """Derive all outcome claims from explicit evidence; used again during ledger replay."""
    blockers, dates = readiness(state, source, measured_at)
    plan = state.get("outcome_plan")
    window = state["measurement_window"]
    actual, difference = None, None
    comparison = "unresolved"
    if not blockers:
        if evidence is None:
            raise ValueError("eligible outcome requires measurement evidence")
        spec = plan["spec"]
        metric = SUPPORTED[spec["metric"]]
        expected_window = {
            "start_inclusive": dates[0].isoformat(),
            "end_exclusive": dates[1].isoformat(),
        }
        if (
            evidence["window"] != expected_window
            or evidence["filters"] != spec["filters"]
            or evidence["dataset_id"] != source["dataset_id"]
            or evidence["mode"] != source["mode"]
            or evidence["provenance"]["manifest_sha256"] != source["manifest_sha256"]
        ):
            raise ValueError("measurement evidence does not match outcome scope")
        facts = evidence["total"]["facts"]
        for key in (metric.numerator, metric.denominator):
            if key and (type(facts[key]) is not int or facts[key] < 0):
                raise ValueError("metric evidence requires nonnegative integer facts")
        result = metric.evaluate(facts)
        if result != evidence["total"]["metrics"][spec["metric"]]:
            raise ValueError("metric evidence arithmetic mismatch")
        if result["reason"] is not None:
            blockers.append(result["reason"])
        else:
            actual_value = Fraction(result["numerator"], result["denominator"] or 1)
            actual = {"metric": spec["metric"], "unit": metric.unit, "value": ratio(actual_value)}
            target = fraction(spec["target"])
            difference = {"unit": metric.unit, "value": ratio(actual_value - target)}
            met = (
                actual_value >= target
                if spec["comparator"] == "at_least"
                else actual_value <= target
            )
            comparison = "observed_target_met" if met else "observed_target_missed"
    elif evidence is not None:
        raise ValueError("ineligible report cannot include measured outcome evidence")
    timing = (
        "prospective"
        if plan is not None and utc(plan["recorded_at"]) < utc(window["start_inclusive"])
        else "retrospective_or_unplanned"
    )
    lesson = {
        "claim_type": "descriptive_lesson",
        "finding": comparison,
        "text": (
            "Observed results meet the planned target; the action's causal effect is unestablished."
            if comparison == "observed_target_met"
            else "Observed results miss the target; the cause remains unestablished."
            if comparison == "observed_target_missed"
            else "Evidence is insufficient for the planned comparison; resolve the listed blockers."
        ),
        "planning_timing": timing,
        "causal_effect": "not_established",
        "measurement_health": evidence["measurement_health"] if evidence else "not_assessed",
        "reuse": "requires_context_review",
    }
    result = {
        "schema_version": "1",
        "claim_type": "descriptive_outcome",
        "decision_id": state["decision_id"],
        "decision_version": state["version"],
        "decision_sha256": digest(encode(state)),
        "measured_at": measured_at,
        "source": source,
        "measurement_evidence": evidence,
        "status": "not_ready" if blockers else "measured",
        "blockers": blockers,
        "actual_outcome": actual,
        "difference_from_expectation": difference,
        "target_assessment": comparison,
        "lesson": lesson,
        "provenance": {"code_sha256": code_sha256},
        "limitations": [
            "Observed target attainment is not causal effectiveness or incremental lift.",
            "Snapshot coverage and human action records are assertions, not independent proof.",
            "Retrospective targets are not experimental preregistration.",
            "Measurement health and metric limitations remain in the source report.",
            "Merchandise receipts exclude refunds and costs and are not profit.",
        ],
    }
    result["revision_id"] = digest(encode(result))
    return result


def validate_result(state, result, recorded_at):
    if utc(result["measured_at"]) < utc(state["updated_at"]):
        raise ValueError("outcome measurement predates its decision state")
    if utc(result["measured_at"]) > utc(recorded_at):
        raise ValueError("outcome measurement cannot be recorded before it was computed")
    expected = build_result(
        state,
        result["source"],
        result["measurement_evidence"],
        result["measured_at"],
        result["provenance"]["code_sha256"],
    )
    if encode(expected) != encode(result):
        raise ValueError("outcome report does not match decision or derived claims")
