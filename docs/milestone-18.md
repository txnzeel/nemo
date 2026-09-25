# Milestone 18 — Response Curves

Implements bounded observational saturation curves with explicit data sufficiency,
chronological holdout comparison and empirical error bands.
See [contract](response-curves.md) and [learning guide](learning-response-curves.md).

## Delivered
A checksummed canonical weekly supplement declares complete receipts, refunds and
variable-cost components. Contribution before media has an explicit definition;
all observations retain integer paise. Private simulation parameters are never read.

The saturating family has decreasing marginal response. Fixed-grid fitting uses only
training weeks; holdout outcomes do not estimate parameters. Weak variation, missing
weeks, grid-boundary fits, unsupported spend and insufficient improvement over a
constant baseline withhold the curve. Accepted curves permit scenarios inside training
spend support only. No causal incremental contribution or action recommendation follows.

## Validation
Thirteen focused tests pass: diminishing marginal response, exact input money,
holdout isolation, support rejection, weak/flat data, missing costs/weeks, duplicate
grain, checksums, optional absence, deterministic reports and safe CLI output.
The full saved suite passes: 386 tests in 460.66 seconds (exit 0).

The manually authored example is constructed from the fitted family: its good holdout
fit verifies mechanics, not generalization to company behavior. Curve MAE is about
10,710 paise versus about 652,631 paise for the constant baseline on that example.
The demonstration passes 36 dbt build/test nodes, compile and docs. One expected
freshness error remains for its empty ad_performance table; four sources pass.
Generated sources, fitted output and sample curve points remain local.

Ruff lint/format and wheel/sdist checks pass. The installed wheel reproduces the complete
response report outside the checkout; archives exclude private/generated data and runtimes.
M1 hashes, M6 code/dbt/dependency fingerprints and exact M12 replay remain preserved. No type checker is configured. Approved
Ubuntu WSL remains the runtime; Windows DuckDB and the historical frozen M6 compiler
fingerprint limitation remain unchanged.

## Limits and next step
Weekly economic aggregates are source assertions, not order-level reconciliation.
Thresholds are documented heuristics; retained-fit error is not guaranteed future
uncertainty. Confounding, seasonality, timing and omitted channel interactions remain.
M19 uses these models only for conditional constrained allocation and controlled review.
