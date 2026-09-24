# Milestone 14 — Decision Memory

Adds explicit, auditable retrieval of prior conversion outcomes beside a new Decision
Case. The original case, diagnosis, recommendations and evidence gates remain unchanged.

See [contracts and commands](decision-memory.md) and the
[eight-part learning guide](learning-decision-memory.md).

## Boundaries
Memory consumes the audited ledger and canonical Decision Case contracts. It never
reads generator parameters, seeds or private truth. Same-dataset/source identity,
compatible metric/device scope, nonoverlapping observation windows and an explicit
knowledge cutoff control eligibility. Source adapters remain canonical ingestion work.

The latest known decision revision is chosen per opportunity before filtering, preventing
old successes from displacing newer unresolved histories. Misses and unresolved outcomes
remain visible. Results retain full evidence/lesson references and generate review
questions, not causal conclusions or automatic actions. Other case/metric families and
learned retrieval remain future work.

## Demonstration
A manually authored canonical source produces an earlier measured outcome. A new case
uses a later period with no observed activity. Memory supplies one relevant prior result,
but the new case's insufficient-data/measurement assessment is unchanged. A cutoff
before outcome recording supplies zero results. This is a contract demonstration,
not a live company integration.

Artifacts are indexed under artifacts/milestone-14 and excluded from Git.

## Validation
Thirteen new tests pass, covering audited cutoffs, incompatible sources/populations,
overlapping windows, unresolved results, revision deduplication, invalid inputs, CLI
overwrite protection and exact preservation of the underlying case.
The complete suite passes: 327 tests in 446.54 seconds, including existing M1/M2 tests.

Ruff lint/format and package build/content checks pass. The installed wheel reproduces
the complete demonstration envelope outside the checkout. M1 hashes, M6 code/dbt/
dependency fingerprints and exact M12 ledger replay are preserved. No type checker is
configured.

The demonstration passes 11 dbt models and 25 tests, compile and docs generation.
Its empty campaign/ad-performance tables retain their two expected full-freshness
errors; the three populated sources pass. No rule was weakened.

Verification uses approved Ubuntu WSL, Python 3.12.13 and the existing lockfile.
The Windows DuckDB block remains unchanged. Historical M6 Windows held-out scoring
is not rerun under Linux's different compiler fingerprint; its frozen code is unchanged.

M15 — Search Intelligence is next. Following the repository's current one-milestone
workflow, it starts after the next proceed instruction.
