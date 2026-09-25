# Milestone 19 — Budget Studio

Implements exact-grid constrained allocation and sensitivity over M18 scenario-only
response evidence. The interactive presentation belongs to M22.
See [contract](budget-studio.md) and [learning guide](learning-budget-studio.md).

## Delivered
Weekly total budget, spend grid, experiment reserve, channel bounds, share limits and
relative change limits define a reproducible feasible set. Current and selected spend
remain within the observed model support. Infeasible constraints fail without relaxation.

A deterministic marginal-gain heap solves the separable concave uniform-grid objective.
Exact fractions preserve objective comparisons and integer paise preserve budget totals.
Output retains effective/binding bounds, current/selected model estimates, empirical
stress bounds and +/-20% per-channel response sensitivity.

The result is conditional_optimization_scenario with controlled_review_only eligibility.
It does not decide whether full spending is worthwhile, infer causal lift, fabricate
reserve return, execute changes or call partial contribution profit.

## Demonstration
A manual two-channel canonical response source yields 190,000 paise paid-search spend,
210,000 paise paid-social spend and 50,000 paise experiment reserve: exactly 450,000 paise.
This illustrates model mechanics and constraints, not a real-company recommendation.
The example curves are constructed observations, not evidence of production economics.

## Validation
Twelve focused tests pass, including exhaustive-search comparison, exact totals,
share rounding, sensitivity feasibility, invalid/infeasible inputs, evidence tampering,
withheld curves, unsupported spend and CLI safety.
The full saved suite passes: 398 tests in 404.11 seconds (exit 0).

The example passes 36 dbt build/test nodes, compile and docs. One expected freshness
error remains for its empty ad_performance table; four sources pass.
Ruff lint/format and package checks pass. The installed wheel reproduces allocation
and sensitivity outside the checkout; clean archives exclude local/private artifacts.
M1 hashes, M6 code/dbt/dependencies and exact M12 replay are preserved. No type checker is configured.
Ubuntu WSL remains the verified runtime; the Windows DuckDB and frozen M6 runtime
limitations remain unchanged. Generated data and outputs remain outside Git.

## Limitations and next step
Only separable concave weekly models and at most 10,000 spend steps / 12 channels
are supported. Empirical stress bounds are not joint confidence intervals. Observational
models remain confounded; the optimizer cannot upgrade their evidence.
M20 is explicitly conditional: assess MMM readiness before deciding whether fitting
is methodologically justified. Continue the remaining authorized release work.
