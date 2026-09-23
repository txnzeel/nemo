# Milestone 13 — Outcome Measurement

## Outcome
Implements descriptive outcome measurement for implemented decisions after declared
observation windows, with exact target comparisons and append-only lessons. The milestone
is verified in the approved Ubuntu WSL environment.

See [the contract and commands](outcomes.md) and [the learning guide](learning-outcomes.md).

## Architecture and changes
- Current source boundary: canonical observations -> existing dbt/metric semantics ->
  outcome report -> decision ledger. No generator-private state is consumed.
- Synthetic coupling discovered: none. Production sources use the same canonical mapping
  and dataset identity contracts. No new connectors or source-specific logic are added.
- outcome_contract.py defines supported metric plans, readiness checks, exact arithmetic
  and bounded descriptive lessons.
- outcomes.py measures ready warehouses against matching public observations and saves
  a reviewable report before an explicit record step.
- ledger.py adds plan_outcome and record_outcome events. The original evidence, action,
  ownership, narrative expectations and prior measurement events remain auditable.
- Plans register while accepted and freeze before work starts. The window freezes at
  planning. Legacy implemented decisions cannot receive retrospective backfilled plans.
- Ordinary terminal action-state updates remain forbidden. Outcome events append
  measurements without reopening a decision.

Existing metric definitions, warehouse models, source contracts, M1 generator behavior
and the frozen M6 detector code are unchanged.

## Supported semantics
Targets use sessions, paid orders, gross merchandise receipts or session conversion.
Count and paise targets are integers; rates and differences use exact fractions.
The existing session-cohort and payment-date definitions remain authoritative.
Arbitrary partial-day windows, narrative-to-numeric target inference, contribution
growth and causal lift are not added.

Readiness requires an implemented decision, declared plan, an elapsed and covered window,
and a reported action occurrence at or before the window starts. Missing plans,
uncovered/future windows and undefined ratios preserve null values with explicit blockers.
Source/decision mismatch, tampering and stale writes fail rather than producing comparisons.

Lessons distinguish observed target met, observed target missed and unresolved evidence.
They retain retrospective planning and measurement-health limits. They never claim
that the action caused the result or that merchandise receipts are profit.
Automated reuse of prior lessons remains Milestone 14 work.

## Canonical demonstration
Six separate hypothetical histories use the existing public M5 payment observations.
All action and target records are explicitly retrospective demonstrations, not deployments.
The Android window is June 17–30, 2026, using complete Asia/Kolkata business days.

| Scenario | Observed result | Outcome |
|---|---|---|
| CVR target at least 1/100 | 12/613 | Observed target met; difference 587/61300 |
| CVR target at least 1 | 12/613 | Observed target missed; difference -601/613 |
| Merchandise target at least 1 paise | 2,855,200 paise | Observed target met; not profit |
| No registered plan | Unknown | missing_outcome_plan |
| Window beyond supplied history | Unknown | source_does_not_cover_window |
| Action occurs after window begins | Unknown | window_precedes_reported_action |

Demonstration targets exercise comparisons; they are not recommended business thresholds.
Local ledgers, reports and checks are indexed in artifacts/milestone-13. Generated
artifacts, local runtimes and private lab truth remain outside Git.

## Validation
The 67 focused outcome/ledger tests pass, including 44 new M13 cases and 23 existing
ledger cases. The complete suite passes: 314 tests in 412.76 seconds, including all
270 prior tests and 44 new M13 cases.
New cases cover manual canonical integration, exact rates and paise, both comparators,
invalid plans, immutable planning, elapsed/covered windows, unknown denominators,
dataset/source mismatch, snapshot mutation, ledger state binding, tampering, retries,
remeasurement history, stable JSON round trips, CLI behavior and private/generator denial.

Ruff lint/format and wheel/source builds pass. All six outcome scenarios reproduce
from the installed wheel outside the checkout. Current decision/time/revision metadata
naturally changes on a fresh measurement; metric evidence and derived outcomes match.
The complete M12 and M13 ledger exports replay exactly.

The fresh warehouse passes all 11 models and 25 dbt tests, compile, docs generation and
full source freshness. Previous M10/M11 empty campaign/ad-source freshness limitations
remain documented in those milestones; no freshness rule was weakened.

M1 source and observation hashes are preserved. M6 code, dbt and dependency fingerprints
match the frozen protocol. Its historical Windows held-out scoring is not rerun under
Linux's different Python compiler/build fingerprint. The existing Blind Lab tests run
under the current Linux runtime; this does not relabel the old benchmark environment.
No type checker is configured. No live company connector or Snowflake verification is claimed.

## Validation environment
The existing Windows DuckDB extension is unsigned and currently blocked by Smart App
Control (Code Integrity event 3077, VerifiedAndReputableDesktop). Windows security
settings were not changed. The user approved Ubuntu WSL validation with the same
Python 3.12.13 and locked dependencies.

The full suite uses an isolated native Linux temporary runtime for faster dbt imports.
The dependency environment under .tools/linux-validation and isolated installed-wheel
environment provide reproducible package checks. See the Ubuntu commands in outcomes.md.
The Windows-native runtime limitation remains open; Linux verification is reported
separately rather than claimed as a Windows pass.

## Remaining scope
Authenticated action delivery, causal outcome attribution, additional outcome metrics,
production service scaling and automated lesson reuse are not implemented here.
M14 — Decision Memory starts only after the user says proceed.
