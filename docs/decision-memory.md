# Decision Memory

M14 adds auditable historical review context beside a new conversion Decision Case.
The existing detector is unchanged. No model training, causal inference, automatic
action, evidence-strength upgrade or recommendation override occurs.

Use decision_memory.build_with_memory(warehouse, observations, ledger,
baseline_start=..., current_start=..., as_of=..., limit=10), or:

~~~bash
python -m nemo.decision_memory --warehouse current.duckdb --observations observations --ledger decisions.sqlite --baseline-start 2025-01-09 --current-start 2025-01-13 --as-of 2026-09-25T00:00:00Z --output new-case.json
~~~

The output has the original case and a separate memory report with immutable evidence
references and review questions. Existing output files are not overwritten. as_of is
an explicit UTC knowledge cutoff and cannot precede the case's observation end.

Retrieval first validates ledger integrity, then replays only events at or before the
cutoff. The provenance records that visible prefix, not later events. The latest known
decision revision per opportunity is selected before eligibility filtering; a later
unresolved revision cannot cause an older successful result to reappear.

Eligibility requires the same declared dataset and source mode, a cvr plan, and a prior
outcome window ending no later than the new case's baseline start. Whole-dataset
histories and histories for a currently supported device are eligible. Channel- or
campaign-filtered histories are excluded, since the current diagnostic case has no
equivalent filter scope. Missing outcomes, other metrics and overlapping windows are
reported as exclusions. Unknown outcomes remain unknown.

Order is most recent prior window end, then stable decision ID. The limit is 1–100;
eligible and returned counts expose truncation. Revisions are not independent trials,
and frequency or target attainment is not a success probability.

The local manual canonical demonstration uses an earlier measured outcome and a new
period with no observations. Memory retrieves one prior result but leaves the current
case's insufficient-data/measurement finding unchanged. An earlier audit cutoff
retrieves no outcome. These are manual fixtures, not real company integrations.
See [the learning guide](learning-decision-memory.md).

The M13 Ubuntu validation environment remains applicable. Windows DuckDB is still
blocked by Smart App Control; M6's old Windows compiler fingerprint is not relabelled
as Linux verification. Current code/dbt/dependency fingerprints remain unchanged.
