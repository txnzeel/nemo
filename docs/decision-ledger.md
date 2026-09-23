# Decision Ledger — contracts and walkthrough

M12 consumes a saved M11 opportunity report. M11 derives that report from canonical
observations and ready warehouse models. The ledger stores the entire source report;
it does not need M1, private truth, a seed, a warehouse connection or a live connector
to replay decisions. Future company adapters still map into the canonical boundary.

## Record and evidence contract

Every decision includes decision_id, decision_case_id (nullable), created_at, problem,
evidence_available, evidence_quality, hypotheses, recommended_action, actual_action,
expected_outcome, confidence, owner, status, measurement_window, actual_outcome,
difference_from_expectation and lesson. Additional fields retain the opportunity ID,
source revision, blockers, version and update timestamp.

Decision IDs derive from dataset, opportunity ID and source revision. Importing that
revision twice is rejected unless it is an identical retry with the same request ID.
A new evidence revision produces a separately reviewed decision linked by opportunity
ID; it never silently modifies the earlier decision. The report revision is checked
against its canonical content hash. Hash validity is not source authentication.

Evidence strength and confidence retain M11's labels. A diagnostic hypothesis remains
a hypothesis; attribution remains model-dependent credit; conditional experimental
results retain their assumptions. Historical capped contribution is not forward value
or profit. No amounts are converted or recomputed. Expected outcomes and human
hypotheses are narrative assertions, not newly defined or calculated metrics.
Actual outcomes, differences and lessons remain null in M12.

## Lifecycle

| Current state | Allowed next states |
|---|---|
| proposed | accepted, rejected, cancelled |
| blocked | rejected, cancelled |
| accepted | in_progress, cancelled |
| in_progress | implemented, cancelled |
| implemented / rejected / cancelled | none |

Acceptance means a human commitment to review/do the bounded next step. It is not
spending, rollout or execution authorization. Import preserves blockers; no command
can remove them or edit the evidence. Resolve evidence prerequisites upstream, generate
a new M11 report and review its new decision separately.

Acceptance requires an owner, an expected outcome and a measurement window. The window
uses explicit UTC start_inclusive and end_exclusive timestamps with start < end. It is
a proposed observation window, not proof of experimental registration or full follow-up.
Retrospective recording is allowed and visible through ledger timestamps.

Before work starts, owner, expectation, window and human hypotheses may be amended.
They freeze when work starts. Every update requires actor, rationale and the exact
current expected_version. Implementation requires an actual_action object with a
description and UTC occurred_at no later than the ledger's recorded time.
Recording an action does not independently verify that it occurred or caused a result.
Cancellation can document partial work in its rationale; it does not claim completion.
Terminal records are immutable in M12. Corrections need a future explicit amendment
contract; never edit the SQLite database manually.

## Local API example

Use an existing report path from artifacts/milestone-11/index.json, or create one using
the M11 walkthrough. This example records a demonstration review, not a real action:

~~~python
import json
from pathlib import Path
from nemo.ledger import read, submit

index = json.loads(Path("artifacts/milestone-11/index.json").read_bytes())
board = json.loads(Path(index["payment"]["report"]).read_bytes())
database = Path("artifacts/ledger-demo/decisions.sqlite")
receipt = submit(
    database,
    {
        "operation": "import",
        "request_id": "payment-import-1",
        "actor": "demo reviewer",
        "rationale": "Demonstration: preserve the evidence for manual investigation.",
        "report": board,
        "opportunity_id": board["opportunities"][0]["opportunity_id"],
    },
)
decision = receipt["decision"]
receipt = submit(
    database,
    {
        "operation": "update",
        "request_id": "payment-accept-1",
        "actor": "demo reviewer",
        "rationale": "Demonstration commitment to investigate, not a verified root cause.",
        "decision_id": decision["decision_id"],
        "expected_version": decision["version"],
        "changes": {
            "status": "accepted",
            "owner": "demo payment analyst",
            "expected_outcome": "Identify evidence needed to explain payment failures.",
            "measurement_window": {
                "start_inclusive": "2026-09-22T00:00:00Z",
                "end_exclusive": "2026-09-29T00:00:00Z",
            },
        },
    },
)
print(json.dumps(read(database, decision["decision_id"]), indent=2))
~~~

Use a new request ID for every new command. An identical retry returns the original
receipt even if later events exist. Reusing a request ID with different content fails.
Fetch the latest decision before making a new update; stale versions fail without writes.
Subsequent updates use the same structure with changes.status = in_progress, then
changes.status = implemented plus changes.actual_action = {description, occurred_at}.

## CLI

Save an API command object above as a UTF-8 JSON file. Submit prints a JSON receipt;
read prints current decisions plus event history. Errors return exit code 1 and JSON
on stderr. Reading a missing database fails without creating it.

~~~powershell
.venv/Scripts/python.exe -m nemo.ledger --database artifacts/ledger-demo/decisions.sqlite submit --command artifacts/ledger-demo/command.json
.venv/Scripts/python.exe -m nemo.ledger --database artifacts/ledger-demo/decisions.sqlite read
~~~

Add --decision-id after read to select one decision. A filtered history retains global
sequence numbers and predecessor hashes; validate the full ledger for the complete chain.

## Persistence and production extension

SQLite BEGIN IMMEDIATE serializes writers; expected versions reject lost updates.
Commands, UTC recording times and preceding hashes form an append-only event chain.
Database triggers reject ordinary UPDATE/DELETE operations. Every read/write replays
the chain and validates versions, timestamps, hashes and lifecycle rules. Failed
commands append no events. Connection scopes close and transactions commit/roll back.

The implementation replays the full local ledger and stores full report snapshots.
This is suitable for the current local platform, not a claim of large-scale service
performance. An authenticated service could retain these contracts with indexed
projections, durable storage, access control and externally anchored audit receipts.
Those integrations, authentication, action execution and multi-tenant isolation are
future work. A privileged file owner can rewrite the entire chain or truncate its
tail; internal hashes cannot detect every such operation. Backups and external audit
anchoring are not implemented here. Database and generated records remain outside Git.

M13 adds explicit plan_outcome and record_outcome events; see [Outcome Measurement](outcomes.md).
These append a plan or measurement without reopening action states or rewriting old
records. Ordinary terminal-state updates remain forbidden. M14 will define how prior
lessons inform new decisions; outcome recording does not automate that reuse.
