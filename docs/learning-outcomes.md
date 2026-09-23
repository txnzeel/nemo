# Learning guide — Outcome Measurement

## Meaning
Outcome measurement revisits an implemented decision after its observation window.
It compares an explicitly planned metric target with observed canonical data.

## Business purpose
A recorded action is not a demonstrated result. Teams need reproducible observations,
an honest comparison with expectations, and a bounded lesson before reusing decisions.

## Example
An analyst plans for observed session conversion of at least 1/5 over seven complete
business days. There are 21 purchasing sessions among 100 sessions. The observed target
is met and the difference is 1/100 (one percentage point), not a 1% causal lift.
Other changes, seasonality and selection could explain the outcome.

## Formula
CVR = purchasing sessions / sessions, using the existing session-cohort contract.
Difference from target = observed value - target, computed as an exact rational number.
At least compares observed >= target; at most compares observed <= target.
Money remains integer INR paise, tax-exclusive merchandise before refunds, never profit.

## Data requirements
An accepted decision needs a metric, dimension filters, comparator and exact target.
Register the plan before work starts. Its existing UTC window must align with complete
Asia/Kolkata business days. Reported action occurrence must precede the window.
Use a ready warehouse of the same dataset/source mode covering the entire window and
matching canonical observations. The wall clock must also have passed the window end.
The public source declares coverage; structural validity cannot prove complete capture.

## Implementation
A separate plan event preserves the metric contract and recording time. A source-only
measurement reuses existing acquisition SQL and metadata. An outcome event binds the
report to the exact decision version and state hash. Replay validates the comparison
and generated lesson. New measurements append history; they never change the old plan,
action or evidence snapshot. Existing M12 histories continue replaying unchanged.

## Failure modes
Missing plans, incomplete follow-up, pre-action windows, and undefined ratios cannot
establish success. Later ingestion may revise results; retain both report revisions.
Retrospective planning is labelled, never presented as preregistration. Filters must
match the intended population; whole-dataset results cannot answer an unplanned device
question. Measurement-health limitations travel with the result. Meeting an observed
target does not estimate incremental effect, profit or attribution accuracy.

## Interview explanation
“I separated intended outcomes from observed outcomes, froze a metric target before
work started, enforced elapsed and covered windows, and preserved exact arithmetic.
Each measurement has source and decision provenance and appends an auditable lesson.
I report target attainment descriptively; causal effectiveness needs its own design.”
