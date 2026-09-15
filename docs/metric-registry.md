# Acquisition measurement learning and contract

Current execution note (M3): dbt owns warehouse facts. The original metric definitions
below are preserved; the SQLite component is now input validation only.
See [warehouse.md](warehouse.md) for the implemented execution path.

This milestone measures observed acquisition activity. It does not recommend spending
changes, assign measurement confidence, or claim incremental impact.

## Learning contract (before implementation)

### CTR — click-through rate
1. Plain English: the share of ad impressions that produced clicks.
2. Business purpose: inspect whether an ad attracts clicks; not whether it produces profit.
3. Example: 100 clicks from 2,000 impressions = 5%.
4. Formula: clicks / impressions. Stored as a fraction (0.05), not a percentage (5).
5. Data: campaign/device/date advertising impressions and clicks.
6. NEMO: divide summed clicks by summed impressions in the selected scope.
7. Failure modes: averaging campaign percentages, low volume, and irrelevant clicks.
8. Interview: “CTR measures click response; I calculate a ratio of sums, not a mean of rates.”

### CPC — cost per click
1. Plain English: the average ad spend for each billed click.
2. Business purpose: understand traffic cost alongside downstream purchase behavior.
3. Example: ₹1,000 / 100 clicks = ₹10 per click.
4. Formula: paid media spend / paid clicks.
5. Data: ad spend in paise and click counts for the same scope.
6. NEMO: sum spend and clicks before division; output paise per click.
7. Failure modes: cheap clicks can be poor quality; CPC does not include non-media costs.
8. Interview: “CPC is a weighted average derived from total spend and total clicks.”

### CVR — session purchase conversion rate
1. Plain English: the share of sessions that produced at least one paid order.
2. Business purpose: inspect the storefront's ability to turn visits into purchases.
3. Example: 5 purchasing sessions / 80 sessions = 6.25%.
4. Formula: distinct purchasing sessions / sessions.
5. Data: session IDs/start times, paid orders/session references, analysis cutoff.
6. NEMO: session-start cohorts within the report window; count purchases observed before
   the report's exclusive end. A session with two orders still counts once in the numerator.
7. Failure modes: click-based platform conversion rates have a different denominator;
   recent cohorts have had less time to convert. No future orders enter historical reports.
8. Interview: “I name the denominator and cutoff: this is session CVR, not Google Ads CVR.”

### CPA — media cost per purchase
1. Plain English: ad spend per recorded purchase credited to a paid session.
2. Business purpose: compare purchase volume with media expenditure.
3. Example: ₹1,000 / 5 paid-session orders = ₹200 per purchase.
4. Formula: paid media spend / paid-session paid orders in the reporting period.
5. Data: paid orders, their purchase-session channel/campaign/device, and ad spend.
6. NEMO: paid-at date for orders; purchase-session source for credit. Organic orders
   are excluded from this denominator even in an all-channel report.
7. Failure modes: repeat buyers count as purchases; order timing may lag spend; this
   accounting ratio does not establish that advertising caused the purchases.
8. Interview: “CPA counts purchases, whereas acquisition cost counts newly acquired buyers.”

### CAC and media-only CAC
1. Plain English: the cost of acquiring one new paying customer.
2. Business purpose: distinguish customer acquisition from repeat purchases.
3. Example: ₹1,000 media spend / 2 new paid-session buyers = ₹500 media-only CAC.
   If attributable sales/marketing costs total ₹1,600, full CAC would be ₹800.
4. Formula: full CAC = total acquisition-related sales and marketing cost / new buyers;
   NEMO media-only CAC = paid spend / first-observed paid-session buyers.
5. Data: full acquisition costs and first purchase history. M1 supplies only media costs.
6. NEMO: rank all available orders by paid timestamp and order ID BEFORE window/channel
   filtering. Credit each first observed buyer to that order's purchase session.
   Return full CAC as unavailable, with missing-cost reason; never silently substitute
   media-only CAC. New buyers means first observed, not proven lifetime first purchase.
7. Failure modes: visitor IDs are not acquired buyers; missing earlier history causes
   left censoring; period spend and acquisitions are not necessarily a causal cohort.
8. Interview: “I distinguish media-only CAC from full CAC, and retain the history
   boundary rather than claiming a customer's first-ever purchase.”

