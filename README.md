# NEMO

**From fragmented signals to measurable decisions.**

Nexus for Engagement, Measurement & Optimization: an evidence-driven Growth Decision
Intelligence Platform in development. NEMO's intended output is an auditable Decision
Case, linking trustworthy observations to evidence, actions, and measured outcomes.

**Current status: Milestone 9 — Attribution Lab.** Canonical source contracts,
a dbt/DuckDB warehouse and acquisition metrics are implemented alongside the reference
synthetic producer. Snowflake configuration is prepared but not live-verified.
Purchase reconciliation and dependency-specific recommendation gating are implemented.
Observation-only Decision Cases now propose bounded manual investigations.
Causal estimates, budget optimization, web UI and AI remain future work.

## Run locally

Requires Python 3.12+ and uv. The reference interpreter is pinned in `.python-version`;
dependency versions are locked in `uv.lock`.

```powershell
uv sync --locked
uv run nemo --output artifacts/demo --lockfile uv.lock
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The default world covers 2025-01-01 through 2026-06-30, using INR integer paise and
Asia/Kolkata business dates. All events are timestamped in UTC. To generate a small run:

```powershell
uv run nemo --start 2025-01-01 --end 2025-01-15 --seed 42 --output artifacts/small --lockfile uv.lock
```

`--end` is exclusive. Use a new output path for each run: the CLI refuses to overwrite
an existing directory. No credentials or network calls are needed during generation.

On the initial Windows workspace Python is installed in `.tools/python` rather than
on PATH. Equivalent setup/execution using that project-local interpreter:

```powershell
uv python install 3.12.13 --install-dir .tools/python --cache-dir .tools/uv-cache --no-bin --no-registry
uv sync --locked --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
.venv/Scripts/nemo.exe --output artifacts/demo --lockfile uv.lock
.venv/Scripts/python.exe -m pytest
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
```

## What is generated

Linked customers (synthetic visitors), products, campaigns, daily advertising aggregates,
sessions, ordered funnel events, paid orders, order lines, and timed partial/full refunds.
Advertising clicks constrain paid landing sessions; payment success creates orders;
line totals reconcile exactly; refunds never exceed their paid line quantities/amounts.

Outputs:

- `observations/*.jsonl`: nine source tables, one JSON record per line.
- `observations/manifest.json`: synthetic label, schema, units, row counts and SHA-256 hashes.
- `private/run.json`: full configuration, generator source hashes, Python version, and
  optional dependency lock fingerprint. Do not give this directory to future analytics.

This is a deliberately simple healthy world with weekly traffic variation and repeat
visitors. There are no planted incidents or hidden-truth evaluation results yet.
Reproducibility requires the same source, config and runtime; it is not evidence of
real-world realism. Amounts exclude tax, shipping, discounts, fees and cost of goods.
They must not be described as profit or contribution.

## Design and learning

- [Product contract and architecture decisions](docs/product-contract.md)
- [Synthetic model, entity grains, formulas, limitations, and acceptance criteria](docs/synthetic-business.md)

Tests include the default 18-month world, multiple seeds, event and money invariants,
zero traffic, failed payments, refund boundaries, subprocess reproducibility, output
checksums, invalid inputs, and safe failure/overwrite handling.

Implementation advances one milestone at a time after user instruction.
[Milestone 1 verification report and interview guide](docs/milestone-1.md)

## Acquisition measurement

The measurement CLI consumes the public observations directory only:

```powershell
uv run nemo-measure --observations artifacts/demo/observations --group-by "channel,campaign_id,device" --output artifacts/acquisition.json
uv run nemo-measure --registry --output artifacts/metric-registry.json
```

For the project-local Windows installation, use `.venv/Scripts/nemo-measure.exe`.
After pulling this milestone, run `uv sync --locked` (or the project-local sync command
above) to register that entry point. The locked environment now includes DuckDB and dbt-duckdb.

Optional filters: `--start YYYY-MM-DD`, `--end YYYY-MM-DD` (exclusive),
`--channel paid_search`, `--device android`, and `--campaign-id campaign-brand`.
Supported grouping dimensions: business_date, channel, campaign_id and device.
Output parents must exist and output files must be new; omit --output for JSON on stdout.

The report includes one versioned registry, grouped results and totals, integer
numerators/denominators, units, null reasons, limitations, and input/code fingerprints.
Money is paise (100 paise = ₹1); rate values are fractions (0.05 = 5%).
Ratio values are six-place decimal strings, avoiding implicit binary floating-point
rounding in the authoritative output.

Full CAC is unavailable because only media costs exist. Media-only CAC is explicit.
New customers are first-observed paying buyers, not every synthetic visitor. Reported
ROAS uses only paid-session revenue, before refunds; it is not profit or incrementality.
Structural input checks do not establish measurement confidence: health is not_assessed.

- [Metric learning contract, definitions and scope](docs/metric-registry.md)
- [Milestone 2 verification and interview guide](docs/milestone-2.md)



## Warehouse-backed measurement (Milestone 3)

Build a persistent canonical warehouse, then query it repeatedly:

```powershell
uv sync --locked
uv run nemo-warehouse build --observations artifacts/demo/observations --database artifacts/warehouse/nemo.duckdb
uv run nemo-measure --warehouse artifacts/warehouse/nemo.duckdb --output artifacts/warehouse-report.json
uv run nemo-warehouse freshness --database artifacts/warehouse/nemo.duckdb
uv run nemo-warehouse compile --database artifacts/warehouse/nemo.duckdb
uv run nemo-warehouse docs --database artifacts/warehouse/nemo.duckdb
```

The Windows project-local equivalents are .venv/Scripts/nemo-warehouse.exe and
.venv/Scripts/nemo-measure.exe after the README's explicit-interpreter sync.
DuckDB and dbt-duckdb are locked runtime dependencies. The --observations measurement
API remains compatible but builds a temporary dbt warehouse; --warehouse avoids that
repeat work. Existing reports are not overwritten.

Canonical schema 2 supports declared dataset/channel/device metadata independently of
M1. Schema 1 retains backward compatibility. “production” is a source-provenance label,
not a claim that any external connector is operational.

- [Source architecture and production extension point](docs/source-architecture.md)
- [Warehouse grains, incremental semantics, freshness and Snowflake status](docs/warehouse.md)
- [Milestone 3 validation and interview guide](docs/milestone-3.md)

Snowflake is **not live-verified**. Optional adapter dependencies and deployment templates
exist; no account resources or grants were created. The local warehouse is fully runnable
without commercial credentials. Next: Milestone 10 after **proceed**.

## Measurement integrity
Canonical purchase events reconcile to paid orders under an explicit public contract.
Missing or duplicated tracking lowers purchase-tracking confidence and suppresses
dependent candidate recommendations. Existing order-based metrics remain observable.
Confidence describes the declared checks only; media, causal and economic prerequisites
remain unassessed.

The verified lab scenario drops 36 Android purchases while retaining all 5,989 paid
orders. Healthy and failure reports are in artifacts/milestone-4. The detector never
reads the separately stored injection truth.

    .venv/Scripts/python.exe -m nemo.integrity --observations artifacts/milestone-4/failure/observations
    .venv/Scripts/python.exe -m nemo.measurement --warehouse artifacts/milestone-4/failure/nemo.duckdb --integrity-observations artifacts/milestone-4/failure/observations

Warehouse reports require matching integrity observations for assessment. Without them,
health stays not_assessed. Observation-based reports assess automatically when the
public contract is available. Assessment scope is the complete snapshot, even for a
filtered report.

See [Milestone 4 contracts, validation and interview guide](docs/milestone-4.md).

## Decision Cases and learning guides
Milestone 5 compares adjacent session cohorts, applies a declared investigation rule,
decomposes the purchasing-session change, and checks device payment-stage evidence.
The controls distinguish healthy data, tracking loss and a planted Android payment problem.
Cases preserve source/method fingerprints and immutable revisions; they do not establish
a causal deployment failure or incremental profit.

    .venv/Scripts/python.exe -m nemo.decision_case --warehouse artifacts/milestone-5/business/nemo.duckdb --observations artifacts/milestone-5/business/observations --baseline-start 2026-06-03 --current-start 2026-06-17 --output-directory artifacts/milestone-5/business/cases

- [Learning guide: anomaly rules, decomposition, payment evidence and Decision Cases](docs/learning-decision-cases.md)
- [Learning lab: reproduce cases, trace code and check the arithmetic](docs/learning-lab-walkthrough.md)
- [Milestone 5 architecture, contracts, tests and limitations](docs/milestone-5.md)

The latest demonstration cases are indexed in artifacts/milestone-5/index.json.
Stop before Milestone 10 until **proceed**.

## Milestone progress
This table and the linked reports are updated with each verified milestone.

| Milestone | Status | Report |
|---|---|---|
| 0 — Product and evidence contract | Documented | [Product contract](docs/product-contract.md) |
| 1 — Synthetic Business Core | Complete | [M1](docs/milestone-1.md) |
| 2 — Acquisition Measurement | Complete | [M2](docs/milestone-2.md) |
| 3 — Warehouse Foundation | Local complete; Snowflake remains unverified | [M3](docs/milestone-3.md) |
| 4 — Measurement Integrity | Complete | [M4](docs/milestone-4.md) |
| 5 — First Decision Case | Complete | [M5](docs/milestone-5.md) |
| 6 — Blind Evaluation Harness | Complete | [M6](docs/milestone-6.md) |
| 7 — Customer Economics | Complete | [M7](docs/milestone-7.md) |
| 8 — Journey Reconstruction | Complete | [M8](docs/milestone-8.md) |
| 9 — Attribution Lab | Complete | [M9](docs/milestone-9.md) |
| 10 — Experimentation Engine | Next; awaiting proceed | Not started |

Current validation: 198 tests pass, with Ruff, dbt and package verification.
Generated demonstration data, warehouse files and private lab truth remain local;
the reports and learning guides include commands to reproduce them.

## Blind Lab and evaluation learning guide
The M6 harness freezes the detector, seals canonical-only predictions and dbt receipts,
then scores them against private truth. The verified recipe contains 27 checkpoints
from three independent worlds: 25/27 diagnoses match, with two early payment misses
retained and explained. Held-out results are 9/9 on one world, not a production guarantee.

- [Blind Lab architecture, metrics and reproducible commands](docs/blind-evaluation.md)
- [Learning guide: holdouts, confusion, false positives and detection delay](docs/learning-blind-evaluation.md)
- [Milestone 6 results and detector limitations](docs/milestone-6.md)

    .venv/Scripts/python.exe -m nemo.blind_lab score --root artifacts/milestone-6 --split held_out

The full prepare/predict/score workflow is documented for a new output directory.

## Customer economics and learning guide
M7 adds first-observed buyer cohorts, calendar-month purchase retention, historical
net merchandise value and scoped contribution before acquisition costs and fixed
overhead. Incomplete periods and missing refund/cost coverage remain unknown.
The original source has no costs; a separate, explicitly labelled assumed-cost demo
exercises contribution without presenting it as real company profit.

- [Customer economics contracts and practical walkthrough](docs/customer-economics.md)
- [Learning guide: cohorts, retention, historical value and contribution](docs/learning-customer-economics.md)
- [Milestone 7 implementation, verification and limits](docs/milestone-7.md)

    .venv/Scripts/python.exe -m nemo.economics --warehouse artifacts/milestone-7/refunds_only/nemo.duckdb --observations artifacts/milestone-7/refunds_only/observations --max-age 18

The full reproduction commands, including an explicitly assumed-cost control, are
in the walkthrough. Generated data and private lab assumptions remain outside Git.

## Journey reconstruction and learning guide
M8 reconstructs observed session paths before each paid order, preserving channel,
campaign and device detail under a versioned lookback contract. Reports include
touch counts, exact elapsed time, path frequency, prior-channel appearances and
channel combinations, with history and timestamp-order uncertainty flags.
Identity uses supplied canonical customer IDs. No attribution or causal credit is assigned.

- [Journey contracts and practical commands](docs/journeys.md)
- [Learning guide: observed journeys, identity and descriptive assists](docs/learning-journeys.md)
- [Milestone 8 architecture, results and validation](docs/milestone-8.md)

    .venv/Scripts/python.exe -m nemo.journeys --warehouse artifacts/milestone-8/nemo.duckdb --lookback-days 30

The verified reference has 5,989 paid-order paths, including 592 multi-touch windows.
Milestone 9 is implemented below.

## Attribution Lab and learning guide
M9 compares first touch, last touch, linear, position based and time decay credit on
the same canonical journeys. Every model conserves gross merchandise paise per order.
A standalone comparison page highlights channel disagreement and history limitations.

**Attribution is a model of credit assignment, not proof of causation.**

- [Attribution contracts and practical commands](docs/attribution.md)
- [Learning guide: model assumptions, exact allocation and disagreement](docs/learning-attribution.md)
- [Milestone 9 results, verification and limitations](docs/milestone-9.md)

    .venv/Scripts/python.exe -m nemo.attribution --warehouse artifacts/milestone-9/nemo.duckdb --output artifacts/milestone-9/new-report.json --html artifacts/milestone-9/new-comparison.html

No causal lift, profit, ROAS or budget recommendation is inferred from attribution.
Milestone 10 awaits **proceed**.
