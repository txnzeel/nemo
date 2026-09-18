# Experimentation contracts and walkthrough

Read [the learning guide](learning-experiments.md) before interpreting results.
M10 supports one fixed-horizon, customer-randomized, 50/50 Bernoulli experiment at a
time. Assignment and analysis are separate. It does not deploy treatments.

## Plan version 1
A plan defines experiment_id, hypothesis, population eligibility description, treatment,
control, registered_at (UTC), start_date, end_date, randomization, allocation,
primary_metric, alpha, power, mde_absolute, practical_threshold_absolute,
gross_cap_paise, contribution_bounds_paise and guardrails.

The common outcome window is [start_date, end_date) in Asia/Kolkata; timestamps are UTC.
Registration precedes the window. All cohort assignments occur after registration and
before the window, and not before the customer's observed first_seen_at. There is no
rolling enrollment, post-treatment exclusion, per-exposure filtering or sequential test.

Primary metric is purchase_probability: assigned customers with one or more paid orders
in the window / all assigned customers. It is not order count, attributed conversions,
session conversion rate or customer acquisition. Repeat orders do not increase its numerator.

The design module validates plans and computes a conservative sample target and duration.
MDE must exceed 0.000001 and be below 1; practical threshold is a separate positive
absolute rate difference. Equal planned allocation does not guarantee equal realized arms.

## Register and assign prospectively
Prepare a JSON spec using the fields above, with future start/end dates. The registered_at
input, if supplied, is replaced with the current UTC timestamp during registration.
The historical synthetic plan generated below is a schema example, not live preregistration.

```powershell
.venv/Scripts/python.exe -m nemo.experiment_design register --plan spec.json --output registered-plan.json
.venv/Scripts/python.exe -m nemo.experiment_design plan --plan registered-plan.json
.venv/Scripts/python.exe -m nemo.experiment_design assign --plan registered-plan.json --population customer-ids.json --output assignment-ledger
```

customer-ids.json is a nonempty JSON list of unique canonical customer IDs, selected
before treatment using the stated population criteria. Assignment uses operating-system
randomness and saves the realized ledger. Reuse that ledger; do not rerandomize users
or regenerate a cohort until a desirable balance appears. Existing outputs are refused.
This is a local single-write tool, not a transactional multi-service assignment system.

The ledger contains experiment_population.jsonl, experiment_assignments.jsonl and a
receipt with plan and table hashes. The adapter copies these two public tables into the
canonical observations directory and adds their row counts and SHA-256 entries to
manifest.tables. It also supplies:

```json
{
  "experiment_contract": {
    "version": "1",
    "plan_sha256": "<SHA-256 of exact registered-plan.json bytes>",
    "randomization_attested": true,
    "assignment_roster_complete": true,
    "outcomes_complete": true
  }
}
```

These booleans are source assertions, not proofs. Set completeness false until the
experiment window is fully captured. External systems may supply equivalent ledgers,
but their assignment mechanism and historical registration require external audit.
The assignment tool does not query outcomes. Analytics cannot inspect hidden lab recipes.

## Canonical analytical boundary
experiment_population has one customer_id per enrolled unit.
experiment_assignments has experiment_id, customer_id, arm (control or treatment) and
assigned_at. Every roster member must have exactly one assignment. IDs must exist in
canonical customers. Duplicate, unknown or late assignments fail validation.
The plan checksum, table checksums and source manifest must match the ready warehouse.

A future source adapter maps its experiment roster and assignments into these contracts.
No advertising API, generator Python object or random seed enters analysis.

## Readiness and causal claims
Inference requires both planned arm targets, complete history and follow-up, attested
randomization/roster/outcomes, and a passing allocation-ratio screen. The screen uses
a conservative fair-Bernoulli Hoeffding tail bound with threshold 0.001.
Very tiny numerical tail bounds are floored at the smallest normal float, never reported
as exact zero. The formula and numerical limitations are explicit in the learning guide.

Before readiness, observed means and differences may be shown but intervals and
incremental estimates are null, and claim_type is observed_association.
After readiness, claim_type is causal_result with an explicit conditional ITT scope.
Passing these checks does not independently verify treatment delivery, stable identity,
absence of interference or historical preregistration. Hashes prove content binding only.

Intervals use independent-customer Hoeffding bounds with Bonferroni allocation across
the fixed three-metric family. They are deliberately conservative and may be wider than
model-based methods. Power planning is a sufficient worst-case target for a positive MDE,
not a guarantee that a realized experiment will be conclusive.

## Economics and guardrails
Customer gross merchandise totals remain exact integer paise before clipping to
[0, gross_cap_paise]. Scoped contribution is merchandise less observed refunds and
declared order-variable costs, clipped to contribution_bounds_paise.
The inference concerns these capped customer outcomes, not uncapped revenue or profit.
Uncapped incremental revenue/contribution fields remain explicitly null.

Contribution requires the existing complete M7 refund/cost contracts and a snapshot
ending exactly at the experiment end, preventing later refund/cost observations from
leaking into the result. Missing order costs make the entire contribution metric unknown.
No-order customers contribute zero only when the coverage contract is complete.
Synthetic cost provenance remains visible.

Point differences and estimated incremental totals in the treated cohort use exact
rational arithmetic. Their confidence limits are numerical approximations. Gross
merchandise is before refunds; contribution excludes acquisition spending and fixed costs.

Each predeclared economic guardrail has a maximum tolerated mean decline in paise.
It passes only if the simultaneous interval lower bound is at least minus that decline;
it fails if the upper bound is below it; otherwise it is inconclusive. Missing evidence
is unknown. Practical significance requires the primary interval lower bound to meet
the separately declared business threshold.

Results are not_ready, harm_detected, positive_with_guardrails,
benefit_guardrails_unresolved or inconclusive. None authorizes deployment or budgeting.

## Reproduce the lab
Use a new directory for generation:
```powershell
.venv/Scripts/python.exe -m nemo.lab_experiments --output artifacts/experiment-demo
.venv/Scripts/python.exe -m nemo.warehouse build --observations artifacts/experiment-demo/effect/observations --database artifacts/experiment-demo/effect/nemo.duckdb
.venv/Scripts/python.exe -m nemo.experiments --warehouse artifacts/experiment-demo/effect/nemo.duckdb --observations artifacts/experiment-demo/effect/observations --plan artifacts/experiment-demo/effect/plan.json --output-directory artifacts/experiment-demo/effect/results
```
Repeat the build and report for no_effect and allocation_mismatch. The engine sees only
plan/observations/warehouse. Seeds, injected probabilities and cost assumptions are in
a separate private/truth.json used only by the producer/evaluator.

The verified runs are indexed in artifacts/milestone-10/index.json. Reports use their
content hash as filename: identical analyses reuse the result, changes create another
immutable revision. This is the experiment-memory foundation; automatic retrieval
into future Decision Cases is not implemented.

These direct-traffic lab worlds intentionally have empty campaign/ad tables. The unchanged
full dbt freshness command returns errors for those two empty sources; customer/session/order
freshness, the 11-model/25-test builds, compilation and documentation are separately checked.
This is a documented warehouse freshness limitation, not evidence of complete advertising data.

## Boundaries
Cluster, geo, switchback, adaptive allocation, rolling enrollment, CUPED, sequential
monitoring and platform-reported incrementality are unsupported. Outcome independence
and no interference must be defensible for this design. Complete data and passing SRM
are necessary checks, not sufficient causal proof. No production treatment delivery,
cross-device identity resolution or external integration is claimed.