### ROAS — reported return on ad spend
1. Plain English: recorded purchase revenue credited to paid sessions per rupee of ad spend.
2. Business purpose: describe reported revenue relative to media cost.
3. Example: ₹4,000 paid-session revenue / ₹1,000 spend = 4×.
4. Formula: paid-session merchandise revenue before refunds / paid media spend.
5. Data: paid order amounts, purchase-session source and corresponding ad spend.
6. NEMO: exclude organic/direct revenue from the numerator, including at grand total.
   Record the credit rule explicitly. This is not a platform attribution model.
7. Failure modes: high ROAS can coexist with losses, refunds or weak incrementality.
   Tax, fees, cost of goods, refunds and counterfactual sales are excluded.
8. Interview: “Reported ROAS is neither profit nor causal incremental return.”

Definitions checked against:
- [Google CTR](https://support.google.com/google-ads/answer/2615875?hl=en)
- [Google average CPC](https://support.google.com/google-ads/answer/14074?hl=en)
- [Shopify CAC](https://www.shopify.com/enterprise/blog/overhauling-customer-acquisition-model)
The precise session denominator, first-observed customer rule and revenue basis above
are NEMO's explicit measurement contract, not claims of matching platform reporting.

## One authoritative registry

The executable registry in src/nemo/metrics.py defines each metric's name, version,
description, numerator, denominator, unit, grain, dimensions, sources, freshness
requirement, and limitations. The CLI can export it; do not maintain a second executable
formula in documentation. Base facts are calculated in acquisition.sql and ratios use
the registry's numerator/denominator references. Six-place Decimal strings use explicit
half-up rounding; numerator/denominator integers are retained for exact audit.
Zero denominators return null and a reason, never zero or infinity.

Counts: impressions, clicks, sessions, orders, conversions, purchasing sessions and
first-observed new buyers. A conversion is a paid purchase, so conversions and orders
share one underlying fact. CVR deliberately uses purchasing sessions, not purchase count.
Revenue is tax-exclusive INR merchandise sales before refunds. Spend is paid media only.

## Scope, timing, and missing data

Report windows are start-inclusive/end-exclusive Asia/Kolkata business dates inside
the snapshot observation window. Session counts and CVR use session-start cohorts;
orders/revenue/new buyers use paid-at dates. A session begun before the window can
contribute an in-window order, but not a session-cohort conversion. Credit is to the
recorded purchase session, not an acquisition journey or incrementality estimate.
First-buyer history spans the full supplied snapshot; order ID breaks timestamp ties.

Group by any subset of business_date, channel, campaign_id and device. Filter values
are bound parameters; SQL identifiers come from a fixed whitelist. Ratios are recomputed
from summed facts for each group and total, never averaged. Organic/direct groups have
no paid media cost data: paid metrics are unavailable, not claims of zero acquisition cost.
Missing required source tables abort the report. A present empty table differs from
a missing table. Ad-row coverage is not evidence of source completeness.

The reader only opens manifest.json and five declared observation tables: customers,
campaigns, ad_performance, sessions and orders. It checks hashes, row counts, units,
schema, timestamps, IDs, types and references. It never opens private/run.json or
imports the simulator. Events and refunds are not needed for these specifically defined
order-based, before-refund metrics. Structural validity is not measurement health:
health remains not_assessed unless the M4 canonical reconciliation input is supplied.
M4 confidence covers purchase tracking only; it does not redefine these order-based metrics.

## Architecture decision

Use Python's built-in SQLite as an ephemeral local executor for the relational SQL.
This adds no dependency or persistent warehouse. Keep raw normalization in the reader,
all analytical aggregation in one packaged SQL resource, and ratio definitions in
the registry. Milestone 3 will migrate this SQL execution to dbt/warehouse adapters
and retain these tests; it must replace the temporary execution path rather than
introduce duplicate Python/dbt transformation definitions.

## Acceptance criteria

- An observation-only snapshot produces grouped metrics and totals through a real CLI.
- Hand-calculated examples verify every metric, units and null reasons.
- Unequal group sizes prove weighted totals; extra order lines/events cannot inflate totals.
- Historical cutoffs exclude future orders; first purchase ranking precedes filters.
- Non-paid revenue never inflates ROAS or paid CPA/CAC denominators.
- Missing costs/history limitations remain visible; full CAC is not fabricated.
- Corrupt/missing sources, duplicate IDs and invalid references fail explicitly.
- Tests, lint, format, offline build and installed-wheel CLI pass.
- No changes to generator behavior or progress into Milestone 3.
