# Milestone 1: synthetic business core

## Learning contract (read before implementation)

### Exact money and refunds

1. Plain English: a paid order is a confirmed sale; a refund returns some or all of a
   paid line amount. Neither a click nor a failed payment is a sale.
2. Business purpose: provide a defensible monetary record for later measurement;
   avoid counting failed payments as revenue or returning more than was paid.
3. INR example: two units at ₹499 make a ₹998 paid line. Refunding one unit returns
   ₹499, leaving ₹499 after refunds. This is not profit.
4. Formula: line amount = quantity × unit price; order amount = sum of line amounts;
   remaining line amount = paid line amount − cumulative line refunds.
5. Required data: order/line/product IDs, quantity, sale-time unit price, payment time,
   refund quantity, refund time, currency and reporting cutoff.
6. NEMO implementation: integer paise throughout; tax-exclusive INR merchandise only;
   sale-time prices copied to lines; successful payments create paid orders; at most
   one partial/full refund per line in this initial model. Refunds after cutoff are
   unobserved, not pulled into earlier data.
7. Failure modes: real tax, shipping, fees, discounts, returns, chargebacks and settlement
   timing are more complex. Remaining merchandise receipts are not contribution/profit.
8. Interview answer: “I model sales and refunds as separately timed records with exact
   integer money, and verify both line-to-order reconciliation and refund bounds.”

### Conditional funnel behavior

1. Plain English: the next business event depends on what has already happened.
2. Business purpose: create linked observations that can later distinguish traffic,
   checkout initiation, and payment-stage changes.
3. Example: of 100 sessions, a 20% checkout chance gives 20 expected checkouts; a 90%
   attempt chance gives 18 expected attempts; a 90% success chance gives 16.2 expected
   paid orders. Actual generated counts are integers and vary by seed.
4. Formula: P(paid | session) = P(checkout | session) × P(attempt | checkout) ×
   P(success | attempt), for this single-attempt funnel. This is the probability chain
   rule, not an assumption that the stages are independent.
5. Required data: session IDs, ordered stage events, payment outcomes, order links.
6. NEMO implementation: sample each next stage only after its prerequisite. Device
   changes the baseline checkout probability; payment success is a configurable
   constant in the healthy core. Paid clicks may fail to create a landing session.
   Advertising spend is generated as clicks × a declared simulated unit click price;
   this is a source billing assumption, not an estimated marketing performance metric.
7. Failure modes: real sessions include retries, multiple orders, cross-device visits,
   consent loss and attribution ambiguity. These are not represented by this funnel.
8. Interview answer: “The generator produces coherent event chains rather than
   independent random tables. Its probabilities are assumptions, not learned findings.”

### Reproducible simulation

1. Plain English: the same model, configuration, and runtime reproduce the same records.
2. Business purpose: make failures debuggable and future analytical evaluations repeatable.
3. Example: seed 42 recreates the same simulated ₹998 order and refund timing; changing
   the seed changes the sampled world without changing accounting rules.
4. Formula: observations = generator(version, seed, configuration, runtime).
5. Required data: full private config, generator source hash, Python version, schema
   version, dependency lock hash, and artifact hashes.
6. NEMO implementation: local Random instance, explicit date interval, stable IDs and
   ordering, canonical JSON Lines and SHA-256 manifests. No wall-clock “now” in data.
7. Failure modes: changing random draws or Python versions can change the world;
   reproducibility is not realism. Seeds/config belong outside future analytics input.
8. Interview answer: “A seed alone is insufficient: I record runtime, source, config,
   and output fingerprints, and test reproducibility in separate processes.”

## Model and boundaries

Default interval: 2025-01-01 inclusive through 2026-07-01 exclusive (18 calendar months).
Business dates use Asia/Kolkata; internally the fixed UTC+05:30 offset is sufficient
for this constrained contemporary Indian simulation. All event timestamps are UTC.
There is no implicit current date. All records are fictional and use no PII.

Paid Search contains brand and nonbrand campaigns. Campaign/device/day aggregates
generate impressions, clicks, spend, and landing sessions. Organic Search and Direct
also generate sessions. A documented weekend traffic multiplier and bounded daily
variation create baseline variation; these are model assumptions, not Indian market
estimates. Sessions select a new or previously seen synthetic person. Customer here
means an identifiable simulated visitor, not necessarily a purchaser. Acquisition
and paying-customer definitions will be introduced with the metrics milestone.

Sessions precede checkout, payment attempt, payment success/failure and purchase events.
Success produces a one-to-three-SKU basket. Prices are fixed. Some order lines get a
quantity-bounded refund 1–14 days later. There is no inventory or fulfillment model.
Record time and ingestion time coincide: no observation defects are injected yet.

## Data contracts

All tables are append-only within a generated immutable snapshot; reruns create a new
directory rather than modifying prior observations. Schema version is recorded in the
manifest. IDs are unique within each table; references use explicit ID fields.

| Table | Grain / primary key | Relationships and rules |
|---|---|---|
| customers | Synthetic person / customer_id | first_seen_at equals first session |
| products | SKU / product_id | Positive integer unit price in paise |
| campaigns | Campaign / campaign_id | Paid Search only in M1 |
| ad_performance | Date × campaign × device / composite key | clicks ≤ impressions; spend = billed clicks × unit click price |
| sessions | Session / session_id | Existing customer; Paid Search requires campaign; one landing session maximum per paid click |
| events | Event occurrence / event_id | Existing session; legal ordered stages; purchase references its paid order |
| orders | Paid order / order_id | Same customer/session; amount equals its lines; exactly one successful payment and purchase |
| order_items | Order line / order_item_id | Existing order and SKU; quantity × sale-time price |
| refunds | Refund / refund_id | Existing order line; positive quantity and amount; after payment; bounded by line amount |

Operational “as of” means before exclusive end midnight in the business timezone.
Events cannot precede their session. Refunds at/after the cutoff are excluded.
The event model intentionally has one payment attempt and at most one order per session.

## Artifact boundary

Each run contains `observations/*.jsonl` and `observations/manifest.json`. The public
manifest records mode, schema, currency, timezone, observation window, row counts and
file checksums. The observation cutoff is public collection metadata, not an incident date.
`private/run.json` records seed, dates, generating parameters, generator/source/runtime
versions and dependency lock hash. Private parameters must not be supplied to future
analytics. This directory separation is preparation, not an enforced security boundary:
future Blind Lab execution must mount only observations in the analysis process.

The writer refuses existing destinations and builds a sibling temporary directory
before renaming it into place. An exclusive sibling lock serializes cooperating NEMO
writers. Abrupt process termination can leave a temporary directory/lock; manual recovery
must verify that no writer is active. This is local snapshot publication, not a durable
distributed transaction. Files serialize deterministically in UTF-8 with LF.
An exception removes only that writer-created temporary directory. The CLI emits a
structured completion/error message. No credentials or external API calls are used.

## Milestone 1 acceptance

- Same seed/config/runtime/source reproduces byte-identical observation files.
- Different seeds change observations; no global random state is modified.
- IDs/references, legal funnels, UTC timestamps and reporting cutoff reconcile.
- Exact order/line money, full/partial refund limits and paid-click/session bounds hold.
- Empty traffic and invalid configs are handled deliberately.
- Default 18-month world is generated and checked without commercial credentials.
- CLI works from an installed package and cannot overwrite an existing run.
- pytest, Ruff lint/format, package build and artifact verification pass.

Milestones 2+ (metrics, warehouse, trust gates, diagnosis, incidents, experiments,
economics, UI and AI) are not implemented or claimed by this milestone.
