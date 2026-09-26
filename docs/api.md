# API contract and local operation

M21 exposes existing NEMO services through an optional FastAPI application.
API version 1 is reported by health and authenticated OpenAPI; analytical responses
retain their existing schema, revision, provenance and evidence-level fields.

## Install and run

Use the repository's locked Python 3.12 environment:

```sh
uv sync --locked --extra api
uv run --extra api python -m nemo.api --root /absolute/public-data-root --catalog /absolute/catalog.json
```

On this machine the verified runtime is Ubuntu WSL; Windows Application Control still
blocks its native DuckDB extension. These commands do not change that policy.

Before starting, set NEMO_READ_TOKEN to a randomly generated secret of at least 32
characters. Optionally set a distinct NEMO_WRITE_TOKEN to enable ledger writes.
Supply secrets through the local environment, not command arguments or committed files.
No default credentials exist. The server binds 127.0.0.1:8000; --port changes the port.
The root, catalog and backing data are operator-managed configuration.

Example catalog (paths are relative to the configured root):

```json
[
  {
    "id": "example",
    "label": "Manual canonical example",
    "origin": "manual_fixture",
    "observations": "observations",
    "warehouse": "verified.duckdb",
    "ledger": "decisions.sqlite",
    "experiment_plan": "plan.json",
    "baseline_start": "2025-01-01",
    "current_start": "2025-01-05"
  }
]
```

Use actual validated canonical observations and their built warehouse. Optional
resources may be omitted. The paired comparison dates must satisfy the existing
Decision Case window contract. The origin label is an operator assertion:
unverified_source (default), manual_fixture, synthetic_lab or company_data_unverified.
Neither this label nor a canonical mode of production establishes real-company provenance.
Catalog capability flags indicate configuration, not successful analytical readiness.

## HTTP surface

All routes except GET /health require Authorization: Bearer <token>.
GET /openapi.json provides the actual request schemas; interactive docs are disabled.

| Route | Purpose |
| --- | --- |
| GET /datasets | Public IDs, labels, origin and configured capabilities; no filesystem paths |
| GET /metrics | Existing metric definitions |
| GET /datasets/{id}/measurement-health | Canonical measurement trust |
| GET /datasets/{id}/acquisition | Metrics with start/end and one grouping |
| GET /datasets/{id}/decision-case | Configured conversion comparison |
| GET /datasets/{id}/opportunities | Existing evidence-gated review board |
| GET /datasets/{id}/experiments | Existing configured experiment analysis |
| GET /datasets/{id}/customers | Customer economics, bounded cohort age |
| GET /datasets/{id}/journeys | Observed journeys, bounded lookback |
| GET /datasets/{id}/attribution | Descriptive allocation, not causality |
| GET /datasets/{id}/search | Paid/organic search evidence |
| GET /datasets/{id}/retention | Explicit baseline/as_of state analysis |
| GET /datasets/{id}/forecast | Bounded naive forecast and audit evidence |
| GET /datasets/{id}/response-curves | Supported observational response evidence |
| POST /scenarios | Conditional assumptions; read role |
| POST /datasets/{id}/optimization | Conditional allocation using server-read response evidence; read role |
| GET /datasets/{id}/decisions | Scoped ledger history |
| POST /datasets/{id}/decisions | Writer imports a server-calculated opportunity |
| PATCH /datasets/{id}/decisions/{decision_id} | Writer updates through existing ledger rules |

Import requires opportunity_id, request_id and rationale. Updates require
expected_version, request_id, rationale and changes. Stable request IDs preserve
idempotent retries; changed commands under the same ID and stale versions return 409.
The actor is local-api-operator, a service role, not an authenticated human identity.
Outcome-plan/measurement operations and decision memory remain available through their
existing Python/CLI interfaces; they are not new HTTP endpoints in this milestone.

## Exact money and evidence

Integer paise and rational numerator/denominator objects are serialized without float
conversion. Consumers must use an integer-preserving JSON parser: JavaScript Number
cannot represent every int64 value exactly. Do not pass large money values through
ordinary JSON.parse and assume precision is preserved. This contract is tested above
2^53. The API introduces no financial or metric definitions.

Missing data, measurement blockers and withheld analyses stay visible in service
responses. HTTP 200 does not mean a recommendation is actionable. Attribution remains
descriptive, forecasts and allocations remain conditional, and receipts remain receipts.

## Boundaries and limitations

Configured paths stay under one root; traversal, private paths and escaping symlinks
are rejected. Each dataset has a distinct ledger and ledger source identity is checked.
Canonical services validate their existing observation/warehouse contracts. No route
accepts arbitrary filesystem paths, SQL, generator parameters or private truth.

Request bodies are limited to 256 KiB based on actual received bytes, including chunked
requests. Validation errors return 422 without echoing submitted values. Missing datasets
return 404, missing configured resources 409, role denial 403, missing credentials 401,
oversized bodies 413, and expected storage/runtime failures 503. Responses include
X-Request-ID, Cache-Control: no-store and X-Content-Type-Options: nosniff.
Uvicorn access logging is disabled.

This is a local authenticated service, not an enterprise deployment. Tokens grant
access across the configured catalog; dataset IDs do not implement tenant isolation.
The operator must protect the root and catalog from concurrent untrusted modification.
No TLS termination, user identity provider, rate limiting, distributed scheduling,
advertising execution or public deployment is claimed. Requests run existing synchronous
analysis; large workloads will need measured operational limits before remote deployment.

## Verification

Install the api extra before running pytest; a base CLI installation intentionally
skips the optional API test module. The milestone validation installs the extra and
runs it without skips. Run the focused boundary checks with:

```sh
uv run --extra api python -m pytest tests/test_api.py
```

See [M21 report](milestone-21.md) and
[learning guide](learning-api.md).
