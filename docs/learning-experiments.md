# Learning guide — controlled experiments and incrementality

## Meaning
A controlled experiment assigns eligible customers to treatment or control before
outcomes. Intention-to-treat (ITT) compares customers as assigned, including nonbuyers.
This is different from attribution, which divides credit for purchases already observed.

## Business purpose
Test whether a change improves purchase probability while protecting commercial
outcomes. Randomization can support causal inference only when assignment, observation,
identity and interference assumptions hold. A declared experiment is not proof those
assumptions were satisfied in a real deployment.

## Example
Suppose 600 customers per arm complete a fixed seven-day window. Control has 90 buyers
and treatment 240. Rates are 15% and 40%; absolute lift is 25 percentage points,
relative lift is about 167%, and estimated incremental buying customers among the
600 treated customers is 150. This is not 150 necessarily observed extra orders.
An interval describes uncertainty; it does not reveal individual counterfactuals.

## Formulas and uncertainty
Primary metric = customers with at least one paid order / all assigned customers.
Absolute lift D = treatment mean - control mean. Relative lift = D / control mean,
undefined when the control mean is zero. Incremental buying customers = D × n_treatment.
Economic outcomes use customer totals, clipped to predeclared bounds before comparison.

For independent outcomes in a range of width R, Hoeffding gives a conservative
two-sided interval with radius
R × sqrt(0.5 × (1/n_treatment + 1/n_control) × log(2/alpha_metric)).
Use alpha_metric = alpha/3 for the fixed family: purchase, capped gross merchandise,
and capped scoped contribution. Missing metrics do not release their error budget.
The null tail-probability upper bound is
min(1, 2 × exp(-2 × (D/R)^2 / (1/n_treatment + 1/n_control))).
It is a conservative p-value bound, not an exact randomization p-value.

For equal arm sizes and desired positive MDE d, required size per arm is the ceiling of
(sqrt(log(2/alpha_metric)) + sqrt(log(1/(1-power))))^2 / d^2.
This is a conservative sufficient target, not a normal-approximation calculator.
Bernoulli allocation does not guarantee reaching both arm targets.

These formulas apply the bounded-independent-sum result in
[CMU's concentration-inequality notes](https://www.stat.cmu.edu/~cshalizi/sml/21/lectures/06/lecture-06.html).
The implementation assumes independent customer units from the target population;
cluster/network dependence requires another design.

## Data requirements
Freeze hypothesis, population criteria, treatment, control, 50/50 customer randomization,
dates, primary metric, MDE, power, alpha, practical threshold, economic caps and guardrails.
Supply the eligible customer roster, assignments logged before the outcome window,
canonical orders and a declared completeness cutoff. Refund/cost coverage is required
for scoped contribution. Missing costs cannot become zero.

The plan and source hashes bind reports. Historical registration timestamps supplied
by adapters are assertions; a hash cannot prove genuine preregistration or deployment.

## Implementation
The design module registers a plan and can create a saved random assignment ledger
using operating-system randomness. Analytics separately validates the public plan,
roster and assignments, constructs customer outcomes and checks readiness.
The engine uses a fixed common outcome window, no exposure filtering, and one final
analysis. Early snapshots show observations but withhold inferential claims.

A sample-ratio screen checks the observed arm count against declared 50/50 allocation,
using a conservative Hoeffding bound and a fixed 0.001 threshold.
[Microsoft Research](https://www.microsoft.com/en-us/research/articles/diagnosing-sample-ratio-mismatch-in-a-b-testing/)
explains why allocation imbalance must be investigated before trusting experiment effects.
Our screen is conservative and is not their full diagnostic implementation.

## Failure modes and business interpretation
Repeated significance checks, dropping nonbuyers, post-treatment exclusions, missing
assignment records, changing the plan, unstable identities and interference can invalidate
inference. Passing checks does not certify correct exposure or absence of contamination.
Wide intervals and low power mean inconclusive, not no effect.

Gross merchandise is before refunds. Capped gross and capped contribution estimands
are not uncapped revenue or company profit. Contribution excludes acquisition and fixed
costs. Synthetic costs remain assumptions. Guardrails pass only when their interval
rules exclude an unacceptable decline; unknown guardrails cannot authorize action.
MDE is a planning target; the separate practical threshold is a business requirement.

## Interview explanation
"I preserved assignment denominators, froze a fixed-horizon plan, checked source
binding, maturity and allocation balance, and used conservative simultaneous intervals.
I distinguished observed lifts from conditional causal estimates and exposed unknown
economics. Exact customer money totals stay integer paise; effect points are rational
estimates, and uncertainty bounds are numerical approximations."

## Practice
Follow [the experiment walkthrough](experiments.md). Compare a healthy effect with
an allocation-mismatch or incomplete snapshot. Explain why the same observed lift
cannot always be called incremental, and why no automatic rollout is produced.
