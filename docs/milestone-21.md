# Milestone 21 — API Product Layer

M21 provides a local authenticated FastAPI transport over the existing NEMO platform.
See [API contract and startup](api.md) and [learning guide](learning-api.md).

## Delivered

Server-configured dataset IDs select canonical observations, validated warehouses,
optional experiment plans and scoped decision ledgers. Typed requests call the existing
measurement, case, opportunity, experiment, economics, journey, attribution, search,
retention, forecast, response and allocation services. No metric logic is duplicated.

Separate read/write bearer roles protect access. Ledger writes preserve lifecycle,
idempotency, optimistic concurrency and source checks. Body limits, safe errors,
request IDs and public path containment bound the local transport. OpenAPI is authenticated.
Money remains exact integer paise or rational values, with an explicit lossless-client
requirement. Catalog origin labels distinguish manually authored fixtures from claims
about production data.

## Architectural review

Current source boundary: canonical observations and validated warehouse models.
Synthetic coupling discovered: none added by the API; its manual fixture never runs M1.
Changes made: optional transport, request validation and scoped local authorization.
Canonical boundary: existing business entities, metric definitions and source hashes.
Future adapter extension: normalize external observations into canonical contracts,
build the existing warehouse, then register a dataset; no analytics rewrite is required.
Tests added: API/service parity, read services, auth roles, retries, stale updates,
safe failures, body streaming limits, path/symlink containment and exact JSON money.
Existing tests affected: no existing expectations or frozen M1/M6 code were changed.
M3 scope remaining: none reopened; this work belongs to M21.

## Validation

The full suite passes: 421 tests in 445.77 seconds, exit 0, with the API extra installed
and no skips. A subsequent focused run passes all 24 API tests, including one additional
large-integer serialization test added after full-suite collection: 422 distinct tests
verified in total. The only warning is Starlette's deprecated HTTPX test-client adapter;
the real Uvicorn smoke check is independent of that adapter.

Ruff lint and format checks pass. The manual fixture passes all 36 dbt build/test nodes,
compile and docs generation. Source freshness deliberately reports two errors for empty
campaigns and ad_performance tables; the other three sources pass. No freshness policy
or existing milestone expectation was weakened.

A real localhost Uvicorn process verifies health, rejected unauthenticated access,
authenticated catalog, acquisition, Decision Case and OpenAPI delivery, then shuts down.
The built wheel reproduces the Decision Case outside the checkout. Wheel/sdist archives
exclude private/generated/local-runtime files. M1 source and observation hashes,
M6 frozen code/dbt/dependency fingerprints and M12 ledger replay remain intact.
No type checker is configured.

Validation uses the locked Python 3.12.13 Ubuntu WSL runtime because Windows Application
Control still blocks the native Windows DuckDB extension. The historical M6 Windows
Python compiler fingerprint is not relabelled as a Linux result. The demonstration
uses manually authored observations, not company data or private simulation truth.

## Limitations and next milestone

Local bearer roles do not establish human identity or tenant isolation. Public deployment,
production secrets infrastructure and live external integrations are not claimed.
Missing analytical evidence remains withheld. The base CLI does not require FastAPI.
The next milestone is M22's Next.js Decision Case experience; it starts after proceed.
