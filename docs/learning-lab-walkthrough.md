# Learning lab — Read, reproduce and defend a NEMO Decision Case

Use this with [the concept guide](learning-decision-cases.md). Everything below refers
to implemented behavior. You do not need advertising credentials or a Snowflake account.

## Before starting
Read these existing guides in order:

| Topic | Guide | Question you should be able to answer |
|---|---|---|
| Business observations and money | synthetic-business.md | Why are receipts not profit? |
| Metric definitions | metric-registry.md | Why is purchasing-session CVR different from orders per session? |
| Warehouse | warehouse.md | How can an old event correction enter an incremental pipeline? |
| Source independence | source-architecture.md | Where would an external adapter plug in? |
| Measurement integrity | milestone-4.md | Why does missing tracking not erase paid orders? |
| Diagnosis | learning-decision-cases.md | Why does a hypothesis not establish a deployment cause? |

A canonical contract defines shared business concepts. It is not a guarantee that real
sources are accurate. A warehouse test can prove a key is unique; it cannot prove that
an advertising provider reported every click.

## Lab 1 — Inspect the three controls
The verified demonstration is under artifacts/milestone-5.

| Folder | What the lab changes | What the detector should conclude |
|---|---|---|
| healthy | No planted business defect | no_signal |
| failure | Purchase tracking removed for selected Android sessions | measurement_issue |
| business | Selected successful payments become failures; corresponding orders and purchases disappear | payment_stage_hypothesis |

Open the case JSON files in each folder's cases directory. The latest verified paths
are listed in artifacts/milestone-5/index.json. Earlier immutable revisions may remain
after method changes; use the index to select the handoff version.

Read these fields in order:
1. scope and analysis_cutoff: are the windows comparable?
2. measurement: what was checked, and what remains unknown?
3. observations.baseline/current: inspect sessions and purchasing_sessions.
4. observations.comparison: examine the rule and exact decomposition.
5. payment_evidence and device_payment_comparisons: locate the observed stage movement.
6. alternatives and contradictions: what weakens the hypothesis?
7. recommendations: distinguish measurement eligibility from execution authorization.
8. provenance: identify source and method fingerprints.

Do not start by opening private/payment-truth.json. A human can inspect lab truth after
reviewing the case, but the detector must never need it.

## Lab 2 — Reproduce a new case revision
From the repository root, using the existing verified business warehouse:

```powershell
.venv/Scripts/python.exe -m nemo.decision_case --warehouse artifacts/milestone-5/business/nemo.duckdb --observations artifacts/milestone-5/business/observations --baseline-start 2026-06-03 --current-start 2026-06-17 --output-directory artifacts/milestone-5/business/cases
```

The current period ends at the supplied snapshot's exclusive end, July 1.
The comparison windows are June 3–16 and June 17–30, both 14 days.
The same inputs and method produce the same revision file. Changing source data or
method evidence creates a distinct immutable revision while preserving the logical case ID.

A historical case requires a canonical snapshot ending at its cutoff. Passing a later
snapshot and casually ignoring future data is not the supported API. This still does
not reconstruct the order in which corrections originally arrived.

## Lab 3 — Work the arithmetic
Business-problem case:
- Baseline: 151 purchasing sessions / 1,242 sessions.
- Current: 65 purchasing sessions / 1,129 sessions.
- Observed purchasing-session change: 65 − 151 = −86.

Compute both rates with a calculator. The decline is about 6.40 percentage points,
or 52.65% relative to baseline. Both anomaly thresholds pass.

The exact midpoint decomposition is:
- Volume: −28,386,617 / 2,804,436 ≈ −10.1220 purchasing sessions.
- Rate: −212,794,879 / 2,804,436 ≈ −75.8780 purchasing sessions.
- Sum: −86 exactly.

These fractional allocations describe arithmetic contributions. They are not fractional
physical orders, measured incremental loss, or a guaranteed recovery opportunity.

Control comparison: the healthy current period has 123 purchasing sessions, not 151.
The lab removed 58 orders; the detector observes an 86-session decline versus baseline.
Why are these different?
Answer: the observed period-to-period movement also includes natural changes in the
reference world. The detector cannot identify the hidden intervention's exact impact
from that difference alone.

## Lab 4 — Trace the implementation
Start at src/nemo/decision_case.py:
- compare implements the operational rule and exact Fraction-based identity.
- _payment_evidence validates the public funnel contract and runs funnel.sql.
- build_case binds source hashes, assembles evidence, chooses a bounded finding and gates candidates.
- save_case retains immutable JSON revisions.

Follow existing measurement.py and acquisition.sql to the dbt session/order facts.
They retain the M2 metric definitions. funnel.sql performs stage aggregation at the
session grain and checks attempt/terminal/order consistency. integrity.py owns the
measurement gate. lab_payment.py produces controls and has no downstream import path.

There is no optimizer, significance test, anomaly model training, causal estimator,
Decision Ledger database or production connector hidden behind these names.

## Lab 5 — Run focused checks
```powershell
.venv/Scripts/python.exe -m pytest tests/test_decision_case.py --tb=short
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
```

Read test_tracking_loss_is_not_diagnosed_as_business_failure, then read
test_generator_and_lab_imports_blocked_and_private_truth_ignored.
Explain why a manually authored fixture is stronger boundary evidence than a test
that can only consume generator-produced Python objects.

## Lab 6 — Create another controlled world
Use a new output path; the lab refuses to overwrite an existing run.

```powershell
.venv/Scripts/python.exe -m nemo.lab_payment --observations artifacts/milestone-1-verified/observations --output artifacts/my-payment-lab --device android --start 2026-06-17 --end 2026-07-01
.venv/Scripts/python.exe -m nemo.warehouse build --observations artifacts/my-payment-lab/business/observations --database artifacts/my-payment-lab/business/nemo.duckdb
.venv/Scripts/python.exe -m nemo.decision_case --warehouse artifacts/my-payment-lab/business/nemo.duckdb --observations artifacts/my-payment-lab/business/observations --baseline-start 2026-06-03 --current-start 2026-06-17 --output-directory artifacts/my-payment-lab/business/cases
```

The producer uses a fixed hash-based subset of eligible paid orders. It does not
resimulate later customer behavior. Its selection and affected IDs are private lab truth.
This is one deterministic demonstration, not the held-out evaluation harness of M6.

## Explain it in an interview
A defensible short explanation:

“I built an observation-only diagnostic slice. It validates measurement, compares
equal session cohorts under explicit thresholds, exactly decomposes the count change,
and inspects device-level payment evidence. It emits an immutable, source-linked
Decision Case. Tracking defects block event-based interpretation, and a payment-stage
hypothesis remains observational. Controls and import-blocking tests enforce that
the detector does not read the planted answer.”

Do not claim production connectors, calibrated false-positive performance, causal
identification, incremental revenue or profit. Those require evidence this milestone
does not yet provide.

## Self-check
- Can you derive the decomposition identity by expansion?
- Can you distinguish a 2 percentage-point decline from a 25% relative decline?
- Can you explain why a device with fewer than 30 attempts is unassessed, not contradictory?
- Can you identify every prerequisite still blocking budget optimization?
- Can you show why the healthy, tracking and business cases have different revisions?

If any answer feels vague, return to the relevant JSON field, formula and test.
