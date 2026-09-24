# Milestone 16 — Retention / Expansion

Adds observed customer states, transitions, retention/reactivation review cases and
fully followed product-sequence evidence for cross-sell test design.
See [contracts](retention.md) and [learning guide](learning-retention.md).

## Delivered and bounded
Eight supported states use explicit precedence and 30/60/90/180-day rules.
CHURNED remains unsupported without a termination contract. Each cutoff independently
filters observed paid orders; future customers/orders cannot change an earlier state.
Historical receipts remain exact integer paise, never profit or forward value at risk.

Expansion validates complete item-to-order reconciliation and counts first A followed
by first B within an exclusive 30-day window, excluding prior/simultaneous B and
incomplete follow-up. A minimum support screen controls review eligibility.
Cases bind source identity and evidence revisions and retain measurement/consent/
cost/experiment prerequisites. No outreach, inferred propensity or causal value occurs.
Economic ranking is explicitly not_assessed until economically applicable evidence exists.

## Demonstration and validation
A manually constructed canonical source produces all eight supported states and three
review cases. It does not invoke M1 or require private truth.
Sixteen new tests cover state precedence and exact boundaries, cutoff exclusion,
sequence denominators, simultaneous/prior purchases, insufficient support, item money,
matching source hashes, exact history, deterministic reports and CLI overwrite safety.
The complete suite passes: 359 tests in 441.85 seconds. All 16 retention tests also
pass after the final policy-copy isolation change.

The demonstration passes all 36 dbt build/test nodes, compile and documentation.
One full-freshness error remains for its empty ad_performance table; four sources pass.
Ruff and package checks pass. The installed wheel reproduces the complete demo report.
M1 hashes, M6 code/dbt/dependencies and M12 replay remain unchanged. No type checker
is configured. Validation uses approved Ubuntu WSL; the Windows DuckDB block and
historical M6 runtime-fingerprint limitation remain unchanged.

## Limitations
No state is a calibrated churn probability. Left truncation may hide earlier purchases.
Refunded purchases remain observed transactions, not proof of ownership or satisfaction.
Product support is not multiple-testing correction, significance or estimated treatment
effect. Case types are explicitly distinct from M5 conversion cases and not automatically
imported into the ledger. Live customer messaging and financial optimization are absent.
M17 follows under the user's authorization for all remaining milestones.
