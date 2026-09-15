# Milestone 3 — Warehouse Foundation and Source Independence

## Status
The local warehouse milestone is implemented and verified. Snowflake is a configuration
and least-privilege deployment template only: no account, ingestion, build, or role
enforcement has been verified. No connector, attribution engine, causal estimate,
optimization, AI, or Measurement Integrity score was added.

## Architecture audit requested before implementation
| Item | Finding / outcome |
|---|---|
| Current source boundary | Public observations and manifest → contract validation → warehouse → metrics |
| Synthetic coupling discovered | Schema-1-only admission, forced synthetic labels, hard-coded channels/devices |
| Changes made | Backward-compatible normalization plus explicit canonical schema 2 metadata |
| Canonical boundary | Dataset identity, mode, canonical channels/paid flags/devices, exact INR paise |
| Future adapter | Map provider schemas, IDs, timestamps and units into this contract |
| Tests added | Hand-authored paid-social/tablet source; fresh process blocks generator imports |
| Existing tests affected | All 85 original tests retained and passing |
| Warehouse scope | Actual local dbt pipeline; connected Snowflake execution remains unverified |

M1 remains a reference producer, demo/development world and future controlled evaluation
laboratory. It is not required to execute production-labelled canonical observations.
See [source-architecture.md](source-architecture.md).

## What was built / why a business needs it
A durable local canonical warehouse, keyed incremental ingestion and a dbt model graph
that preserves acquisition measurement. This provides repeatable data products instead
of rerunning independent ad hoc transformations and makes model relationships/test
results inspectable. Advertising and sessions remain central alongside paid orders.

There are 11 dbt models: five staging views, one intermediate order-history view, customer
and campaign dimensions, an incremental advertising fact and rebuilt session/order facts.
dbt owns model transformations. The semantic query uses these facts and the existing
metric registry. The old SQLite acquisition execution path was removed; the input
validator still uses SQLite constraints before loading DuckDB.

The loader validates the complete snapshot, compares normalized record hashes, applies
keyed upserts in one transaction and records load batches. Replay is a no-op. Arrival
batches capture corrections on old business dates. Session/order models rebuild so a
late earlier purchase can revise existing customer history. Reporting uses read-only
connections and refuses unbuilt, failed or changed-model states.

## Alternatives and trade-offs
- Blind append would duplicate purchases/spend; event-date watermarks would miss corrections.
- Incrementalizing all history-dependent models would require more complex dependency
  invalidation; rebuilding these small models is simpler and correct.
- A permanent parallel M2 analytical implementation was rejected. The observation API
  builds a temporary real dbt warehouse; repeated reporting should use a persisted warehouse.
- Complete cumulative snapshots simplify a verified ingestion boundary. Provider delta/CDC
  delivery and deletions require a separate explicit contract, not silent retention.
- One dataset per local database is deliberately simpler than premature multi-tenant
  serving. dataset_id is a mixing guard, not authorization.

The canonical loader, dbt transformations, and adapter-specific query execution are
separate responsibilities. A future Snowflake executor will bind the same metric semantics
using its driver; no provider payload belongs in downstream metric calculations.

## Concepts learned
Grain determines what a row means and prevents many-to-many aggregation errors.
Dimensions describe entities; facts store observations at declared grains.
An arrival watermark differs from a business event date: old events can arrive or be
corrected later. Record hashes enable idempotence without relying on random seeds.
RBAC grants capabilities to roles; role names alone are not evidence of enforcement.

No new financial or statistical metric was introduced. Paid merchandise receipts remain
distinct from profit; full CAC is unavailable without complete costs. All current metric
outputs explicitly state descriptive_metric, not causal evidence. See the M2 learning
contract for the eight-part metric explanations.

## Validation
The suite contains 98 tests: 85 original tests, five canonical-boundary tests, and eight
warehouse tests. All pass, including real dbt builds. The warehouse tests exercise replay,
old-date correction, earlier-purchase ranking, transactional rollback on rejected deletion,
cross-dataset refusal, actual dbt test failure with blocked reporting and full-refresh
recovery, read-only serving, freshness failure, and stale-model refusal.

