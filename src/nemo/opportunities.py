"""Bounded opportunity discovery from recomputed canonical analytical evidence."""

import argparse
import json
import sys
from datetime import date
from importlib.resources import files
from pathlib import Path

import duckdb

from nemo.attribution import report as attribution_report
from nemo.decision_case import build_case
from nemo.experiment_design import digest, encode
from nemo.experiments import report as experiment_report
from nemo.integrity import assess, gate_recommendations
from nemo.warehouse import open_warehouse, project_hash

POLICY = {
    "version": "1",
    "ranking": "blocked_last_then_review_priority_then_stable_id",
    "priorities": {
        "measurement": 10,
        "harm": 20,
        "diagnosis": 30,
        "experiment_review": 40,
        "attribution_study": 50,
        "more_evidence": 60,
    },
    "execution": "manual_review_only",
    "forward_value": "unknown_no_extrapolation",
}


def _candidate(
    dataset,
    rule,
    subject,
    kind,
    title,
    question,
    evidence,
    strength,
    priority,
    next_step,
    metrics,
    *,
    blockers=None,
    case_id=None,
    historical=None,
):
    identity = {"dataset_id": dataset, "rule": rule, "subject": subject}
    return {
        "opportunity_id": "OP-" + digest(encode(identity))[:24],
        "rule": rule,
        "type": kind,
        "title": title,
        "business_question": question,
        "claim_type": "decision_recommendation",
        "evidence": evidence,
        "evidence_strength": strength,
        "estimated_value": None,
        "value_range": None,
        "value_basis": "forward_value_not_estimated",
        "historical_effect": historical,
        "confidence": {"basis": strength, "calibrated_probability": None},
        "risk": {
            "level": "unassessed",
            "reason": "Operational and rollout risks need owner review.",
        },
        "effort": {"status": "unestimated", "hours": None},
        "recommended_next_step": next_step,
        "affected_metrics": metrics,
        "decision_case_id": case_id,
        "status": "blocked" if blockers else "proposed",
        "blockers": blockers or [],
        "review_priority": priority,
        "execution": "manual_review_only",
    }


def _experiment_candidate(dataset, value, evidence):
    result = value["result"]
    eid = value["experiment_id"]
    primary = value["metrics"]["purchase_probability"]
    historical = None
    contribution = value["metrics"]["capped_contribution_paise"]
    if value["readiness"]["eligible"] and contribution["status"] == "assessed":
        historical = {
            "scope": "completed_experiment_treated_cohort_only",
            "metric": "capped_contribution_paise",
            "estimate": contribution["incremental_in_treated"],
            "cost_provenance": value["economics"]["cost_provenance"],
            "not_forward_opportunity_value": True,
        }
    details = {
        **evidence,
        "result": result,
        "readiness": value["readiness"],
        "primary": primary,
        "guardrails": value["guardrails"],
        "causal_scope": value["causal_scope"],
        "limitations": value["limitations"],
    }
    if not value["readiness"]["eligible"]:
        rule, kind, priority = "experiment_readiness", "MEASUREMENT", 10
        title = "Resolve experiment readiness before interpreting lift"
        step = (
            "Resolve the listed readiness failures; preserve the registered plan and cohort. "
            "Wait for fixed follow-up or repair assignment/coverage evidence as applicable. "
            "Do not extend or stop the experiment in response to observed significance."
        )
        strength = "observed_association"
    elif result == "harm_detected":
        rule, kind, priority = "experiment_harm", "INVESTIGATE", 20
        title = "Review evidence of experiment harm"
        step = (
            "Review affected outcomes and guardrails with the experiment owner; validate "
            "delivery and coverage, and assess containment. Do not execute a change automatically."
        )
        strength = "conditional_randomized_experiment"
    elif result in ("positive_with_guardrails", "benefit_guardrails_unresolved"):
        rule, kind, priority = "experiment_review", "INVESTIGATE", 40
        title = "Review experiment benefit and remaining deployment assumptions"
        step = (
            "Review randomization, treatment delivery, target population and all guardrails. "
            "Resolve unknown or inconclusive economics and estimate uncapped rollout costs "
            "before considering a separately approved rollout."
        )
        strength = "conditional_randomized_experiment"
    elif result == "inconclusive":
        rule, kind, priority = "experiment_followup", "EXPERIMENT", 60
        title = "Decide whether a separately registered follow-up is worthwhile"
        step = (
            "Review the interval, practical threshold and information needed for the decision. "
            "If further evidence is worthwhile, register a new experiment; do not reinterpret "
            "inconclusive evidence as no effect or extend the completed test opportunistically."
        )
        strength = "conditional_randomized_experiment"
    else:
        raise ValueError("unsupported experiment result")
    return _candidate(
        dataset,
        rule,
        eid,
        kind,
        title,
        value["plan"]["hypothesis"],
        details,
        strength,
        priority,
        step,
        list(value["metrics"]),
        historical=historical,
    )


