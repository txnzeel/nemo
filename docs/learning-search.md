# Learning guide — Search Intelligence

## Meaning and business purpose
Search intelligence compares paid query observations with organic query observations
to direct investigation. It helps a marketer review expensive queries and organic
visibility without confusing two different measurement systems.

## Example and formulas
A query with 1,000 paid impressions, 50 clicks and 100,001 paise spend has CTR 50/1,000
and CPC 100,001/50 paise. Neither requires floating-point money. Zero reported
conversions can prompt intent/negative-keyword review only when conversion reporting
is explicitly complete. It cannot establish wasted spend or incremental loss.
Organic mean position = sum of impression-weighted position millionths / impressions
/ 1,000,000. Never average daily averages without impression weights.

## Data requirements
A public canonical snapshot plus search_performance.jsonl and search_contract version 1.
Each row is one business date, surface, normalized query and device. Paid keyword,
campaign and organic page details must be aggregated by the adapter before this grain;
detail lists retain drilldown identities without duplicating counts. No account or
property can be merged into this snapshot unless its metrics share the declared scope.
Conversions are optional source-reported integer counts with a definition and window.
Fractional attributed conversion exports require a future version, never rounding.

## Implementation
Validate checksums, row grain, devices, dates, campaign identities and integer units.
Group query/device across dates; preserve paid and organic denominators independently.
Normalize query using Unicode NFKC, casefold and collapsed whitespace. Brand labels
come from a declared classification rule; conflicting labels remain mixed.
Only same-day visibility contributes to overlap. Hidden/privacy-filtered queries are
not zero: coverage is explicitly reported, not assumed exhaustive.

## Failure modes
Different populations, privacy suppression, reporting lag, brand ambiguity and match
types undermine naive joins. Position is an observed rank statistic, not a lever.
An absent table is not_assessed. Missing conversion coverage suppresses zero-conversion
review. Thresholds prioritize manual investigation; no automated negatives, bids or
budget moves occur. Overlap does not identify cannibalization.

## Architecture and alternatives
The optional canonical table extends ingestion without changing frozen M1–M6 code.
Live Google extraction belongs to M24. A direct API join would couple analytics to
vendor schemas. Daily query grain trades keyword/page-level performance attribution
for additive query totals; drilldown lists do not allocate performance to their members.

## Interview questions and answers
1. Why join search? To compare visibility and prioritize intent or controlled tests.
2. Why exact ratios? Spend remains integer paise and zero denominators stay unknown.
3. Why not call overlap waste? A counterfactual requires experimental evidence.
4. How are missing queries handled? Coverage metadata discloses returned-query scope.
5. What would you improve? Add source adapters, reconciliation and preregistered tests,
   then evaluate decision outcomes rather than treating review flags as recommendations.