The persisted 18-month build runs 25 dbt data tests: key uniqueness, not-null, relationships,
paid flags, advertising grain, monetary/funnel constraints, and order count/amount
reconciliation. All pass. A second load returns unchanged at batch 1 with no duplicate rows.
Source freshness, dbt compile and docs generation succeed locally.
All M2 demo metric values, additive facts and 12 groups match exactly.

Ruff lint/format and package checks apply to the current repository. No mypy/type-check
command is configured; none is claimed. Source distributions exclude generated data and
runtime caches; the wheel includes the actual dbt project. An isolated installation with
locked dependencies built a warehouse and produced a report outside the source checkout.
The final full report is at artifacts/milestone-3-final.json. Snowflake templates are
reviewed configuration, not live integration or authorization tests.

An initial structured-parameter bulk-load approach was measured as slow (30,000 small
records took 31.64 seconds in an isolated binding probe). It was replaced with typed JSON
bulk loading; no percentage speed-up or production throughput claim is made. No failing
test was weakened. The original five M1 Python modules remain unchanged.

## Commands
Use the README's local interpreter selection where needed.

    uv sync --locked
    uv run pytest --tb=short
    uv run ruff check .
    uv run ruff format --check .
    uv run nemo-warehouse build --observations artifacts/milestone-1-verified/observations --database artifacts/milestone-3/nemo.duckdb
    uv run nemo-warehouse freshness --database artifacts/milestone-3/nemo.duckdb
    uv run nemo-warehouse compile --database artifacts/milestone-3/nemo.duckdb
    uv run nemo-warehouse docs --database artifacts/milestone-3/nemo.duckdb
    uv run nemo-measure --warehouse artifacts/milestone-3/nemo.duckdb --output artifacts/milestone-3-final.json
    uv build
    git diff --check

## What can go wrong / limits
The warehouse stores the latest canonical snapshot. Historical event-window reports
are restatements using currently available data, not point-in-time reconstructions of
what was known on an earlier ingestion date. Immutable input artifacts can support
rebuilding an old snapshot; the current warehouse is not an SCD/audit-history system.
Load audit rows do not substitute for full prior record versions.

Freshness measures row load/change recency, not tracking completeness or business-event
recency. Measurement health remains not_assessed. Correct source validation does not
establish factual truth or incrementality. No production connector is verified.

A crash can leave a writer lock; inspect the owning process before recovery. Manual
out-of-band database writes are outside the trusted builder workflow. The guarded
report API does not claim to detect arbitrary tampering of warehouse files.

Snowflake needs credentials, canonical RAW ingestion, a connected execution adapter,
dbt parity tests and positive/negative role tests. The optional adapter is locked but
not installed for local execution. Deployments must review names, grants and compute costs.

## Five interview questions and strong answers
1. **Does production need the synthetic generator?**
   “No. A manual canonical fixture works through dbt and measurement while generator
   imports are blocked. M1 is one reference producer; adapters map other sources to the contract.”
2. **Why use arrival batches rather than max business date?**
   “A correction for last month can arrive today. Its new load batch is processed even
   though its business date is older than the existing maximum.”
3. **Why rebuild customer order history?**
   “A late earlier order can change which purchase is first. Rebuilding the small
   history-dependent models is safer than updating only the newly arrived row.”
4. **How do you stop a failed pipeline from serving stale results?**
   “The builder marks the warehouse unready before dbt runs. The report API requires
   a successful build for the current batch and model fingerprint. Tests prove a real
   dbt failure blocks reporting and full refresh recovers.”
5. **What has actually been verified on Snowflake?**
   “Nothing live. I prepared the profile, optional adapter and role-grant template,
   but I would not claim integration or least-privilege enforcement until credentialed
   execution, parity, and denied-access tests pass.”

## Next milestone
Milestone 4 — Measurement Integrity: source reconciliation, one tracking failure, and
dependency-specific suppression of affected recommendations. Stop until the user says
**proceed**. Snowflake credentialed verification remains a separate outstanding integration.
