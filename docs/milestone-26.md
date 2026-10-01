# Milestone 26 — Measured reliability and security

Adds a bounded local latency benchmark and hardens the web proxy against redirects,
oversized streamed bodies, non-JSON output and invalid UTF-8. Existing exact-money
parsing remains intact. The pipeline and canonical analytical definitions are unchanged.

## Measured outcome
Ten sequential warm-process samples on the manual 1,200-customer/330-session/330-order
fixture measured median Decision Case construction at 678.235 ms (nearest-rank p95
793.269 ms), and local no-model Analyst rendering at 0.161 ms (p95 0.373 ms).
The benchmark JSON records raw samples, response bytes, source case revision and runtime.
These are local descriptive timings, excluding HTTP/UI and warehouse construction;
they are not production scale, concurrency or SLA evidence.

See [measurement and security scope](reliability-security.md) and the
[learning guide](learning-reliability.md).

## Security changes and audits
The locked urllib3 dependency moves 2.7.0 → 2.8.0 for three advisories; optional PyJWT
moves 2.14.0 → 2.15.0 for one advisory. No other uv.lock version changes. An explicit
post-install overlay applies both fixes to the isolated Airflow environment.
The complete exported lock scope (all extras plus development dependencies), installed
Airflow environment and npm lock now report zero known vulnerabilities as of 2026-10-01.
Audit results do not certify security or future advisory status.
Airflow dependency compatibility checks pass and the real DAG replay remains successful
after the overlay. Core/API runtime changes are limited to urllib3.

## Validation
Full Python regression: 472 passed in 472.91 seconds with the existing Starlette/httpx warning. Nine Node tests pass:
the four existing precision/route/origin checks plus chunked exact-money parsing,
actual-size limits with misleading headers, declared oversize, invalid content/encoding,
and a real loopback redirect rejected before its target receives a request.
ESLint, Prettier, Ruff lint/format and the Next production build pass.
Wheel/sdist, installed-wheel benchmark case parity, clean archives, M1 hashes,
M6 frozen code/dbt/dependency fingerprints and M12 replay pass.
The existing suite runs actual dbt/SQL validation. No type checker is configured.

The rebuilt public lab preview was browser-checked across payment, healthy, measurement
failure, Analyst and empty-ledger views. Screenshots were captured for M27.
Authenticated Next/API browser verification remains pending from the earlier automatic
approval rejection; tests do not relabel the lab preview as a live API connection.

## Production limits
The platform remains a local validated foundation. Identity/tenant isolation, TLS,
rate limits, operational monitoring, backup/restore drills, real company reconciliation,
live provider verification and production capacity tests remain deployment gates.
No public service, advertising execution, causal profit or penetration-test claim is made.
