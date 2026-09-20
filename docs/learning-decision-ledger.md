# Learning guide — Decision Ledger

## Meaning
A decision ledger records the evidence available at review time, the intended action,
and subsequent human reports. It preserves what was known before later results arrive.

## Business purpose
Teams can distinguish a recommendation they declined from one they implemented.
Later outcome measurement can compare expectations with observations without rewriting
the original rationale. Marketing hypotheses, attribution and experimental evidence
keep their original evidence class.

## Example
A payment-stage hypothesis suggests investigating Android failures. An owner records
an expectation that reconciliation will identify affected payment attempts, accepts the
investigation, starts it, and reports completing it. This does not establish the cause,
prove improved conversion, or authorize a payment-system change.

## Formula
State at version n = apply(event n, state at version n - 1).
A successful new event increments the version by one. Each event hash is SHA-256 of
its canonical JSON envelope, including the preceding event hash. Matching retry keys
return the original receipt; conflicting reuse fails. Hashes detect accidental editing,
but a database owner could rewrite the entire chain. They are not signatures.

## Data requirements
Import an intact M11 opportunity report and select one opportunity. Preserve its full
report, source revision, evidence strength, blockers and bounded next step. Human
updates need an actor and rationale; acceptance needs an owner, an expected outcome
written as an assumption, and a UTC observation window with start before end.
An implementation report needs actual action text and a nonfuture occurrence timestamp.
Text expectations introduce no new numeric metric, money or profit definition.

## Implementation
A local SQLite append-only event table serializes writes in a transaction. Replay
validates the chain and lifecycle, producing the current decision and audit history.
Expected versions reject stale edits; request IDs support safe retries. Blocked items
cannot be accepted. New evidence requires a new report revision and a separately
reviewed decision. Stable opportunity IDs link those decisions. Planning fields freeze
when work starts; terminal decisions remain immutable.

## Failure modes
A source hash cannot authenticate the source. Actor and owner names are assertions,
not authenticated identities. Recorded implementation is not verified execution.
A retrospective observation window is not experimental preregistration. Accepted work
may still become stale; no live revalidation runs here. Changing evidence needs another
review. Local history is not a production multi-tenant approval or backup system.
Full replay favors simplicity and integrity checks over large-scale query performance.
Outcomes, differences and lessons stay null until a later measurement contract exists.

## Interview explanation
“I preserved the recommendation and evidence as an immutable snapshot, then used a
versioned event log for ownership, review and reported action. Transactions prevent lost
updates, retry keys prevent duplicate writes, and lifecycle rules preserve blockers.
The ledger tracks decisions; it does not upgrade attribution into causality or claim
that a reported action produced a business result.”
