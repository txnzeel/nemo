# Learning guide — Grounded Evidence Analyst

## Meaning and purpose
A grounded explanation selects and presents existing evidence with references.
It helps reviewers understand a Decision Case without allowing an LLM to become a
second metric engine or to turn a hypothesis into a cause.

## Example and formula
A payment-stage case can state the existing current paid-order count, measurement
confidence and supported investigation, followed by a mandatory causal limitation.
Every displayed statement has a source JSON pointer and case revision.
The grounding invariant is displayed_statements ⊆ validated_evidence_statements.
The model selects statement IDs; deterministic code supplies their text.

## Data and implementation
The input is a versioned Decision Case produced from canonical observations/warehouse
models. Hash checks detect accidental revision changes, not malicious authorship.
An evidence pack contains allowlisted aggregate facts, no customer rows or private truth.
The default deterministic mode performs no model call and is explicitly labelled.

An optional OpenAI Responses request uses a strict JSON schema of allowed fact IDs.
The operator supplies a compatible model and explicitly opts into sending aggregate
evidence. Credentials remain in OPENAI_API_KEY; they are never serialized in results.
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
constrains response shape; local validation still checks membership, duplicates, completeness
and refusal. The renderer always restores the finding, measurement caveat and action limit.

## Failure modes and trade-offs
Invented IDs, extra prose, modified evidence packs, incomplete responses and refusals
fail closed. The model cannot invent a number or silently omit the evidence boundary.
Selection can still be irrelevant; usefulness needs real model evaluation before making
quality claims. Template-based text is intentionally narrower than unconstrained chat.
No causal explanation, recommendation execution or financial advice is generated.

## Interview explanation
“I separated evidence calculation, AI selection and deterministic rendering. The model
returns IDs, not new claims. Every statement is traced to an immutable case revision,
and mandatory caveats survive even adversarial selections. Offline mode is clearly
labelled so passing local tests never masquerades as a verified live AI integration.”
