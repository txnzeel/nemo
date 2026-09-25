# Learning guide — Budget Studio

## Meaning and purpose
Constrained allocation finds the best modelled distribution of a fixed budget subject
to declared limits. A mathematically optimal solution is conditional on the response
model; it does not make observational evidence causal or authorize spending.

## Example and formula
For channel i, scenario contribution before media is f_i(x_i).
Maximize sum(f_i(x_i)-x_i) subject to sum(x_i)+experiment_reserve=total budget,
channel bounds, share limits, change limits and observed model support.
With a fixed modelled budget, subtracting media is constant, but must still appear in
the reported contribution calculation. Experimental reserve has unknown outcome.
Diminishing marginal gains permit discrete greedy allocation: start at feasible minima,
then repeatedly assign one spend step to the channel with the largest next gain.
This is exact on the declared uniform grid for separable concave response functions.

## Data requirements
Versioned response evidence, explicitly scenario-only observational curves, integer
paise budgets and step sizes, channel constraints and current allocations.
Every candidate allocation stays inside the observed spend support. No model for an
unobserved channel or outside its range is invented. Reserve spending is separate.

## Implementation
Validate evidence hashes, model shape and finite parameters. Round lower bounds up and
upper bounds down to the spend grid and report those effective bounds. Reject infeasible
budgets rather than relax constraints silently. Preserve exact budget accounting and
deterministic ties. Compare current and selected model outputs and perturb response
scales for sensitivity. Retain every assumption and binding constraint.

## Uncertainty and failures
Empirical curve errors summed across channels are stress bounds, not a joint confidence
interval. Omitted channel interactions and common demand shocks violate separability.
An observational optimum is a test proposal, not an economically justified causal
recommendation. Small parameter perturbations can move allocation; show that sensitivity.
Grid size trades resolution for runtime. Current spending can differ from the proposed
budget, so a difference must never be labelled experimental uplift.

## Alternatives and trade-offs
Linear constraints alone do not justify a linear response assumption. Generic nonlinear
solvers need feasibility checks and can hide local optima. Concave grid allocation is
transparent and testable by exhaustive enumeration on tiny problems.
Stronger experiment-calibrated response models are needed before action recommendations.

## Interview questions and answers
1. What is optimized? Conditional modelled contribution, under explicit constraints.
2. Why a grid? Exact budget feasibility and a reproducible bounded optimization problem.
3. Why is greedy valid? Separable concavity makes each channel's next gain decrease.
4. Does it prove more profit? No, observational models do not establish intervention effects.
5. How do you test it? Compare tiny cases to exhaustive search, assert every bound,
   and report sensitivity rather than relying only on a plausible-looking allocation.
