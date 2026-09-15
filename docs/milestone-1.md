# Milestone 1 — completion and interview guide

## What was built and why
A deterministic 18-month synthetic retailer with nine linked source tables, exact
monetary records, an offline CLI, reproducibility fingerprints, and safe snapshot
publication. Later diagnostics need coherent records that can be reconciled. All
activity is simulated; this milestone makes no analytical accuracy or business-impact claim.

## Architecture, alternatives, and trade-offs
- contracts.py: frozen typed records and validated generator configuration.
- simulation.py: local random generator; advertising → session → checkout → payment →
  paid order; paid lines → timed partial/full refunds.
- artifacts.py: canonical JSON Lines, checksums, public collection metadata, private
  config/source/runtime fingerprints, exclusive writer lock, and directory rename.
- cli.py: validated inputs and structured completion/error messages.

Runtime: Python 3.12.13, standard library only. Development: pytest and Ruff, locked
with uv. The build backend has a bounded requirement in pyproject.toml.
Independent Faker tables were rejected because they cannot prove event or money
consistency. pandas, an ORM, warehouse and services are unnecessary for this slice.
Advertising is aggregated; sessions, events and order lines retain individual relationships.
An in-memory model is adequate for the verified default world, not arbitrary scale.
Frozen dataclasses prevent mutation; arbitrary imported data validation is future work.

## Concepts learned
See [the eight-part learning contracts](synthetic-business.md).
Paid orders require successful payment. Refunds are separately timed records. Integer
paise makes reconciliation exact. Merchandise receipts are not contribution or profit.
Funnel probabilities are conditional on prior stages; expected counts are not realized
integer counts. Probabilities are modeling assumptions, not fitted findings.
Reproducibility needs config, source and runtime fingerprints as well as a seed.

## Verification
48 pytest cases passed, without warnings, on Windows / Python 3.12.13. They include the
default 546-day world and two independent short-world seeds; identity and relationships;
customer first-seen chronology; legal funnels; payment/order correspondence; exact line
and order totals; full/partial refund bounds and cutoffs; paid-click/session bounds;
empty traffic; probability endpoints; invalid inputs; artifact hashes; separate-process
reproducibility; overwrite refusal; writer-lock refusal; and failed-write cleanup.

Ruff lint and format checks passed. The wheel and source distribution built offline.
Archive inspection confirmed that no interpreter, dependency cache, generated data or
secrets were packaged. Git was initialized on main; there is no commit or remote.

Default seed 42 produced:

| Table | Rows |
|---|---:|
| customers (synthetic visitors) | 30,191 |
| products | 4 |
| campaigns | 2 |
| ad_performance | 3,276 |
| sessions | 46,152 |
| events | 72,393 |
| orders | 5,989 |
| order_items | 11,980 |
| refunds | 942 |

These are fixture sizes, not speed benchmarks or real commercial results.

Principal commands (PowerShell):

    uv sync --locked --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
    .venv/Scripts/python.exe -m pytest --tb=short
    .venv/Scripts/ruff.exe check .
    .venv/Scripts/ruff.exe format --check .
    uv build --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
    .venv/Scripts/nemo.exe --output artifacts/milestone-1-verified --lockfile uv.lock
    git diff --check

The initial Ruff run accidentally scanned .tools and altered installed libraries.
An explicit exclusion was added; Python was reinstalled, the altered package cache was
removed, and dependencies were downloaded cleanly before verification. A separate
pytest temporary-directory permission problem required an elevated test run. The cache
was moved into .tools/pytest-cache, and the final run passed without warnings. Tests
were not weakened to work around setup failures.

## What can go wrong / limitations
Uniform repeat-visitor selection, fixed prices, fixed stage timings and constant funnel
probabilities are simplistic. Visits occur during daytime. No inventory, tax engine,
shipping, promotions, costs, settlements, payment retries, cross-device identity uncertainty,
tracking defects or real integrations exist. A customer row is a simulated visitor, not
necessarily a paying customer. Amounts are tax-exclusive INR merchandise values.
Process termination can leave a lock/temporary directory; verify no writer is active
before recovery. Local snapshot publication is not distributed fault-tolerant storage.

Private config separation prepares for Blind Lab; it is not enforced process isolation.
No planted incident, diagnostic engine, evaluator, warehouse, API, web UI or AI exists.
Synthetic coherence does not establish real-world realism or analytical validity.

## Five interview questions and strong answers
1. **Why use a simulator instead of unrelated random tables?**
   “I need coherent observations: paid sessions are bounded by clicks, orders require
   payment success, and refunds reference paid lines. These constraints support meaningful
   downstream measurement and diagnostic tests.”
2. **How do you make monetary results defensible?**
   “Integer paise, sale-time unit prices, exact line-to-order sums, and bounded refunds.
   Costs and tax are explicitly excluded, so I do not call the resulting amounts profit.”
3. **Is a seed sufficient for reproducibility?**
   “No. Code, random draw order and runtime versions matter. I record configuration,
   source hashes, Python version and output hashes, and compare separate-process runs.”
4. **How does this prepare blind evaluation?**
   “Observations are separated from private generation parameters. Future analytics must
   receive only observations, with predictions sealed before comparison to hidden truth.
   The evaluator is not built yet.”
5. **What is the biggest limitation?**
   “This proves repeatable, internally consistent simulation, not realism or analytical
   performance. Authoritative metrics, tracking defects and blind diagnostics come next.”

## Next milestone
Milestone 2 — Acquisition Measurement: teach metric definitions, grains, denominators
and source requirements; build an authoritative metric registry and tests.
Stop until the user says **proceed**.
