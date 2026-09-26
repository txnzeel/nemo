# Learning guide — API Product Layer

## Meaning and business purpose
An API gives the web product and integrations a typed way to request existing analyses.
It is a transport and authorization boundary, not a second analytics engine.
The business benefit is consistent definitions and evidence across interfaces.

## Example and flow
Request -> authenticate -> resolve configured dataset -> validate parameters ->
existing canonical service -> versioned evidence response.
A conversion case returned over HTTP retains its measurement blockers and observational
claim. A POST scenario computes assumptions; it does not execute advertising changes.
HTTP success means the request succeeded, not that an economic recommendation is valid.

## Data requirements and architecture
Operators configure dataset IDs with public observation/warehouse locations and optional
experiment/ledger resources under an allowed root. Clients never submit arbitrary paths
or SQL. Existing services enforce canonical hashes, ready warehouses and metric semantics.
Optional FastAPI/Uvicorn dependencies keep the core CLI usable without a web server.

## Authorization and implementation
Use bearer credentials loaded from environment/configured server arguments, constant-time
comparison and separate read/write privileges. Tokens identify local service roles, not
an enterprise identity provider. Bind localhost by default; deployment authentication,
TLS and tenant isolation require separate review. Do not log tokens or raw customer data.
Typed request validation, bounded fields, generic safe errors and request identifiers
make failures explainable without exposing filesystem details.
FastAPI exposes bearer authentication through its dependency system:
[official security reference](https://fastapi.tiangolo.com/reference/security/).

## Formula and exact representation
The transport invariant is API_value = existing_service_value for the same canonical
inputs and parameters. For a descriptive conversion rate, the existing service returns
purchasing_sessions / observed_sessions; the endpoint does not redefine either count.
Integer paise and exact numerator/denominator objects survive JSON serialization.
Browser clients need a lossless integer parser for values above 2^53.

## Practical implementation and verification
Follow [API setup and route contracts](api.md). A manually authored canonical fixture
is built into the warehouse, served over HTTP, and compared with the direct Python
Decision Case result. No seed or generator object is needed. Tests exercise read-only
credentials, ledger retries, stale versions, bounded bodies and sanitized failures.

## Failure modes
A valid token can still have the wrong role. A valid dataset ID can reference stale data.
A content hash does not authenticate its author. Concurrent decision updates need the
ledger's expected version; retries need stable request IDs. APIs must not bypass those
controls. Missing services are unavailable, never replaced by invented demo answers.

## Alternatives and trade-offs
Reusing service functions preserves definitions; implementing calculations again in
endpoints would drift. Configured dataset IDs constrain access more clearly than raw
paths. A local authenticated API is useful before enterprise deployment, but does not
establish production security or multi-tenant isolation.

## Interview questions and answers
1. Why FastAPI? Typed HTTP contracts and documentation around existing Python services.
2. Where are metrics computed? Existing canonical services and SQL, not route handlers.
3. What prevents arbitrary data access? Server-configured IDs, path containment and no SQL endpoint.
4. How are writes safe? Role checks plus unchanged ledger lifecycle/concurrency/idempotency.
5. Does API exposure change evidence strength? No; hypotheses and conditional scenarios
   remain explicitly distinct from causal evidence and action authorization.
