# Outcome Measurement — M13 contract

Outcome measurement and package checks run in the approved Ubuntu WSL environment
with Python 3.12.13 and locked dependencies. Windows Smart App Control still blocks
the local Windows DuckDB extension; no Windows security policy was changed.

## Scope

M13 adds descriptive comparison of observed results with a declared target after an
implemented decision's window. It does not calculate causal lift, attributed revenue,
CAC, profit or contribution growth. Narrative expectations remain narrative; no parser
converts them into numeric claims.

Supported metrics reuse the existing registry unchanged:

| Metric | Exact value | Unit / boundary |
|---|---|---|
| sessions | observed session count | count, session-start business-date window |
| orders | paid order count | count, payment business-date window |
| revenue | paid merchandise receipts | integer INR paise, before refunds and costs |
| cvr | purchasing sessions / sessions | fraction, session cohort observed by window end |

Zero CVR denominator remains unknown. Ratios compare exact fractions, not rounded
display strings. Difference from expectation is actual minus target, in the metric's
unit. A CVR difference of 1/100 is one percentage point, not relative lift.

## Plan before work starts

Use the ledger's normal import and acceptance flow. Acceptance already requires an owner,
narrative expectation and observation window. Then submit a plan_outcome command while
the decision is accepted, before moving to in_progress. The command below is a template;
replace its decision ID and expected version with a current ledger read.

~~~json
{
  "operation": "plan_outcome",
  "request_id": "decision-plan-1",
  "actor": "marketing analyst",
  "rationale": "Declare the observed session conversion target before starting work.",
  "decision_id": "REPLACE_WITH_DECISION_ID",
  "expected_version": 2,
  "plan": {
    "version": "1",
    "metric": "cvr",
    "filters": {"channel": null, "device": null, "campaign_id": null},
    "comparator": "at_least",
    "target": {"numerator": 1, "denominator": 5}
  }
}
~~~

Use at_least or at_most. Count and paise targets must be whole numbers; CVR targets
must be between zero and one. All three dimension filter keys are explicit; null means
all values. Select the population deliberately; a dataset-wide target is not a device
or campaign target.

The existing measurement_window must align with Asia/Kolkata midnight, expressed in
UTC. For example, January 2 through January 8 inclusive uses start
2025-01-01T18:30:00Z and end 2025-01-08T18:30:00Z. Arbitrary partial-day windows are
unsupported because existing acquisition semantics use business days.

Planning freezes the window. Target/metric/filter amendments are audit events allowed
only while accepted; starting work freezes them. Narrative ownership/expectations still
follow the M12 lifecycle. Plan recording time determines the prospective/retrospective
label; registering a plan for historical observations never becomes preregistration.

Old M12 decisions replay unchanged. Already implemented decisions lacking a plan cannot
have one backfilled; their outcome reports are unresolved with missing_outcome_plan.
This avoids inventing targets after seeing results.

## Measure, review, record

After reporting implementation through the ledger, run:

~~~powershell
.venv/Scripts/python.exe -m nemo.outcomes --database artifacts/my-ledger.sqlite measure --decision-id REPLACE_WITH_DECISION_ID --warehouse artifacts/my-warehouse.duckdb --observations artifacts/my-source/observations --output artifacts/outcome-report.json
.venv/Scripts/python.exe -m nemo.outcomes --database artifacts/my-ledger.sqlite record --report artifacts/outcome-report.json --request-id outcome-1 --actor "marketing analyst" --rationale "Record the descriptive comparison and its limitations."
~~~

The output file must not already exist. Measurement itself does not modify the ledger.
Record uses the saved report so identical request retries are stable. Do not recompute a
different report and reuse the request ID. New measurements require new request IDs and
the current decision version.

The Python APIs are outcomes.report(database, decision_id, warehouse, observations) and
outcomes.record(database, result, actor=..., rationale=..., request_id=...).

## Readiness and provenance

The report checks implemented status, declared plan, elapsed wall-clock window, source
coverage and reported action occurrence at or before the window starts. Unmet prerequisites
produce not_ready, null outcomes/differences and a lesson explaining that comparison
remains unresolved. Nonimplemented decisions can be previewed but cannot record outcomes.

A ready warehouse and matching checksummed canonical observations are required. Dataset
ID and source mode must match the original decision; the manifest may change as new data
arrives. This identity is declared, not independently authenticated. Legacy synthetic
snapshots share an ID, so it is not a guarantee that two worlds have matching lineage.

The report preserves the complete acquisition measurement, its metric metadata,
measurement-health assessment and source/method fingerprints. Known scope mismatches fail.
Coverage means the public snapshot declares the window; it cannot prove every real event
was captured. A low/not_assessed health label is retained: observed target attainment
must not be presented as a validated real-world business result.

## Ledger effects and lessons

record_outcome is separate from ordinary terminal-state updates. It appends evidence
without reopening the decision, editing its original recommendation or changing its plan.
The report binds the exact decision version and state hash. Replay re-derives its claims;
stale, altered or future-dated reports fail. Earlier measurement events remain available
when a newer snapshot revises the latest observed result.

actual_outcome contains metric, unit and exact value. difference_from_expectation contains
the signed exact difference. outcome_report preserves source evidence and the comparison.
lesson is a descriptive statement: observed target met, observed target missed, or
unresolved, with planning timing and health limitations. None establishes the action's
causal effect. Lessons require context review; automated reuse is M14 work.

Hashes bind content, not truth or author identity. Actors and reported actions remain
human assertions. Source report imports are not an authenticated execution service.
Metric definitions/reducers are versioned contracts; future changes must preserve replay
semantics rather than silently reinterpret old events.

## Validated Ubuntu environment

The same APIs and data contracts run in Linux. On this workstation, enter Ubuntu and
the repository, then use the isolated environment already provisioned under .tools.
All paths below are relative to /mnt/d/projects/Projects/nemo:

~~~bash
.tools/linux-validation/venv/bin/python -m pytest --tb=short
.tools/linux-validation/venv/bin/ruff check .
.tools/linux-validation/venv/bin/ruff format --check .
.tools/linux-validation/bin/uv build --offline --python .tools/linux-validation/venv/bin/python --cache-dir .tools/linux-validation/cache
~~~

For the measure/record commands above, replace .venv/Scripts/python.exe with
.tools/linux-validation/venv/bin/python. A new Linux setup with uv can install the
same lockfile using UV_PROJECT_ENVIRONMENT=.tools/linux-validation/venv uv sync
--locked --python 3.12.13. Local runtimes and generated artifacts stay outside Git.

The six local demonstration ledgers and saved outcome reports are indexed under
artifacts/milestone-13/index.json. Each scenario is a separate hypothetical history:
target met, target missed, merchandise receipts, no plan, uncovered window and an
action reported after the observation window started. All are retrospective demos,
not evidence of real deployments or business improvement.
