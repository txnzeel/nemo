# NEMO product contract and architecture decisions

Status: Milestone 0 design, retained during Milestone 1. This document describes
future boundaries as decisions, not implemented capabilities.

NEMO turns fragmented growth data into auditable Decision Cases: verify measurement,
identify changes, separate facts from hypotheses, recommend proportionate actions,
and record outcomes. The first business is a fictional Indian direct-to-consumer
home-and-personal-care retailer. Tagline: From fragmented signals to measurable decisions.

## Architecture decisions

1. Start with a modular Python application, not microservices.
2. Make Decision Cases the analytical output, with source and method provenance.
3. Separate measurement health, evidence basis, and estimate uncertainty. No arbitrary
   confidence percentages. Health is HEALTHY, DEGRADED, BLOCKED, or UNKNOWN per dependency.
4. Keep private scenario configuration and ground truth outside analytics inputs.
   Observations alone enter analytics; the evaluator joins sealed predictions to truth.
5. Python owns generation and statistical/decision methods. SQL/dbt will own warehouse
   transformations. Do not duplicate warehouse metric calculations in Python.
6. Keep a credential-free local execution path. DuckDB/dbt is proposed for local
   warehouse work and Snowflake/dbt for connected work; verify each adapter separately.
7. Retain decisions, actions, expectations, outcomes, and lessons as structured history.
8. Add AI explanations after validated evidence packages exist.

Evidence bases: hypothesis, single-source observation, corroborated observation,
adjusted observational analysis, quasi-experimental design, randomized experiment.
Assess validity, precision, applicability, and source independence separately. Claim
types are descriptive, diagnostic, causal, or predictive. An observational diagnosis
does not establish a causal deployment failure.

## Future domain contracts

A Decision Case contains identity/version/mode; question; analysis cutoff and comparison
windows; metric definitions and scope; observed values and denominators; measurement
assessment; evidence and contradictions; facts, supported contributors and hypotheses;
impact and assumptions; recommendation and prerequisites; owner/status; input, method,
and code versions; related experiments and ledger entries. Unknown values stay null.
Identical runs must not duplicate cases. Revisions retain evidence history.

A Decision Ledger entry links the case version to evidence available at decision time,
chosen and recommended actions, owner, execution time, expected outcome, assumptions,
predefined measurement window and method, actual outcome, uncertainty, difference from
expectation, and a qualified lesson. Observed recovery is not automatically causal uplift.

## First vertical slice (Milestones 1–6)

Distinguish real Android payment deterioration from broken purchase tracking, produce
an auditable investigation case, and evaluate it against isolated ground truth and
healthy/noisy controls. Avoid attribution, optimization, AI, and a web UI until their
milestones. GA4 reporting aggregates alone cannot reconstruct individual journeys;
connected journey work needs event-level data and appropriate identity limitations.

Blind Lab will use separate development/calibration/held-out worlds, historical data
cutoffs, sealed predictions, false-positive controls, localization and detection-delay
scores, and explicit synthetic-to-real limitations. Milestone 1 implements the healthy
business core only: no planted incident, evaluator, or analytics engine exists yet.
