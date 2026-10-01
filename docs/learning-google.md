# Learning guide — Google integration boundaries

## What you built and why
Read-only Google report extraction with explicit staging and coverage metadata.
A marketing team can bring spend, landing-session totals and query visibility into a
controlled reconciliation process without teaching every downstream analysis vendor schemas.

## Example, formula and data requirements
A campaign reports 1,230,000 micros in INR: 1,230,000 / 10,000 = 123 paise.
A value of 1,230,001 has a remainder; the current mapping rejects it. Rounding is a
business/accounting policy, not an incidental float conversion.
You need an authorized account, OAuth token, provider report dimensions, currency,
timezone, window and coverage. GA4 session counts do not supply individual session rows.

## Architecture and implementation
Fixed extraction → provider-aware normalization → versioned aggregate staging →
reviewed future canonical mapping → existing analytics. Extraction does not execute M1.
Pagination validates duplicate grain and detects changing GA4 row counts. Atomic publication
keeps partial results from replacing a valid report. Source quality metadata survives.

## Alternatives and trade-offs
Direct SDK ingestion could manage OAuth and richer types, but adds dependencies and still
needs semantic mapping. REST keeps this narrow read surface inspectable. Bulk warehouse
exports are better for event-level reconstruction and large volumes. The bounded report
extractor deliberately does not pretend to be that pipeline.

## Business and statistical concepts
Reporting coverage is different from data accuracy. A returned Search Console query table
can omit queries. A GA4 threshold flag warns about suppressed visibility. Neither lets
you estimate causal lift. Daily counts in Pacific time and India time are different
windows even when their date strings match.

## Failure modes
Expired access, missing account permissions, quota, schema changes, duplicated pages,
fractional money, timezone mismatches and mutable historical reports. Fail closed and
retain a clear pending verification status. Keep staged query/account data outside Git.

## Five interview questions and strong answers
1. Why not call the raw Google response canonical? Vendor grain, timezone and meaning
   differ; normalization must reconcile them before downstream reuse.
2. Why reject fractional paise? An unapproved rounding rule changes accounting totals.
   Preserve exactness or introduce an explicit reconciled policy.
3. Can 100 GA4 sessions become 100 canonical sessions? No. Counts provide no identifiers,
   event sequence or order links. Use entity-level observations.
4. Does pagination establish complete market visibility? No. It exhausts a returned
   report, whose coverage and privacy restrictions still apply.
5. What does offline testing prove? Request construction, mapping and failure behavior.
   It does not prove live credentials, quota, reconciliation or company-data validity.

## Interview explanation
“I built read-only report ingestion without coupling analytics to Google or the synthetic
generator. I preserve source coverage and exact money, and refuse to turn aggregate
reports into fictitious events. Live verification remains a separate acceptance gate.”
