# Milestone 11 — Opportunity Engine

## Outcome
Implemented structured opportunities from canonical measurement, diagnostic, attribution
and experiment evidence. Each item gives a bounded recommended_next_step and retains
evidence strength, assumptions, blockers, source references and unknown forward value.

See [the contracts and walkthrough](opportunity-engine.md) and
[the eight-part learning guide](learning-opportunities.md).

## What changed
- opportunities.py recomputes requested upstream analyses, verifies a common source
  snapshot and applies explicit opportunity rules.
- Stable IDs and immutable revisions separate business questions from changing evidence.
- Ranking places blocked items last, then uses documented manual-review priorities.
- Existing payment and attribution gates remain effective.
- Historical capped experiment effects stay separate from unestimated forward value.
- Nineteen new tests exercise rules and integration using manually authored canonical data.

No existing generator, warehouse model, metric, evidence gate or experiment inference
method changed. Production adapters still target canonical observations; private truth
and generator parameters are not inputs. No speculative connectors are added.

## Demonstration outcomes
Seven queues are reproduced from existing public canonical observations:

| Scenario | Proposed | Blocked | Outcome |
|---|---:|---:|---|
| Healthy diagnostic control | 0 | 0 | No invented work |
| Tracking discrepancy | 1 | 0 | Measurement reconciliation |
| Payment-stage hypothesis | 1 | 0 | Bounded diagnostic investigation |
| Positive experiment | 1 | 0 | Evidence/guardrail/rollout-assumption review |
| Inconclusive experiment | 1 | 0 | Consider a separately registered follow-up |
| Allocation mismatch | 1 | 0 | Resolve experiment readiness; no incremental value |
| Attribution disagreement | 0 | 1 | Research candidate retains the attribution-contract blocker |

The positive experiment does not produce a SCALE instruction or forecast. Attributed
credit never becomes causal evidence. An observed payment hypothesis never becomes a
verified root cause. All items are manual_review_only.

Local artifacts, source locations, parameters and checks are indexed under
artifacts/milestone-11. Generated queues, warehouses and private lab truth remain outside Git.

## Validation
The complete suite contains 247 tests: 228 prior tests and 19 opportunity cases.
Tests cover healthy silence, tracking-versus-business distinction, missing funnel contracts
with healthy purchase tracking, preserved suppression,
experimental evidence scope, historical-versus-forward value, inconclusive/readiness/harm
routing, attribution thresholds and blockers, ranking, replay, stable IDs, immutable
revisions, source mismatch, parameter validation, CLI output and private/generator access
denial. The manually authored fixtures prove M1 is not required.

Ruff lint/format and wheel/source builds pass. The installed wheel reproduces all seven
complete queues exactly outside the checkout. Archives exclude generated data, private
truth and local runtimes. No type checker is configured.

All seven demonstration warehouses run the existing 11-model/25-test dbt pipeline,
compilation and documentation generation. The four M5-based inputs have nonempty source
tables. The three M10 inputs retain the documented full-freshness errors for empty
campaign/ad-performance sources; customer/session/order freshness is checked separately.
The existing rules are not weakened or relabelled as a complete freshness pass.

```powershell
.venv/Scripts/python.exe -m pytest --tb=short
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv build --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
```

Original M1 artifact/source hashes and the M6 frozen detector/held-out score are preserved.
No live integration or Snowflake verification is claimed.

## Remaining scope
Forward economic valuation, risk/effort estimation, value-of-information optimization,
additional opportunity families and production UI remain future work. Status describes
review eligibility only. This milestone does not implement a decision ledger, automatic
execution, ownership assignment or post-action measurement.

Next: Milestone 12 — Decision Ledger, after the user says proceed.
