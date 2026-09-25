# MMM readiness decision

Decision: defer model fitting. This is the conditional M20 review, not an implemented
MMM feature or a causal media-return result.

NEMO has canonical metrics, experiment infrastructure, attribution comparisons,
forecast baselines and source/evidence boundaries. Those satisfy software prerequisites.
They do not by themselves provide an identified media-effect dataset.

## Evidence reviewed
- M18/M19 public response examples have 24 deliberately constructed weeks per channel.
  Their outcomes follow the illustrative curve family; good fit validates mechanics.
- M1 is a deterministic business reference world, not observed company marketing data.
- No approved public time/geo panel of demand, pricing, promotions and relevant confounders
  is currently supplied for the same KPI/media population and reporting period.
- Existing checkout experiments do not automatically calibrate channel-spend effects.
- Private generator coefficients are unavailable to analytical fitting by design.

Google Meridian's data guidance distinguishes aligned media, spend, KPI and control
series; its causal guidance also makes clear that observational identification requires
assumptions beyond predictive accuracy.
[Data preparation](https://developers.google.com/meridian/docs/pre-modeling/collect-data)
and [causal assumptions](https://developers.google.com/meridian/docs/causal-inference/about-mmm-causal-inference-methodology).

## What would justify reopening
Provide audited, consistently scoped media exposure/spend and an additive outcome with
complete coverage; documented demand and business drivers chosen using a causal graph;
enough independent variation and history for the proposed effects; and compatible
experiment evidence where available. Define estimands, priors, lag/saturation choices,
out-of-time validation, residual/collinearity diagnostics, sensitivity and transport limits.
No universal row-count threshold proves identification.

A future controlled lab could produce public covariates and observations plus separately
sealed evaluator truth. Fit sees observations only; evaluation joins truth afterwards.
A future company adapter supplies the same canonical analytical inputs without M1.
Do not substitute private probabilities for missing confounders or label regression
coefficients causal simply because a sampler converges.

## Product consequence
No MMM endpoint, empty tab, dependency or fabricated ROI output is added.
M18 response curves and M19 allocation remain explicitly conditional scenarios.
Continue with M21 API work; real data and a reviewed methodological design can reopen MMM.
