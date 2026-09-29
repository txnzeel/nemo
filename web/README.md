# NEMO web workspace

Node 24+ is required for exact JSON numeric-token parsing. From this directory:

```sh
npm ci
npm run lint
npm run format:check
npm test
npm run build
npm run start
```

Set NEMO_READ_TOKEN in the server process environment and optionally NEMO_API_URL
(default http://127.0.0.1:8000). Use the read-only token from the local FastAPI service.
Never use NEXT_PUBLIC for credentials. The UI binds 127.0.0.1:3000 and accepts local
same-origin requests only. It does not provide enterprise identity or tenant isolation.
No ledger writes, advertising changes or external model calls originate from this UI.

## Explicit lab preview

With the M5 public lab observations and warehouses prepared (see docs/milestone-5.md),
run from the repository root in the verified Python environment:

```sh
python web/scripts/export_demo.py
```

Then from web, run npm run build followed by npm run demo. The preview binds
127.0.0.1:3002 and displays a public-lab-export label. It is opt-in, never an automatic
fallback from a failed API. Reports are generated from the unchanged canonical services.
The empty preview ledger is explicitly empty; it does not imply historical actions.
Generated JSON stays ignored under web/demo. No source rows, private truth, credentials
or externally sourced company data are copied.

## Scope and evidence

Decision Cases, measurement checks, opportunities and ledger records are read-only.
Missing or blocked evidence remains visible. Exact integer tokens become strings before
reaching the browser; BigInt formats counts/paise and rounds only displayed percentages.
Expandable evidence retains the exact ratios, contracts and revision hashes.
Dataset origin labels are declarations, not independently verified provenance.

The proxy accepts a fixed route allowlist and dataset IDs, not user-supplied API URLs,
paths or SQL. Its API mode has a 60-second upstream timeout and sanitizes service errors.
Local operator access is assumed; do not expose this service publicly as-is.

ESLint is pinned to 9.39.5 because ESLint 10.11.0 failed with the Next 16.3.6 parser
(scopeManager.addGlobals). This development-tool compatibility limitation is separate
from the zero-vulnerability npm audit observed at implementation time. No framework
TypeScript check is claimed for this JavaScript application.
