# Learning guide — Reliable orchestration

## Meaning, business purpose and example
Orchestration controls when work runs, what depends on what and how failures are handled.
A morning marketing report must not show a newly built case alongside yesterday's
measurement checks. NEMO publishes the whole report set together only after validation.

## Formula and data requirements
run_id = SHA256(canonical encoding of source manifest hash + comparison dates + method
hashes + runtime versions). Same validated inputs and method select the same publication.
Different source/method revisions get distinct identities. Inputs require complete
canonical observations, explicit dates, a writable protected output root and the locked
core runtime. Credentials are not needed for the canonical runner.

## Implementation
A temporary snapshot prevents later source edits from changing the files in a running
analysis. An exclusive lock gives one writer per output. Reports and their checksums
are staged, verified and renamed atomically. Airflow's publish task calls this runner;
verify_publication checks the result independently. Retry means re-execute safely,
not duplicate business effects.

## Alternatives and trade-offs
Cron can launch commands but lacks native dependency state and retry visibility.
A single transactional database could manage publications but adds schema and operational
complexity. Immutable directories are inspectable and appropriate for the current local
platform; distributed object storage needs different commit/locking semantics.

## Failure modes and statistical limits
Partial writes, stale locks, quota, timeouts and changed inputs must not appear as a
successful fresh report. Hash identity is not source authentication. A successful job
does not establish complete data, statistical significance or causal validity.
The existing measurement gates remain responsible for analytical limitations.

## Five interview questions and strong answers
1. What is idempotency here? A validated repeated run returns the same report identity
   without appending duplicate output, while still checking source and warehouse readiness.
2. Why copy observations? To analyze one coherent checksummed snapshot rather than a
   moving source directory. Failed checksum validation blocks publication.
3. Why verify after publish? It independently checks that the declared immutable artifact
   actually exists with its expected contents.
4. Why not clear stale locks automatically? A slow or disconnected writer may still be
   active. Manual process verification avoids concurrent corruption.
5. Is an Airflow DAG a production deployment? No. We ran a real local DAG, but HA,
   access control, storage, alerting and scheduling policy remain deployment responsibilities.

## Interview explanation
“I separated deterministic analytical work from orchestration. Airflow retries a bounded
command; immutable publication and source/method identity make that retry safe. I tested
partial failure and replay, not just whether the happy-path DAG parses.”
