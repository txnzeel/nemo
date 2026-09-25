# Budget Studio contract

M19 provides conditional weekly allocation over accepted M18 response evidence.
It is a model-based scenario, not a causal spending recommendation or external execution.

## Input and feasibility
allocate(response_report, spec) verifies the response content revision and supported
saturating family. A hash checks content integrity, not author identity.
Only estimated scenario-only curves are accepted; all current and proposed spend must
stay within their observed training support.

Specification fields:
- period_days: exactly 7, matching weekly response observations.
- total_budget_paise: positive int64 total planned spend.
- step_paise: positive integer grid step.
- experiment_reserve_paise: nonnegative reserved spend with unknown outcome.
- channels: 1–12 unique declared channel specifications.

Each channel has channel, current_spend_paise, min_spend_paise, max_spend_paise,
min_share_bps, max_share_bps and max_change_bps. Shares are relative to total budget,
including the reserve. Basis points range 0–10,000; maximum change is relative to current
channel spend. All money is integer paise. Current spend need not equal the new budget.

Effective minima are the greatest of declared minimum, observed support minimum,
minimum share and downward change bound, rounded up to the grid. Effective maxima
are the least of declared maximum, support maximum, maximum share and upward change
bound, rounded down. Modelled budget must be divisible by the grid and use <=10,000
steps. Empty bounds or an infeasible total fail; constraints are never relaxed silently.

## Objective and solution
Allocate the fixed modelled budget (total less reserve) to maximize sum of predicted
contribution before media minus allocated media spend. Start at effective minima and
assign each remaining grid unit to the greatest next marginal gain.
Positive A/B in A*x/(B+x) make gains decrease, so greedy solves this separable concave
uniform-grid problem. Deterministic channel-name tie-breaking makes it reproducible.
Fitted parameter decimal representations are converted to exact fractions for objective
comparison; this preserves computation, not extra statistical precision.

This is a fixed-spend scenario. It does not decide whether spending the entire budget
is worthwhile. No return is fabricated for the experiment reserve.

## Output and evidence
Retain current/selected spend, effective bounds, binding constraints, marginal response,
modelled before-media and net contribution, and +/-20% per-channel response-scale
sensitivity allocations. Sum-of-error-width stress bounds are not a joint confidence
interval. Total expected contribution including unknown experiment return stays null.
Contribution excludes fixed overhead; it is not profit. Differences are not causal uplift.
Channel interactions and common demand confounding are outside this model.

## Commands
    python -m nemo.budget_studio --response response.json --spec budget-spec.json --output allocation.json

Existing files are protected. No credentials or network execution are involved.
The web interface is a separate M22 milestone; this milestone implements the verified
allocation service. See [learning guide](learning-budget-studio.md).
