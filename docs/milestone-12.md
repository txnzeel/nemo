# Milestone 12 — Decision Ledger

## Outcome
Implemented local decision tracking from immutable M11 opportunity reports. Decisions
retain evidence, confidence, blockers, recommendations, ownership and human expectations.
A transactional append-only history records review and reported action through a strict
lifecycle. Actual outcomes, differences from expectation and lessons remain null.

See [the contracts and walkthrough](decision-ledger.md) and
[the learning guide](learning-decision-ledger.md).

## Architecture review
- Current source boundary: canonical observations -> existing analyses -> M11 report -> ledger.
- Synthetic coupling discovered: none introduced; ledger replay needs only its database.
- Changes made: new ledger module, tests, lifecycle documentation and learning material.
- Canonical boundary: existing schemas, money contracts, warehouse models and metric
  definitions remain unchanged. Evidence labels and exact source values are preserved.
- Future production adapter: normalize company sources into the canonical contract;
  existing analyses and the ledger consume the same downstream report structure.
- Tests added: 23 cases covering manual canonical evidence, lifecycle, blocked actions,
  immutable snapshots, retries, concurrent edits, failed-write rollback, audit corruption,
  CLI errors and denial of generator/private-state access.
- Existing tests affected: none modified. All 247 prior tests remain in the full suite.
- Scope remaining: M13 outcome measurement and M14 decision memory; no new connectors,
  attribution rules, causal methods, optimization or external action execution.

The ledger stores the complete report as an evidence snapshot. A report content hash
detects changes but does not authenticate its author or prove the source true.
New report revisions create new decisions linked by the stable opportunity ID.

## Demonstration
Six existing opportunity scenarios are imported into a local ledger:

| Scenario | Final ledger status |
|---|---|
| Tracking discrepancy | proposed |
| Payment-stage investigation | implemented, demonstration assertion only |
| Positive experiment review | proposed |
| Inconclusive experiment follow-up | proposed |
| Allocation readiness failure | proposed measurement work |
| Attribution disagreement | blocked |

Nine events preserve the six imports and payment review/start/completion sequence.
The payment completion is explicitly labelled a demonstration. It does not claim a
real system change, verified root cause or improved conversion. All measured outcome
and lesson fields remain null. Artifacts and JSON export are under artifacts/milestone-12
and are excluded from Git.

## Validation
- Full pytest suite: 270 passed (247 existing + 23 new).
- Ruff lint and format check pass.
- Wheel and source distribution build; archive contents exclude generated artifacts,
  private truth, local runtimes and Git metadata.
- Installed wheel outside the checkout replays the complete saved ledger exactly.
  Re-submitting the demonstration commands reproduces all decision fields except the
  new recording timestamps. Identical retry returns the original receipt.
- Fresh payment-source warehouse: 11 models + 25 dbt tests pass; compilation, docs
  generation and full source freshness pass. Its M11 report matches the saved report.
- Original M1 source/observation hashes, M6 frozen method and held-out score are unchanged.
- No type checker is configured. No live Snowflake or company connector is claimed.

The earlier M10/M11 direct-only experiment fixtures still have their documented empty
campaign/ad-performance source freshness limitation. The M12 warehouse verification uses
the existing nonempty payment fixture and does not change or weaken those freshness rules.

~~~powershell
.venv/Scripts/python.exe -m pytest --tb=short
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv build --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
~~~

## Operating limits
Actor/owner names and implementation reports are human assertions. Acceptance does not
authorize spending or execute work. Expectations are narrative assumptions, not computed
metrics. Observation windows may be retrospectively recorded and are not experiment
preregistration. The ledger does not revalidate live evidence freshness.

SQLite transactions and optimistic versions protect local writes; full replay checks
the chain. Hashes and triggers are not a security boundary against a privileged database
owner, full-chain rewriting or tail truncation. Authentication, external audit anchoring,
backups and large-scale projections remain future integration work. Plans freeze at
work start and terminal records cannot be amended in M12.

Next: Milestone 13 — Outcome Measurement, only after the user says proceed.
