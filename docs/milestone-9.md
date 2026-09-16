# Milestone 9 — Attribution Lab

## Outcome
Implemented first touch, last touch, linear, position based and time decay attribution
over the canonical M8 journey contract. Added exact per-order money allocation,
rational conversion credit, channel/campaign summaries and a standalone HTML comparison.
The comparison prominently states:

> Attribution is a model of credit assignment, not proof of causation.

See [contracts and commands](attribution.md) and the
[eight-part learning guide](learning-attribution.md).

## Architecture and scope
A new attribution.py module reads existing ready warehouse models and the M8 journey
report. No existing analytics, generator, dbt model, metric contract or recommendation
gate changed. Future adapters continue to normalize into the canonical source boundary.
There is no seed, private truth, generator object or production connector dependency.

The module verifies source binding between journey reconstruction and order amounts.
The evidence class is attribution_result. Credit covers paid tax-exclusive gross
merchandise before refunds; it does not establish incremental value or profit.

The UI is an offline comparison report, not a production application. Markov attribution,
causal inference, experiment design and budget recommendations are outside this milestone.

## Reference results
All five models reconcile 5,989 orders and 1,380,800,300 paise.
The common population has 322 history-boundary-limited windows and no empty or tied
windows. Model ranges on gross merchandise credit are:

| Channel | First touch, paise | Last touch, paise | Linear, paise | Position based, paise | Time decay, paise | Range, paise |
|---|---:|---:|---:|---:|---:|---:|
| Direct | 251713700 | 251254500 | 251322215 | 251393653 | 251745627 | 491127 |
| Organic Search | 424899800 | 425659200 | 425523708 | 425443510 | 426684279 | 1784479 |
| Paid Search | 704186800 | 703886600 | 703954377 | 703963137 | 702370394 | 1816406 |

These differences describe sensitivity to rules, not channel effectiveness. Local
artifacts are in artifacts/milestone-9; generated reports and warehouses stay outside Git.

## Numerical decisions
Largest-remainder paise allocation preserves every order total, including values beyond
floating-point exact-integer precision. Conversion credit is separate from integer money.
Empty paths retain all credit in an explicit unassigned bucket.

A full-data check exposed unbounded denominators when adding independently normalized
time-decay fractions. Version 1 therefore declares 24-decimal score and normalized-credit
resolution. A regression covers 810 different decay paths and bounded serialization.
The final weights are exact fractions of those declared units; exponential weighting
itself is numerically approximated.

## Validation
The complete suite contains 198 tests: 176 prior tests and 22 attribution cases.
Targeted cases cover hand-calculated models, short/repeated/tied paths, half-life
sensitivity, tiny weights, largest-remainder ties, very large/zero money, invalid
parameters, channel/campaign reconciliation, empty windows, source binding, future-touch
exclusion, escaped HTML, CLI output protection and blocked generator/private reads.

Ruff lint/format and wheel/source builds pass. The installed wheel reproduces the
complete reference JSON and HTML outside the checkout. The comparison page was rendered
in headless Chrome and visually inspected at 1440 × 1100. The in-app browser inspector
could not initialize because of a local sandbox helper failure.

The reference dbt build passes 11 models and 25 tests; source freshness, SQL compilation
and docs generation pass. No type checker is configured. Original M1 artifact/source
fingerprints and frozen M6 method/held-out scores remain protected by preservation checks.

```powershell
.venv/Scripts/python.exe -m pytest --tb=short
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv build --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
```

## Remaining limitations
No live company integration, identity stitching, causal ground truth or attribution
accuracy is verified. Time ties and incomplete paths remain explicit limitations.
Report memory usage grows with the full journey population. Source corrections can
restate allocations. Snowflake remains unverified from M3.

Next: Milestone 10 — Experimentation Engine, after the user says proceed.
