# Learning guide — evidence-driven opportunities

## Meaning
An opportunity is a structured next step supported by analytical evidence. It is
not an executed decision, guaranteed gain or instruction to spend money.

## Business purpose
Move from a collection of reports to a review queue: resolve measurement problems,
investigate a diagnostic hypothesis, review a completed experiment, or design a better
test. A healthy control should not generate invented work.

## Example
A Decision Case observes a conversion decline consistent with payment-stage deterioration.
An INVESTIGATE opportunity links that case, its observed decline and device evidence,
and recommends inspecting payment errors. It does not claim a deployment caused the
decline or calculate recoverable profit.

An experiment may estimate capped contribution in its treated cohort. That historical
estimate is retained separately; the value of a future rollout remains unknown.

## Rules and ranking
Only implemented evidence rules generate candidates. Their review priorities are:
10 measurement/experiment-readiness repair; 20 experiment harm review;
30 diagnostic investigation; 40 experiment benefit/guardrail review;
50 attribution-sensitivity research; 60 additional experiment design after inconclusive evidence.
Sort by (blocked last, priority ascending, opportunity_id ascending).

These numbers are ordering labels, not arithmetic utilities. No confidence × value ÷
effort score is calculated because those quantities are not calibrated or estimated.
Attribution research triggers only when a channel's model range meets a declared
minimum, default 100000 paise (INR 1000). This is a review threshold, not significance
or expected economic value.

## Data requirements
Ready canonical observations/warehouse and existing M4 integrity, M5 Decision Case,
M9 attribution or M10 experiment contracts. The engine recomputes requested analyses;
it does not accept arbitrary recommendation JSON or private simulation parameters.
All analyses must bind to the same canonical snapshot.

## Implementation
nemo.opportunities maps existing evidence to versioned candidate rules. Each opportunity
has a stable identity and evidence references, plus a report revision that changes with
the inputs, policy or method. Existing payment and attribution gates are preserved.
An experiment uses its own order-based readiness contract, not an unrelated event gate.
Missing optional events alone do not block order-based experiments.

The report provides type, business question, evidence strength, confidence basis,
unknown forward value/range, unassessed risk/effort, next step, affected metrics,
Decision Case link and proposed/blocked status. A proposed item is eligible for manual
review only. It never changes source data, assigns an owner or executes a treatment.

## Failure modes
Attribution is not causal evidence. Diagnostic hypotheses are not verified root causes.
A significant experiment is not proof of profitable scale. Historical capped economics
cannot be silently extrapolated into a forward value estimate. Missing evidence stays
visible, and suppressed candidates cannot become eligible through ranking.
Snapshot corrections can change revisions; the queue has no live freshness certification.
Synthetic worlds remain labelled synthetic. Content hashes prove binding, not truth.

## Interview explanation
"I converted analytical evidence into bounded, auditable review items, retained upstream
gates and uncertainty, and used deterministic prioritization instead of invented ROI.
Stable IDs separate the continuing business question from changing evidence revisions.
Tests prove healthy controls stay quiet and missing prerequisites block downstream action."

## Practice
Follow [the walkthrough](opportunity-engine.md). Compare healthy, tracking-loss and
payment-decline cases, then a positive, inconclusive and allocation-failed experiment.
Explain why a positive experiment's historical value is not the opportunity's forward value.
