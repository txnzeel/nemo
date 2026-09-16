# Attribution Lab contracts and walkthrough

**Attribution is a model of credit assignment, not proof of causation.**

Read [the learning guide](learning-attribution.md) before interpreting model outputs.

## Source and population
nemo.attribution reads the ready canonical warehouse through the existing M8 journey
contract. Each paid order has an independent inclusive window, default 30 elapsed days.
Touches are observed session starts for the supplied canonical customer ID. Campaigns
and channels come from canonical observations; no provider-specific fields or generator
internals are read. Repeat-order windows can reuse touches.

Order amounts and the journey report must have the same source-manifest fingerprint.
Changing warehouse state between reads fails the report. The input is the existing
canonical tax-exclusive paid merchandise amount, in INR integer paise. No refunds,
costs, spend or additional revenue semantics are inferred.

## Model contracts, version 1
| Model | Session credit |
|---|---|
| First touch | 100% to earliest included session |
| Last touch | 100% to latest included session, including Direct |
| Linear | 1/n per included session |
| Position based | One touch: 100%; two: 50/50; three or more: 40% each endpoint, 20% divided among interior touches |
| Time decay | Normalize half-life weights; default 7 elapsed days |

Time decay uses age differences relative to the latest touch, which preserves normalized
ratios. Scores are computed at 50-digit Decimal precision and rounded half-up to 10^-24
units. Normalized credit is apportioned into 10^24 units using largest remainders, then
represented as exact fractions. This keeps aggregate denominators bounded; it is an
explicit numerical approximation to exponential weights. Tiny weights may become zero.

All other model fractions are exact. Timestamps sort by UTC time then session ID.
First/last/position credit inherits this deterministic tie-break; tied paths retain the
M8 uncertainty flag. The lexical tie-break must not be interpreted as real chronology.

## Exact-money conservation
Conversion credit is a rational number of order equivalents, not a count of distinct
customers or an acquisition metric. An order can carry conversion credit even when its
money amount is zero.

Money is allocated per order and per touch: floor amount times normalized weight, then
assign remaining paise in descending fractional-remainder order. Exact ties follow the
journey order. Channel and campaign totals sum those already-rounded touch amounts;
they are not independently rounded. Every model conserves each order's amount exactly.

Empty paths receive one conversion and all money in the null channel/campaign/session
bucket, labelled unassigned_no_eligible_touch. No Direct touch is fabricated. Zero-credit
touches are retained for auditability. Repeated channel appearances sum normally.

## Run and compare
```powershell
.venv/Scripts/python.exe -m nemo.warehouse build --observations artifacts/milestone-1-verified/observations --database artifacts/milestone-9/nemo.duckdb
.venv/Scripts/python.exe -m nemo.attribution --warehouse artifacts/milestone-9/nemo.duckdb --output artifacts/milestone-9/attribution.json --html artifacts/milestone-9/comparison.html
```
Open comparison.html in a browser. It works offline and has no script or network dependency.
Use new output paths for another run; the CLI refuses existing or colliding paths.

To inspect sensitivity, run with --lookback-days 7 or --half-life-days 1 and different
output filenames. Alter one assumption at a time. The API is
nemo.attribution.report(Path(database), lookback_days=30, half_life_days=7).

JSON includes five per-order allocation sets, channel/campaign totals, channel ranges,
deltas from last touch, exact conversion fractions, coverage flags and source/method
fingerprints. HTML places the same model money totals side by side and highlights
maximum-minus-minimum channel credit. This range is not a statistical confidence interval.

## Evidence and architectural limits
Outputs are labelled attribution_result. They do not modify M2 acquisition semantics,
M4 recommendation gates or M5 diagnostic rules. Producing model credit does not certify
tracking completeness or enable gated recommendations. Last touch here is not a
last-non-direct or platform advertising-click model.

Missing identities, offline activity, lookback truncation and source errors remain.
Canonical IDs are assertions supplied by ingestion, not a claim of resolved humans.
Gross merchandise credit is before refunds and is neither profit nor incremental value.
No ROAS, CAC, budget optimizer or recommendation is added. Model disagreement does not
rank models by truth or accuracy.

The standalone comparison is a local report, not the future authenticated NEMO web app.
Its full-path JSON contains company identifiers and should be handled as company data.
The implementation materializes reports in memory; pagination and warehouse-scale
materialization are future work. Markov attribution is deferred: conversion-only paths
do not justify a removal-effect model or claims about incremental impact.
