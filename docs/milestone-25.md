# Milestone 25 — Canonical pipeline orchestration

Adds a source-neutral runner and an isolated Airflow 3.3.2 DAG. The runner validates a
copied canonical snapshot, builds the existing warehouse, creates measurement/case/Analyst
reports and atomically publishes one immutable checksummed directory. The DAG publishes
then independently verifies it. No generator execution, external model, company
credentials or marketing action is required.

## Operational guarantees and learning
Source/method/runtime identity governs replay. Repeated runs validate source and output,
restore/verify warehouse readiness and return unchanged. Corruption and active locks fail
closed. Ordinary failures clean temporary work and do not publish partial reports.
Airflow has two retries, exponential backoff, one active run and bounded task/subprocess
execution. Child processes receive only basic runtime environment variables.

Read [operations and recovery](orchestration.md) and the
[learning guide](learning-orchestration.md), including examples, formulas, alternatives,
failure modes and five interview answers. Airflow requirements and a standalone DAG
check are in orchestration/. They are separate from the core package and frozen lock.

## Verification
Seven focused pipeline tests pass with manually authored canonical observations:
publication/replay, independent verification, checksum corruption, injected failure and
retry recovery, source tampering, existing locks and invalid configuration/identity.
A real Airflow DAG test passed both a replay (9.01 seconds) and fresh publication
(10.26 seconds); both publish and verify_publication tasks reached success. The isolated
check also verifies actual DAG structure, retries/timeouts, child credential isolation
and controlled subprocess failure/timeout propagation.

Wheel/sdist and installed-wheel pipeline replay pass, alongside clean archive checks,
M1 hashes, M6 frozen method/runtime/dbt fingerprints and M12 ledger replay. Ruff checks
pass. Full Python regression: 471 passed in 512.93 seconds with one known warning. Existing
warehouse tests exercise real dbt/SQL. No web code changed and no type checker is configured.

## Limits
This is a tested local orchestration path, not a hosted production scheduler.
schedule=None prevents accidental recurring execution; reporting cadence, arrival
completeness, date advancement, backfill policy, alerts, access control, distributed
storage, HA and backups remain deployment work. A hard crash may leave a lock requiring
operator recovery after confirming no process is still active. Atomic rename provides
publication visibility, not a power-loss durability guarantee. Canonical inputs and output
roots are trusted operator-managed files; hashes do not establish source authenticity.

Airflow validation used Linux/WSL and local SQLite metadata. A Graphviz warning affected
optional diagram rendering only. Core validation retains the known Starlette/httpx
deprecation warning. The subsequent M26 audit will address newly identified urllib3
advisories without changing the frozen analytical dependency versions.
