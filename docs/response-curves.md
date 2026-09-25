# Response curve contracts

M18 fits a bounded observational model from a public canonical weekly supplement.
It does not infer causal incremental contribution or authorize budget changes.

## Input
response_observations.jsonl uses unique Monday week_start/channel rows. Each week must
fit completely inside the canonical snapshot. Channel must be declared paid media.
Rows provide nonnegative int64 spend_paise, merchandise_receipts_paise,
merchandise_refunds_paise and all five existing cost components: net_cogs_paise,
fulfillment_paise, payment_fees_paise, refund_handling_paise, other_variable_costs_paise.

response_contract requires version "1", outcome "contribution_before_media",
cost_provenance "observed", weeks_complete true, variable_cost_components in the existing
canonical order, and nonempty scope and lineage_reference descriptions.
These aggregates are source assertions, not independently reconciled with canonical
order-level costs. The adapter must preserve comparable timing and population and
must exclude media from the five cost components. Missing components are not zeros.

Contribution before media = merchandise receipts - merchandise refunds - five costs.
Refunds can exceed current-week receipts; resulting contribution may be negative.
This explicit partial contribution definition excludes fixed overhead and is not profit.
All observed money stays integer paise. Fitted parameters and predictions are numerical
estimates, never settlement amounts.

## Method and gates
At least 24 consecutive observed weeks are required. First two thirds train; last third
audit. Training needs >=8 distinct spends and positive max/min spend ratio >=3.
Audit spends outside training support withhold the model.
Fit y=A*x/(B+x) with nonnegative least-squares A for each of 41 fixed B candidates:
max(training spend)*2^(-5+i/4), i=0..40. Choose minimum training squared error.
Zero A or a winning grid boundary withholds the model because saturation is not
identified within this family/grid. Holdout MAE must improve a constant training-mean
baseline by at least 5%. These are explicit heuristic screens, not causal/statistical proof.

Accepted models retain training support, parameters, holdout errors and 90th-percentile
absolute audit error. Evaluation rejects extrapolation. Marginal response is A*B/(B+x)^2.
Bands are predicted point +/- empirical error width, not guaranteed coverage or parameter
credible intervals. Data-dependent acceptance can make retained models look optimistic.

## Source boundary and commands
Future adapters map complete economic aggregates into this supplement; vendor payloads,
seeds, private configuration and synthetic probabilities are not inputs.
A missing supplement is not_assessed. Invalid declared data fail validation.

    python -m nemo.response_curves --observations observations --output response.json

report(observations) produces an evidence-bound report; evaluate(curve, spend_paise)
returns a conditional scenario only within observed support. Existing files are protected.
See [learning guide](learning-response-curves.md).
