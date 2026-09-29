# Milestone 23 — Grounded Evidence Analyst

Implements cited explanations of observational Decision Cases with a deterministic
renderer and an optional, explicitly opted-in OpenAI evidence-selection client.
The API/web default is labelled deterministic_no_model and makes no provider call.
See [contract and commands](analyst.md) and [learning guide](learning-analyst.md).

## Architecture and evidence

The Analyst consumes the existing versioned Decision Case, which is produced from
canonical observations and warehouse models. It has no generator, seed, configuration
or private truth dependency. Future source adapters feed the same canonical contracts.
No frozen analytical implementation, metric semantics or money representation changed.

A hash-checked evidence pack contains allowlisted findings, aggregate counts, exact
integer-paise receipts and measurement confidence. Every displayed statement carries
a source pointer and case revision. Optional model output contains only statement IDs;
local code rejects invented IDs, duplicates, extra prose, incomplete output and refusals.
Finding, measurement and causal/action boundaries cannot be removed by selection.
Hash checks establish consistency, not source authenticity. This is a constrained
explanation service, not freeform chat, new analysis or an action executor.

## Verification

- Full configured Python suite: 443 passed in 545.23 seconds, with the existing
  Starlette/httpx test-client deprecation warning. API extra installed; no test skips.
- Twenty Analyst cases cover manually authored canonical inputs, deterministic focus
  selection, citations, revision tampering, model-output rejection, mandatory caveats,
  exact values above 2^53, ignored source-text instructions and mocked provider transport.
- The existing API read-service parameterization now includes the authenticated Analyst
  route. Existing M1/M2 and downstream regression tests continue to pass.
- Ruff lint and format check pass (129 Python files). Four Node tests, ESLint,
  Prettier and the Next production build pass. No type checker is configured.
- Wheel and sdist build successfully. Installed-wheel execution reproduces the saved
  explanation from the manual case. Archive checks exclude credentials, generated
  artifacts, private truth and local runtimes. M1 hashes, M6 frozen code/dbt/dependency
  fingerprints and M12 ledger replay remain intact.
- The full regression suite runs actual dbt builds and SQL checks, including failure
  propagation and stale-source detection. No dbt models changed in M23.
- Browser inspection verified the public lab Analyst view: nine cited statements,
  explicit no-model/no-live-API labels and a visible causal/action boundary. A screenshot
  is saved locally under artifacts/milestone-23/evidence-analyst.png, outside Git.

## Material limitations

No live OpenAI request or model-quality evaluation was performed. The provider transport
and response contract are tested offline. A compatible model, authorized credential and
explicit aggregate-evidence transfer opt-in are needed before external verification.
Selection relevance, provider availability and actual costs are unverified.

The web visual check uses labelled public lab exports. Authenticated Next-to-API browser
verification remains pending from M22: automatic approval review blocked launching Next
with the local API credential, reporting only 'blocked by policy'. No workaround was
used. Windows native DuckDB is still blocked; Python validation ran in Ubuntu WSL.

## Next milestone

M24 concerns Google integrations and separate live verification as authorized credentials
become available. It has not started. Per the current repository workflow, stop after
publishing M23 and wait for the next proceed request.
