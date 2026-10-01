# Canonical pipeline and Airflow operations

M25 runs a producer-independent canonical snapshot through warehouse validation,
measurement assessment, Decision Case construction and local Evidence Analyst rendering.
It publishes a complete report directory only after every step succeeds.
No advertising action, external model call or source extraction is scheduled.

## Core runner

Use the locked NEMO environment. An operator-owned JSON config has exactly these fields:

```json
{
  "observations": "/absolute/canonical/observations",
  "output": "/absolute/pipeline-output",
  "baseline_start": "2025-01-01",
  "current_start": "2025-01-05"
}
```

```sh
uv run python -m nemo.pipeline --config /absolute/config.json
uv run python -m nemo.pipeline --config /absolute/config.json --verify RUN_ID
```

The source must be a valid complete canonical snapshot. It can come from a manual
fixture, M1 or a future production adapter. Google aggregate staging is not an accepted
substitute for event/entity contracts. Each output root belongs to one canonical dataset.

The runner takes an exclusive output lock, copies only known public observation files
to a temporary snapshot and validates them. It derives a run ID from the source manifest,
comparison dates, analytical code/dbt hashes and relevant runtime versions. It builds
the existing warehouse, writes case.json, measurement.json and analyst.json, verifies
their hashes, then renames the pending directory to the run ID on the same filesystem.
publication.json records the identity and exact file hashes. There is no mutable latest
pointer: consumers must select an explicit successful run ID.

On replay, source and publication checks still run, and warehouse readiness is restored
or verified. A matching publication returns unchanged. A corrupted publication fails;
it is never silently overwritten. An ordinary error removes temporary work and releases
the lock. An old successful publication remains available but is not a new successful run.

## Isolated Airflow runtime

Airflow is separately pinned to 3.3.2 with its Python 3.12 constraints in
orchestration/requirements.txt. Do not install it into the frozen core environment.
Use a Linux/WSL environment and an operator-chosen runtime path:

```sh
uv venv /absolute/airflow-venv --python 3.12
uv pip install --python /absolute/airflow-venv/bin/python -r orchestration/requirements.txt
export AIRFLOW_HOME=/absolute/airflow-state
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__CORE__DAGS_FOLDER=/absolute/nemo/orchestration
export NEMO_CORE_PYTHON=/absolute/nemo-core-venv/bin/python
export NEMO_PIPELINE_CONFIG=/absolute/config.json
/absolute/airflow-venv/bin/airflow db migrate
/absolute/airflow-venv/bin/python orchestration/check_dag.py
/absolute/airflow-venv/bin/airflow dags test nemo_canonical_pipeline -f /absolute/nemo/orchestration/nemo_pipeline.py
```

Use an absolute DAG file path; the validated Airflow version rejects a relative file
outside its resolved bundle path. The core interpreter must have the locked NEMO package
installed. Paths and config are trusted operator inputs, not user-submitted DAG params.

The DAG has publish → verify_publication dependencies, two retries with exponential
backoff, one active run and task timeouts of 30/5 minutes. Child execution is bounded
at 25 minutes and its process group is terminated on interruption/timeout. Only basic
runtime environment variables reach the child; scheduler credentials are not forwarded.
Failures propagate. The second task independently rechecks the published hashes.
No company data or credentials are read when parsing the DAG.

schedule=None and catchup=False are intentional. A production operator must define
arrival completeness, reporting windows, cadence, backfills, alerts and retention before
enabling an automated schedule. Repeated execution of a fixed config does not advance
its dates automatically.

## Recovery and limits

After a hard kill or power loss, a lock or pending directory may remain. First confirm
that the pipeline and its dbt subprocesses are no longer running, preserve failure logs
and previous publications, then remove only that abandoned lock/pending directory.
Never clear a lock merely because a retry encountered it.
A report-stage failure can leave a built warehouse; publication still fails atomically,
and the retry reuses the validated warehouse. Disk corruption and power-loss durability
are not solved by atomic rename; backup and restore policies are required.

The output root must be protected from untrusted concurrent edits. Hashes detect
consistency failures, not malicious authorship. SQLite Airflow metadata and local files
are a development validation setup, not distributed HA, tenant isolation or a deployment.
External connectors, alerts, secrets rotation, distributed storage and recurring schedules
remain operator/infrastructure work.

[Airflow installation](https://airflow.apache.org/docs/apache-airflow/stable/installation/installing-from-pypi.html)
and [public Task SDK](https://airflow.apache.org/docs/task-sdk/stable/api.html) are the
authoritative runtime references. See [learning guide](learning-orchestration.md).
