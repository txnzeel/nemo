# Evidence Analyst contract

M23 explains a schema-1 observational Decision Case through a small, validated evidence
pack. It adds no metric, attribution model or causal inference. The API and web view
use deterministic selection and display that mode explicitly.

## Data path

Canonical observations / warehouse → Decision Case → evidence pack → statement
selection → deterministic renderer → cited explanation.

The pack accepts existing finding classes, measurement confidence and baseline/current
sessions, paid orders and merchandise receipts. Numbers remain exact nonnegative int64
values or unknown; receipts are stated in integer paise. Arbitrary case text, customer
rows, source credentials, generator internals and private lab truth are not included.
The existing Decision Case revision is checked. Each statement includes a JSON pointer
to that case, with case and pack revisions in the result. Hashes prove consistency,
not authenticity; the operator remains responsible for source provenance.

## Local use

Run from the locked repository environment with an existing public Decision Case:

```sh
uv run python -m nemo.analyst --case /path/to/case.json --focus summary --output /path/to/explanation.json
```

Supported focus values are summary, measurement and next_step. The output directory
must already exist. Default mode is deterministic_no_model. The authenticated read route
GET /datasets/{id}/analyst?focus=summary builds the configured case and explains it locally.
It never invokes an external model. The Evidence Analyst tab uses this same default
contract, or explicitly labelled public lab exports when running the demo.

## Optional model selection

An operator may set OPENAI_API_KEY locally and invoke the CLI with an explicitly chosen
compatible model plus --allow-external-evidence. That flag authorizes transmission of
the pack's aggregate statements to OpenAI for that invocation. No default model or
credential is supplied. Do not place keys in arguments, repository files or screenshots.
No real provider request was made during milestone verification.

The fixed HTTPS Responses endpoint receives store=false and a strict JSON schema whose
only field is fact_ids. No freeform prose is rendered. Local validation rejects unknown
IDs, duplicates, extra fields, refusals and incomplete output. Requests have a 45-second
timeout, a 128 KiB response limit and no redirects. Provider failures produce sanitized
errors. store=false does not promise zero provider retention; review the applicable
provider data controls before transmitting company evidence.

Finding, measurement confidence and the causal/action boundary are mandatory even if
selection omits them. Model selection can still be irrelevant: local contract tests do
not establish live model usefulness, quality, availability or cost.

## Scope limits

This is a constrained evidence explanation surface, not conversational analytics.
It cannot calculate new metrics, determine causes, execute recommendations or turn
merchandise receipts into profit. New Decision Case evidence classes need an explicit
contract update. The CLI accepts operator-supplied case files; it is not an authenticity
or authorization boundary for untrusted uploads.

See the [learning guide](learning-analyst.md) and [milestone report](milestone-23.md).
