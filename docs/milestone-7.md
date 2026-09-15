# Milestone 7 — Customer Economics

## Outcome
Implemented first-observed buyer acquisition, monthly cohorts, calendar-month purchase
retention, historical customer value and explicitly scoped order contribution.

Read [the contracts and hands-on walkthrough](customer-economics.md) and
[the learning guide](learning-customer-economics.md). The guide explains meaning,
business purpose, examples, formulas, required data, implementation, failure modes
and interview explanations before the new calculations.

## What changed and why
- economics_inputs.py validates optional declared item/refund/cost observations.
- economics.sql produces one row per buyer with exact money and coverage propagation.
- retention.sql distinguishes complete inactive months from partial/future months.
- economics.py exposes acquisition, customer, cohort, retention and total views, plus
  versioned metric definitions and input/code provenance.
- lab_economics.py creates refund-only and explicitly assumed-cost controls.
- Tests use a manually authored multi-month company-labelled fixture.

The existing dbt order facts and purchase_rank determine observed acquisition.
No generator internals, private cost assumptions or synthetic probabilities enter
analytics. Existing M1–M6 metric definitions and dbt models are unchanged.

## Business and evidence boundaries
First observed is not first-ever acquisition. Purchase-session channel credit is not
causal attribution. Historical net merchandise value is not predicted lifetime value.
Retention measures calendar-month purchases, not subscription survival.

Contribution subtracts declared net order-variable costs from net merchandise receipts.
It excludes acquisition spending and fixed overhead. Missing costs or refunds stay
unknown; partial coverage cannot silently shrink the customer denominator.
Merchandise receipts and scoped contribution are not labelled profit. Full CAC and
incremental economics remain unassessed.

Source assertions of coverage or observed cost provenance are not independently audited
financial truth. Synthetic cost observations are marked synthetic_assumption.

## Verified reference results
- 5,574 observed buyers; 5,989 paid orders; 381 repeat buyers.
- Gross merchandise receipts: 1,380,800,300 paise.
- Observed refunds: 83,655,300 paise.
- Net merchandise receipts: 1,297,145,000 paise.
- Refund-only contribution: null because the source has no cost feed.
- Assumed-cost contribution: 559,274,494 paise under explicitly documented toy costs.

The assumption-based result tests the implementation; it does not estimate a company's
cost structure or profitable acquisition budget. Both controls preserve original order
observations. Original M1 source and artifacts are retained.

## Validation
The suite contains 165 tests: 148 prior tests plus 17 Customer Economics tests.
The 17 targeted tests pass. They cover hand-calculated values, first-purchase credit,
distinct buyer denominators, zero/partial/future retention, grouping reconciliation,
missing cost coverage, invalid refunds/costs, very large exact integers, negative
contribution, source binding and blocked generator/lab imports.

All 165 tests pass, along with Ruff lint/format, wheel/source builds and artifact checks.
The installed package reproduces both demonstration reports exactly outside the checkout.
Both dbt builds pass all 11 models and 25 tests; freshness, compilation and docs generation
also pass. Original M1 source/artifact fingerprints and the M6 frozen detector/held-out
score are unchanged. No type checker is configured.

Configured commands:
```powershell
.venv/Scripts/python.exe -m pytest --tb=short
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv build --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
```

The new SQL runs in integration tests and package smoke tests. Each demonstration
warehouse retains the existing 11-model / 25-test dbt pipeline.
The M6 frozen detector is unchanged; its prior sealed evaluation remains verifiable.

## Trade-offs and remaining work
Canonical supplemental files extend the established source boundary without altering
existing analytics or requiring speculative connectors. Persistent refund/cost marts,
broader credit/rebate schemas, arrival-as-of reporting and production completeness
reconciliation remain future integration work.

No LTV forecast, causal estimate, optimizer, subscription churn or profit model is added.
Current cost components are a declared scope; they cannot silently stand for all
company costs. Cohorts have unequal observed histories and calendar follow-up.

## Next milestone
Milestone 8 — Journey Reconstruction. Stop until the user says proceed.