def report(
    warehouse: Path,
    observations: Path,
    *,
    baseline_start=None,
    current_start=None,
    experiment_plan=None,
    include_attribution=False,
    minimum_attribution_range_paise=100000,
):
    if (baseline_start is None) != (current_start is None):
        raise ValueError("baseline_start and current_start must be supplied together")
    if type(include_attribution) is not bool:
        raise ValueError("include_attribution must be boolean")
    if type(minimum_attribution_range_paise) is not int or minimum_attribution_range_paise < 1:
        raise ValueError("minimum attribution range must be positive integer paise")
    with open_warehouse(warehouse) as snapshot:
        source_hash = snapshot.manifest_sha256
        if digest((observations / "manifest.json").read_bytes()) != source_hash:
            raise ValueError("opportunity observations do not match warehouse")
        dataset = snapshot.contract.dataset_id
        scope = {
            "dataset_id": dataset,
            "source_mode": snapshot.contract.mode,
            "start_inclusive": snapshot.start.isoformat(),
            "end_exclusive": snapshot.end.isoformat(),
        }
    candidates, analyses = [], []
    measurement = assess(observations)
    case = None
    if baseline_start is not None:
        case = build_case(
            warehouse, observations, baseline_start=baseline_start, current_start=current_start
        )
        measurement = case["measurement"]

    def reference(kind, value, bound_hash, claim):
        if bound_hash != source_hash:
            raise ValueError("analysis source changed during opportunity construction")
        item = {
            "analysis": kind,
            "sha256": digest(encode(value)),
            "manifest_sha256": bound_hash,
            "claim_type": claim,
        }
        analyses.append(item)
        return item

    mr = reference(
        "measurement", measurement, measurement["manifest_sha256"], measurement["claim_type"]
    )
    confidence = measurement["measurement_confidence"]
    if confidence == "low" or (confidence != "high" and baseline_start is not None):
        candidates.append(
            _candidate(
                dataset,
                "purchase_measurement",
                "purchase_tracking",
                "MEASUREMENT",
                "Resolve purchase measurement evidence",
                "Can purchase tracking support the requested diagnosis?",
                {
                    **mr,
                    "confidence": confidence,
                    "checks": measurement["checks"],
                    "reason": measurement.get("reason"),
                    "limitations": measurement["limitations"],
                },
                "measurement_assessment",
                10,
                "Reconcile orders and purchase events; verify coverage and identity mapping "
                "and the declared tracking contract before using dependent diagnostics.",
                ["purchase_tracking"],
                case_id=case["case_id"] if case else None,
            )
        )
    if case is not None:
        cr = reference(
            "decision_case", case, case["provenance"]["manifest_sha256"], case["claim_type"]
        )
        finding = case["finding"]
        if finding in ("payment_stage_hypothesis", "conversion_decline_unexplained"):
            blockers = []
            if finding == "payment_stage_hypothesis":
                gated = case["recommendations"]
                allowed = any(
                    c["kind"] == "payment_funnel_investigation"
                    for c in gated["measurement_eligible"]
                )
                if not allowed:
                    blockers = [
                        reason for item in gated["suppressed"] for reason in item["reasons"]
                    ]
                    blockers = blockers or ["payment_funnel_investigation:not_eligible"]
            candidates.append(
                _candidate(
                    dataset,
                    "conversion_diagnosis",
                    case["case_id"],
                    "INVESTIGATE",
                    "Investigate the observed conversion decline",
                    case["question"],
                    {
                        **cr,
                        "case_id": case["case_id"],
                        "revision_id": case["revision_id"],
                        "finding": finding,
                        "comparison": case["observations"]["comparison"],
                        "supported_devices": case["supported_devices"],
                        "alternatives": case["alternatives"],
                        "recommendation_gate": case["recommendations"],
                        "limitations": case["limitations"],
                    },
                    "observational_hypothesis",
                    30,
                    case["next_investigation"],
                    ["session_conversion_rate", "payment_success_rate"],
                    blockers=blockers,
                    case_id=case["case_id"],
                )
            )
        elif finding in ("measurement_issue", "insufficient_measurement") and confidence == "high":
            candidates.append(
                _candidate(
                    dataset,
                    "funnel_measurement",
                    case["case_id"],
                    "MEASUREMENT",
                    "Resolve payment-funnel measurement evidence",
                    case["question"],
                    {
                        **cr,
                        "finding": finding,
                        "payment_evidence": case["payment_evidence"],
                        "dependencies": measurement["dependencies"],
                        "limitations": case["limitations"],
                    },
                    "measurement_assessment",
                    10,
                    case["next_investigation"],
                    ["payment_success_rate"],
                    case_id=case["case_id"],
                )
            )
        elif finding == "insufficient_data":
            candidates.append(
                _candidate(
                    dataset,
                    "diagnostic_coverage",
                    case["case_id"],
                    "MEASUREMENT",
                    "Collect comparable cohorts before diagnosing conversion",
                    case["question"],
                    {**cr, "finding": finding, "comparison": case["observations"]["comparison"]},
                    "observed_assessment",
                    10,
                    case["next_investigation"],
                    ["session_conversion_rate"],
                    case_id=case["case_id"],
                )
            )
    if experiment_plan is not None:
        value = experiment_report(warehouse, observations, experiment_plan)
        er = reference(
            "experiment", value, value["provenance"]["manifest_sha256"], value["claim_type"]
        )
        candidates.append(_experiment_candidate(dataset, value, er))
    if include_attribution:
        value = attribution_report(warehouse)
        ar = reference(
            "attribution",
            value,
            value["provenance"]["journeys"]["manifest_sha256"],
            value["claim_type"],
        )
        differences = [
            r
            for r in value["channel_comparison"]
            if r["model_range_paise"] >= minimum_attribution_range_paise
        ]
        if differences:
            gate = gate_recommendations([{"kind": "attribution"}], measurement)
            blockers = [reason for item in gate["suppressed"] for reason in item["reasons"]]
            candidates.append(
                _candidate(
                    dataset,
                    "attribution_disagreement",
                    "channel_model_comparison",
                    "EXPERIMENT",
                    "Investigate whether attribution disagreement affects a real decision",
                    "Would a controlled incrementality study resolve the channel decision?",
                    {
                        **ar,
                        "channel_comparison": differences,
                        "threshold_paise": minimum_attribution_range_paise,
                        "recommendation_gate": gate,
                        "limitations": value["limitations"],
                    },
                    "model_dependence_not_causal",
                    50,
                    "Resolve the listed prerequisites, review the decision sensitivity, and design "
                    "a controlled study if justified. Never reallocate budget from credit alone.",
                    ["attributed_gross_merchandise_credit_paise"],
                    blockers=blockers,
                )
            )
    if digest((observations / "manifest.json").read_bytes()) != source_hash:
        raise ValueError("source changed during opportunity construction")
    candidates.sort(
        key=lambda c: (c["status"] == "blocked", c["review_priority"], c["opportunity_id"])
    )
    for rank, candidate in enumerate(candidates, 1):
        candidate["rank"] = rank
    result = {
        "schema_version": "1",
        "claim_type": "decision_recommendation",
        "scope": scope,
        "policy": POLICY,
        "parameters": {
            "baseline_start": baseline_start.isoformat() if baseline_start else None,
            "current_start": current_start.isoformat() if current_start else None,
            "include_attribution": include_attribution,
            "minimum_attribution_range_paise": minimum_attribution_range_paise,
        },
        "opportunities": candidates,
        "analyses": analyses,
        "summary": {
            "proposed": sum(c["status"] == "proposed" for c in candidates),
            "blocked": sum(c["status"] == "blocked" for c in candidates),
        },
        "provenance": {
            "manifest_sha256": source_hash,
            "dbt_project_sha256": project_hash(),
            "code_sha256": digest(files("nemo").joinpath("opportunities.py").read_bytes()),
        },
        "limitations": [
            "Proposed means manual review, never execution, rollout or spending authorization.",
            "Review priorities are policy labels, not calibrated value or probability scores.",
            "Forward value, effort and risk are unestimated; historical effects are not forecasts.",
            "Snapshot and analysis hashes bind evidence but cannot prove source assertions true.",
            "No live freshness, causal root cause, profitable scale or integration is certified.",
            "Only implemented evidence rules are covered; silence is not proof of no opportunity.",
        ],
    }
    result["revision_id"] = digest(encode(result))
    return result


def save_report(value, directory):
    unsigned = {k: v for k, v in value.items() if k != "revision_id"}
    if digest(encode(unsigned)) != value["revision_id"]:
        raise ValueError("opportunity revision does not match content")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (value["revision_id"] + ".json")
    payload = encode(value)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("existing opportunity revision differs")
    else:
        with path.open("xb") as stream:
            stream.write(payload)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEMO evidence-bound opportunity review queue")
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--baseline-start", type=date.fromisoformat)
    parser.add_argument("--current-start", type=date.fromisoformat)
    parser.add_argument("--experiment-plan", type=Path)
    parser.add_argument("--include-attribution", action="store_true")
    parser.add_argument("--minimum-attribution-range-paise", type=int, default=100000)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = report(
            args.warehouse,
            args.observations,
            baseline_start=args.baseline_start,
            current_start=args.current_start,
            experiment_plan=args.experiment_plan,
            include_attribution=args.include_attribution,
            minimum_attribution_range_paise=args.minimum_attribution_range_paise,
        )
        path = save_report(value, args.output_directory)
        print(json.dumps({"report": str(path), **value["summary"]}))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, duckdb.Error) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
