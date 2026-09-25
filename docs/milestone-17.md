# Milestone 17 — Forecasting / Scenario Lab

Adds chronological naive forecasting and exact conditional scenario arithmetic.
See [contract](forecasting.md) and [learning guide](learning-forecasting.md).

## Delivered
Forecasts use existing canonical sessions, orders and merchandise receipt definitions.
SQL produces daily totals; missing days become zero only under explicit public complete
coverage. Last-value and weekly seasonal candidates compete on earlier rolling origins.
Later audit targets are separated by a horizon gap, preventing target leakage.
MAE, bias, empirical interval coverage and horizon-specific error bands are retained.

Scenario calculations expose spend/CPC/conversion multipliers and fixed landing rate,
orders-per-purchasing-session and average receipt assumptions. All calculations use
exact fractions. Caller-provided totals retain their declared source reference and
unverified status. No auction effect, causal counterfactual or incremental profit is claimed.

## Validation
Fourteen new tests cover seasonal selection, held-out structural breaks, nonoverlapping
evaluation targets, short histories, invalid horizons, canonical SQL facts, historical
cutoffs, exact scenario arithmetic, unsupported changes, missing coverage and CLI safety.
The complete saved validation passes: 373 tests in 400.93 seconds (exit 0).

The manual weekly demo passes all 36 dbt nodes, compile, docs and all five freshness
checks. A separate structural-break example demonstrates degraded audit performance.
The perfectly periodic example has zero audit error, explicitly not a real-world claim.
Artifacts remain local and excluded from Git.

Ruff lint/format, wheel/sdist builds and clean-archive checks pass. Installed-wheel
forecast and scenario outputs reproduce the complete demonstration outside the checkout.
M1 hashes, M6 code/dbt/dependency fingerprints and exact M12 ledger replay are preserved. Ubuntu WSL is the verified runtime; Windows DuckDB and the old frozen M6
compiler-fingerprint limitations remain unchanged. No type checker is configured.

## Limits
Only naive daily forecasts over 1–14 days are supported. Overlapping audit errors are
not independent; empirical bands do not guarantee future coverage. Source coverage is
an assertion. No complex model is justified by these examples.
M18 follows under the user's authorization for all remaining milestones.
