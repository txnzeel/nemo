# Learning guide — MMM readiness

## What was built and why
M20 produces a documented readiness decision. It deliberately does not fit an MMM
to data that cannot support the intended causal interpretation. A business needs a
defensible reason to trust media-effect estimates before moving money.

## Meaning and example
Marketing mix modelling relates an additive outcome to media and other business
drivers over time, sometimes across geography. Suppose search spend and sales both
rise when demand rises. A predictive relationship alone does not isolate the effect
of changing spend. Observational identification needs assumptions and appropriate
controls. [Meridian causal guidance](https://developers.google.com/meridian/docs/causal-inference/about-mmm-causal-inference-methodology).

## Illustrative formula
y_t = baseline_t + sum_c f_c(adstock(x_c,t)) + beta*z_t + error_t.
An illustrative adstock recursion is a_t = x_t + lambda*a_(t-1), with lambda between
zero and one. These symbols define possible mechanisms, not fitted NEMO parameters.
Private generator probabilities are never substitutes for observed drivers.

## Data and architecture
A future model consumes aligned canonical media exposure/spend, an additive KPI,
documented relevant drivers and coverage. Driver selection follows a causal design,
not a rule to control for every available column.
[Meridian data guidance](https://developers.google.com/meridian/docs/pre-modeling/collect-data).
Source adapters and canonical models remain separate from simulation and evaluation.
The evaluator may know hidden effects; the analytical fit may not.

## Alternatives considered and trade-offs
Current naive forecasts, observational response scenarios and controlled experiments
already have explicit scopes. Adding a flexible MMM now would increase apparent
sophistication without identified media effects. Deferral leaves a real capability gap
visible instead of manufacturing ROI. Neither attribution nor good holdout fit fills it.

## Failure modes
Confounding, collinear channel spend, inappropriate controls, missing coverage, weak
variation, unrealistic priors and transport between treatments can all undermine media
claims. Convergence does not prove identification. A checkout experiment is not
automatically a prior for the effect of an advertising budget change.
Synthetic fitting success validates code under its constructed assumptions, not clients.

## Five interview questions and answers
1. Why defer? Current constructed examples lack independently observed causal drivers.
2. What is still useful? Explicit scenario analysis and experiments within their scopes.
3. What would reopen it? A reviewed estimand/design, suitable data, diagnostics and
   sensitivity checks, with compatible experimental calibration where available.
4. Why not use the generator's coefficients? It would leak answers into analytics.
5. What can you claim now? A documented readiness assessment; no implemented MMM
   endpoint, causal media ROI or MMM-based production recommendation.
