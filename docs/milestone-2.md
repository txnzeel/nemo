# Milestone 2 — Acquisition Measurement

## What was built
An observation-only acquisition measurement layer with an executable metric registry,
one packaged SQL definition of additive facts, safe dimensional grouping/filtering, and
a separate nemo-measure CLI. It reads the healthy M1 data without importing the simulator
or reading private generation parameters. The existing generator remains unchanged.

A business needs explicit definitions before it can trust diagnostic comparisons.
Clicks, sessions, purchases and newly acquired buyers are different populations.
This milestone makes those distinctions visible and testable; it does not recommend actions.

## Architecture and decisions
- observations.py verifies five required public tables against the manifest, normalizes
  timestamps to UTC and Indian business dates, validates identities and types, and loads
  a temporary SQLite database.
- acquisition.sql contains the additive facts. Advertising aggregates are unioned with
  session and order contributions rather than joined to order lines, avoiding fan-out.
- metrics.py is the authoritative registry: definitions, versions, units, sources,
  grains, dimensions, freshness requirements, limitations and numerator/denominator references.
- measurement.py executes fixed-whitelist grouping and bound filters, recomputes each
  ratio from summed facts, retains numerator/denominator values and produces a JSON report.
- Report provenance fingerprints the input manifest, consumed source files, measurement
  code, SQL resource, Python and SQLite versions. Results are reproducible for the same
  inputs/runtime/code and contain no wall-clock generation timestamp.

No runtime dependency was added. SQLite is an ephemeral SQL executor, not Milestone 3's
warehouse. Warehouse/dbt migration must replace this execution path and retain its
behavioral tests, not create a second authoritative transformation implementation.

## Alternatives, trade-offs, and learning
A pandas aggregation implementation followed by rewritten warehouse SQL was rejected
to avoid duplicate transformation logic. Bringing in a persistent warehouse immediately
would not improve correctness for this bounded slice. SQL owns relational aggregation;
Decimal arithmetic uses registry references to produce six-place ratio strings with
explicit rounding. Integer numerators and denominators remain available for exact audit.

Averaging campaign percentages was rejected: totals must divide summed numerators by
summed denominators. Paid media costs cannot be divided by organic purchases to produce
a paid-channel CPA, nor can organic revenue inflate reported ROAS.

The full eight-part lessons for CTR, CPC, CVR, CPA, CAC/media-only CAC and ROAS are in
[metric-registry.md](metric-registry.md). The main business lessons are that a visitor
is not a paying customer, purchase CPA differs from acquisition cost, full CAC requires
more than ad spend, and reported ROAS is not profit or incremental return.
The statistical lessons here are denominator alignment, weighted aggregation,
distinct-unit counting, historical cutoffs and left-censored customer history.
No significance testing or causal estimation was introduced.

## Verification
85 tests passed without warnings: all 48 previous tests plus 37 measurement cases.
The new cases cover hand-calculated values for all 16 registered metrics; unequal-weight
aggregation; paid/non-paid separation; first-purchase ranking before filters; future-order
exclusion; midnight boundaries; distinct converting sessions with multiple orders;
first-purchase timestamp ties; row-order invariance; unavailable versus zero values;
all-dimension reconciliation; malformed/corrupt sources; duplicate keys and invalid
references; bound SQL filter values; output refusal; and CLI source-failure handling.

Ruff lint and format passed. A source distribution and wheel built offline. The installed
wheel ran from outside the source checkout and produced the same full report as the
editable package. Its SQL resource was included. Source/lock comparison against the
M1 run metadata confirms the five original Python modules and dependencies were unchanged.

On the existing 18-month seed-42 snapshot the report contains 12 channel/campaign/device
groups, 682,258 impressions, 27,090 paid clicks, 46,152 sessions, 5,989 paid orders and
5,574 first-observed paying customers. Paid media spend is 46,025,400 paise (₹460,254).
These are simulated observations from uncalibrated assumptions, not real results or
evidence that these are realistic marketing performance levels.

Commands run:

    .venv/Scripts/python.exe -m pytest --tb=short
    .venv/Scripts/ruff.exe check .
    .venv/Scripts/ruff.exe format --check .
    uv sync --locked --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
    .venv/Scripts/nemo-measure.exe --observations artifacts/milestone-1-verified/observations --group-by channel,campaign_id,device --output artifacts/milestone-2.json
    uv build --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
    git diff --check

The sandbox process helper failed before inspection, so local commands used approved
elevated execution. No network dependency installation was necessary for this milestone.
An initial long-line lint finding was resolved by formatting; no test assertions were
weakened. The builder warns about an in-project cache; archive inspection checks that
neither the cache nor generated artifacts are shipped.

## What can go wrong / limits
Full CAC returns null because salaries, agency fees and other acquisition costs are absent.
Media-only CAC counts first-observed buyers credited to paid purchase sessions, not an
experimentally identified acquisition effect. Earlier customer history may be missing.
ROAS uses tax-exclusive merchandise sales before refunds; it ignores costs and profit.
All-channel ROAS still uses paid-session revenue only, never total business revenue.

CVR is a session-start cohort measure observed through report end; orders/revenue use
payment dates. Recent sessions have less follow-up. A later report can update a cohort's
CVR. These are explicit reporting policies, not a match to Google Ads or GA4 metrics.

The loader checks structural and artifact integrity, not authenticity, freshness,
reconciliation, completeness or measurement confidence. Health is not_assessed.
If required sources are missing it refuses the report instead of producing partial
metrics; dependency-specific degraded reporting belongs to the integrity milestone.
Only synthetic schema 1 is supported. This is a local in-memory execution path,
not a verified external connector or warehouse. No API, UI, Decision Case or AI is added.

## Five interview questions and strong answers
1. **Why can conversion counts and CVR's numerator differ?**
   “Conversions mean paid purchases. CVR counts sessions with at least one paid purchase.
   Two purchases in one session increase conversions twice and CVR's numerator once.”
2. **Why not average campaign CTRs?**
   “Campaigns have different impression counts. I sum clicks and impressions, then divide.
   For 20/100 and 9/900, total CTR is 29/1000 = 2.9%, not 10.5%.”
3. **How do you avoid marking returning buyers as new after filtering?**
   “I rank each customer's orders across all supplied pre-cutoff history before applying
   the reporting date or campaign filter. Order ID resolves exact timestamp ties.”
4. **Why does full CAC show unavailable?**
   “Ad spend alone is incomplete acquisition cost. I calculate a labelled media-only
   ratio and leave full CAC unavailable rather than silently inventing missing costs.”
5. **Why isn't reported ROAS evidence of incremental growth?**
   “It divides revenue credited by a stated session rule by media spend. It does not
   estimate what sales would have occurred without the ads, and it excludes costs/refunds.”

## Next milestone
Milestone 3 — Warehouse Foundation: local credential-free warehouse/dbt execution,
dimensional models and tests, then Snowflake adapter/RBAC verification where credentials
permit. No warehouse work has started. Stop until the user says **proceed**.
