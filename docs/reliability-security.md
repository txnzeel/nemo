# Reliability, performance and security evidence

M26 measures local behavior and closes specific input/transport/dependency risks.
This document is a bounded engineering assessment, not a production certification.

## Measured service latency
On 2026-10-01, Python 3.12.13 in Ubuntu WSL2 ran ten sequential samples after one
untimed Decision Case warm-up. The manually authored canonical fixture has 1,200
customers, 330 sessions and 330 paid orders; ad and campaign tables are empty.
The prebuilt warehouse lives on the Windows-mounted project filesystem.

| Operation | Median ms | Nearest-rank p95 ms | Min–max ms | Serialized bytes |
| --- | ---: | ---: | ---: | ---: |
| Decision Case | 678.235 | 793.269 | 510.968–793.269 | 21,359 |
| Analyst, no model | 0.161 | 0.373 | 0.137–0.373 | 2,117 |

p95 = sorted_samples[ceil(0.95 × n) - 1]. With n=10 this is the maximum sample,
not a reliable estimate of production tail latency. Timings exclude HTTP, browser
rendering, source extraction and warehouse construction. No concurrency, throughput,
large-company dataset, memory-capacity or SLA claim is supported. The slowest measured
step is case construction; caching would need source/method identity and invalidation
semantics before adoption. No speculative metric/warehouse rewrite was made.

Reproduce against a validated canonical fixture:
```sh
uv run python -m nemo.benchmark --warehouse /path/to/warehouse.duckdb --observations /path/to/observations --baseline-start 2025-01-01 --current-start 2025-01-05 --repetitions 10 --output /path/to/latency.json
```
The JSON includes raw timings, row counts, case revision and runtime information.
Timing floats are operational measurements; business money remains exact integer paise.

## Hardening delivered
The server-side web proxy rejects redirects, accepts JSON responses only, validates UTF-8
and bounds the actual streamed response to 8 MiB even if Content-Length is absent or
false. Oversized/rejected streams are cancelled. Existing fixed route/loopback allowlists,
server-only credentials, 60-second aborts, origin checks and safe errors remain in place.
Large reports fail visibly; the UI does not quietly truncate analytical evidence.

urllib3 was upgraded from 2.7.0 to 2.8.0 in uv.lock to address CVE-2026-97687,
CVE-2026-97688 and CVE-2026-97689. The optional Snowflake dependency set also moves PyJWT from 2.14.0 to 2.15.0 for
CVE-2026-101918. Only those two locked packages changed. Frozen DuckDB,
dbt and analytical code versions remain intact. The isolated Airflow runtime also needs
the post-install security overlay in orchestration/security-requirements.txt; its upstream
constraints otherwise retain 2.7.0. The same overlay upgrades PyJWT 2.14.0 to 2.15.0
for CVE-2026-101918, found by auditing the separate Airflow environment. Apply the overlay after the constrained installation:
```sh
uv pip install --python /absolute/airflow-venv/bin/python -r orchestration/security-requirements.txt
uv pip check --python /absolute/airflow-venv/bin/python
```
[Proxy TLS advisory](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77)
and [chunked streaming advisory](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw)
describe upstream conditions and fixes. The
[PyJWT advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v)
documents its pre-verification parsing fix. Upgrading addresses the installed dependency;
it does not assert that NEMO was exploiting or exposed to every affected code path.

## Re-run checks
```sh
uv sync --locked --extra api
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
uv export --locked --all-extras --no-emit-project --format requirements-txt --output-file /tmp/nemo-all-requirements.txt
uv tool run pip-audit -r /tmp/nemo-all-requirements.txt --no-deps --disable-pip
```
From web/: npm ci, npm test, npm run lint, npm run format:check, npm run build and
npm audit. Stop an existing Next process before rebuilding, then restart it.
Airflow's standalone checks run in its own environment. Audit the installed Airflow
site-packages separately; the core/API export does not include that optional runtime.

No type checker is configured. Dependency audits report known advisories at the scan
time, not the absence of vulnerabilities. No penetration test or external deployment
audit was performed.

## Remaining production gates
A company deployment still needs verified company ingestion/reconciliation, tenant
isolation, human identities and role scope, TLS/reverse-proxy policy, rate limits,
retention/deletion policy, encrypted backups and restore exercises, secrets rotation,
centralized safe logging/alerts, capacity testing and operational ownership.
The current API is local; its catalog-wide tokens are not tenant isolation.
Canonical hashes are integrity checks, not proof that a source told the truth.
No credentials or private lab truth are committed or included in release archives.
