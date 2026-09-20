# Opportunity Engine contracts and walkthrough

M11 turns existing analytical evidence into bounded, auditable manual-review items.
Read [the learning guide](learning-opportunities.md) first.

## Source boundary
The API is nemo.opportunities.report(warehouse, observations, baseline_start=None,
current_start=None, experiment_plan=None, include_attribution=False,
minimum_attribution_range_paise=100000).

It validates the supplied canonical manifest against the ready warehouse, then recomputes
M4 measurement assessment and any requested M5, M9 or M10 analyses. Every upstream report
must bind to that same manifest. A final manifest check rejects a source change during
construction. No arbitrary external recommendation JSON, generator internals, seed,
private truth or source-provider object is accepted.

The engine does not modify existing canonical contracts or upstream metric semantics.
A future production adapter continues to normalize into those contracts. Source mode
and dataset ID remain visible on the queue.

## Opportunity schema, version 1
Every opportunity carries the requested product fields:
opportunity_id, type, title, business_question, evidence, evidence_strength,
estimated_value, value_range, confidence, risk, effort, recommended_next_step,
affected_metrics, decision_case_id and status.

Additional fields include rule, historical_effect, review_priority, rank, blockers and
execution. Every item is manual_review_only. Status is proposed or blocked, not executed,
approved, successful or assigned. Decision ownership/action tracking belongs to M12.

estimated_value and value_range remain null because forward impact is not estimated.
Risk and effort are explicitly unassessed. Confidence describes an evidence basis and has
no calibrated probability. A completed experiment's capped contribution estimate may
appear under historical_effect, with its original scope, bounds and cost provenance;
it never populates forward value. No historical result is extrapolated to profitable scale.

## Implemented rules
| Evidence | Opportunity | Bound on next step |
|---|---|---|
| Purchase discrepancies, or unassessed purchase/payment tracking needed for diagnosis | MEASUREMENT | Reconcile orders/events and verify contracts |
| Supported payment hypothesis or unexplained conversion decline | INVESTIGATE | Inspect the evidence and competing explanations |
| Insufficient diagnostic cohorts | MEASUREMENT | Collect comparable observations |
| Experiment fails readiness | MEASUREMENT | Resolve assignment/coverage/sample/follow-up prerequisites |
| Experiment indicates harm | INVESTIGATE | Owner review of harm and containment |
| Positive experiment or unresolved benefit guardrails | INVESTIGATE | Review delivery, population, guardrails and rollout costs |
| Inconclusive experiment | EXPERIMENT | Decide whether a separately registered follow-up is worthwhile |
| Attribution model range reaches the declared threshold | EXPERIMENT | Review sensitivity and consider a controlled study, subject to gates |

Healthy diagnostic controls produce no item. Missing optional events alone do not create
an obstacle for an order-based experiment. Silence only means no implemented rule fired;
it is not proof that the business has no opportunities.

SCALE, REDUCE, RETAIN, REACTIVATE, CROSS_SELL, SEO and CREATIVE are not fabricated to fill
a category list. They require additional validated decision contracts and evidence.

## Eligibility and ranking
M5 payment-investigation eligibility and suppression reasons are retained. M9 disagreement
uses the existing M4 attribution gate; the current attribution_contract prerequisite
remains unassessed. Such a research candidate is therefore blocked, even though model
credit can be calculated. This milestone does not silently unlock old gates.

M10 opportunities inherit experiment readiness and conditional causal scope. The
experiment's own order-based checks are not replaced by an unrelated event-tracking gate.
An experiment that fails readiness never supplies historical incremental value.

Sort order is (blocked last, review_priority ascending, stable opportunity_id ascending).
Priorities are: 10 measurement/readiness, 20 harm, 30 diagnosis, 40 experiment benefit
review, 50 attribution research, 60 further evidence after an inconclusive experiment.
These are explicit review-order policy choices, not profit estimates or weighted scores.

Attribution sensitivity uses channel model range in integer paise. Default minimum is
100000 paise (INR 1000). The threshold is user-configurable and is not a statistical
significance test or a claimed economic loss. The comparison does not imply causation.

## Identity, revisions and evidence
Stable opportunity IDs bind dataset, rule and business subject; changing evidence can
produce a new report revision while preserving that opportunity ID. Report revisions
bind parameters, source snapshot, upstream analytical hashes, policy and method hash.
Canonical source IDs must remain stable and correctly scoped by ingestion.

The evidence object includes the upstream claim type and report hash, plus the relevant
finding, comparisons, alternatives, guardrails, readiness or channel differences.
Decision Case references retain case_id and revision_id. Reports can be regenerated from
the pinned inputs and parameters; hashes bind content, not truth or source completeness.

save_report verifies the revision and writes immutable content-addressed JSON. Identical
replay is a no-op; changed content produces another revision. This is not a decision
ledger and does not execute actions, write to advertising accounts or notify staff.

## Run a diagnostic queue
```powershell
.venv/Scripts/python.exe -m nemo.opportunities --warehouse artifacts/milestone-5/business/nemo.duckdb --observations artifacts/milestone-5/business/observations --baseline-start 2026-06-03 --current-start 2026-06-17 --output-directory artifacts/opportunity-demo/payment
```

Both diagnostic dates are required together, with the existing M5 equal-window semantics.
The source end is the analysis cutoff. Omit both dates when a diagnostic case is not needed.

## Run an experiment review queue
```powershell
.venv/Scripts/python.exe -m nemo.opportunities --warehouse artifacts/milestone-10/effect/verified.duckdb --observations artifacts/milestone-10/effect/observations --experiment-plan artifacts/milestone-10/effect/plan.json --output-directory artifacts/opportunity-demo/experiment
```

Use no_effect or allocation_mismatch with the corresponding warehouse and plan to see
inconclusive-evidence and readiness opportunities. Diagnostic dates and an experiment
plan may be combined only when both analyses refer to the same supplied snapshot.

## Inspect attribution disagreement
```powershell
.venv/Scripts/python.exe -m nemo.opportunities --warehouse artifacts/milestone-5/healthy/nemo.duckdb --observations artifacts/milestone-5/healthy/observations --include-attribution --minimum-attribution-range-paise 100000 --output-directory artifacts/opportunity-demo/attribution
```
The generated research candidate remains blocked under the current attribution gate.
Review its reasons; do not treat a review priority as permission to reallocate budget.

## Limitations
This is a deterministic rule layer, not a learned opportunity detector, forecast,
optimizer or calibrated value-of-information system. It does not independently certify
freshness, randomization, source completeness or causal root causes. Synthetic mode stays
labelled; hypothetical costs do not become observed economics. Future decision tracking,
execution and measured outcomes remain separate milestones.
