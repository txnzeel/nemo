# Milestone 24 — Google integration boundary

Implements bounded read-only Ads v25, GA4 Data API and Search Console REST extraction.
Each writes a versioned aggregate staging report. No company account has been accessed;
live verification for all three services remains pending authorized credentials.

## Delivered
Fixed provider endpoints, bounded pagination/response sizes, safe failure messages,
atomic output publication, exact INR micros-to-paise mapping, duplicate-grain checks,
GA4 quality metadata and Search Console returned-query/Pacific-time coverage.
The [setup and contract guide](google-integrations.md) explains account access, environment
variable names, commands, provider sources and the separate canonical activation gate.
The [learning guide](learning-google.md) includes business meaning, formula, failure
modes, alternatives and five interview questions with answers.

## Boundary
No aggregate report invents individual sessions, customers, orders or events.
Staging is explicitly not activated for analytics. Future reviewed adapters normalize
into existing canonical contracts; downstream services and private lab separation are
unchanged. No CAC, ROAS, causal or profit definition was introduced.

## Validation
Twenty-one offline Google checks pass: pagination, currency/sub-paise rejection,
out-of-window/duplicate rows, changing GA4 counts/schema, threshold metadata, exact
decimal position, missing credentials, response bounds, redirects and atomic failure.
Full regression: 464 tests passed in 614.21 seconds, with the existing Starlette/httpx
deprecation warning. Ruff lint/format pass.
Wheel/sdist and installed-wheel GA4 fixture reproduction pass, with clean archives,
M1 hash preservation, M6 frozen fingerprints and M12 ledger replay.

No web or dbt implementation changed; the full regression includes actual dbt/SQL
checks. No type checker is configured. Windows native DuckDB remains blocked; Python
validation uses Ubuntu WSL. Constructed provider fixtures do not establish live API
compatibility, quota, account permission, reconciliation or data completeness.

## Remaining external gate
Supply approved credentials locally, run a small window, reconcile against each source,
record limitations and approve canonical mapping. Token refresh, continuous ingestion,
bulk event exports and source-to-canonical activation remain future integration work.
