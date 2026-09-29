# Milestone 22 — Web Product

Implements a Next.js Decision Case workspace with source selection, observed metric
comparisons, device payment evidence, competing explanations, provenance, measurement
checks, opportunity review and a read-only ledger. See [learning guide](learning-web.md)
and [startup instructions](../web/README.md).

## Boundaries
The API proxy keeps the read credential server-side and allows only configured dataset
IDs and fixed read routes. Integer JSON tokens become strings without Number precision
loss; display formatting uses BigInt. The UI introduces no new metrics or causal claims.

An explicit local preview reads public lab report exports computed by existing canonical
services. It is labelled, credential-free, read-only and never substitutes for failed API
calls. Generated exports remain ignored. Production API mode remains independent of lab
generation and supports registered canonical datasets.

Python sdist inclusion is now explicit: source, tests, docs and project metadata.
The separately locked web project and its local dependencies/builds stay outside Python
distributions. No frozen analytical code or dependency versions changed.

## Verification
The complete Python suite passed 422 tests in 610.54 seconds with one known Starlette
test-client deprecation warning. Four Node tests verify int64 precision, undefined ratios,
proxy route restrictions and browser host/origin checks. ESLint, Prettier and the Next
production build pass. npm audit reported zero vulnerabilities in this lockfile.

Browser checks verified the payment-stage, healthy and measurement-failure cases,
opportunity and empty-ledger views, desktop/mobile presentation, source-preserving refresh
and repeated active-tab navigation. Screenshots are saved outside Git under
artifacts/milestone-22. Disconnected API mode shows an explicit error and no invented data.

The Python wheel/sdist and installed-wheel reproduction were verified separately,
including M1 hashes, M6 frozen code/dbt/dependencies and M12 replay. Existing dbt/SQL
coverage passes in the regression suite; no dbt models changed.

## Material limitations
The user-started authenticated Next process successfully returned the API dataset catalog,
but final authenticated browser rendering remains unverified: a stale build needed a
restart, and automatic approval review blocked subsequent credential-bearing launches.
The full visual checks above use explicitly labelled public lab exports. No public
deployment or enterprise authentication is claimed.

ESLint 9.39.5 is pinned because ESLint 10.11.0 failed with this Next parser. The deprecated
development-tool pin needs revisiting when compatibility is available. This JavaScript
frontend has no standalone type checker. Windows native DuckDB remains blocked; Python
validation uses Ubuntu WSL.

## Next
Continue the authorized batch with M23's grounded Analyst. External provider verification
will be distinct from deterministic local evidence rendering.
