# Search Intelligence contract

M15 consumes canonical observations plus the optional search_performance table. It
does not access generator internals or private truth. Adapters normalize vendor fields
before this boundary; M24 will implement live Google extraction.

## Canonical supplement
Manifest search_contract contains version "1", scope (account/property/population),
brand_classification (rule description), coverage ("returned_queries" or
"complete_queries"), conversions_complete (boolean), and, when complete,
conversion_definition and conversion_window (nonempty descriptions).
Completeness includes the reporting delay; it is an adapter assertion, not independent
measurement verification. One scope per snapshot prevents silently combining accounts.

Rows have business_date, surface ("paid"/"organic"), normalized query, device,
brand_segment ("brand"/"nonbrand"/"unknown"), impressions, clicks, spend_paise,
reported_conversions, position_sum_micros, campaign_ids, keywords, landing_pages.
The unique grain is date/surface/query/device. Counters are nonnegative integers,
clicks <= impressions, exact monetary inputs use int64 paise. Dates/devices must belong
to the canonical snapshot. Campaign IDs must refer to canonical paid campaigns.
Adapters must restrict this supplement to search traffic; campaign channel labels
remain source-neutral. Lists preserve drilldown identities, not allocated statistics.

Paid rows require spend and campaign IDs; rank is null. Conversions require complete
declared reporting or must be null. Organic spend/conversions are null and paid
campaign/keyword lists empty. Organic position is the sum of impression-level rank
millionths (at least 1,000,000 per impression), with zero sum for zero impressions.
Fractional attributed conversion counts require a future contract version.
An absent/empty supplement is not_assessed, never a synthetic fallback.

## Metrics and review policy
CTR = sum(clicks)/sum(impressions); CPC in paise = sum(spend)/sum(clicks).
Mean organic position = sum(position_sum_micros)/(1,000,000 * sum(impressions)).
Ratios retain exact numerator and denominator; zero denominator is null.
Absent surfaces have rows=0 and no evidence of zero population activity.
Brand conflicts are labelled mixed. No acquired-customer, revenue attribution, CAC
or ROAS definition is introduced.

Defaults flag paid queries with >=100,000 paise spend, >=30 clicks and zero completely
reported conversions for intent/negative-keyword review. Organic queries with >=1,000
impressions and CTR <2% prompt intent/snippet/rank review. Same-date nonzero impressions
on both surfaces prompt a controlled cannibalization test. These are explicit review
heuristics, not automatic actions or proven wasted spend. Economic value remains null.

## Run
    python -m nemo.search_intelligence --observations observations --output search.json

Python report(observations, min_spend_paise=100000, min_paid_clicks=30,
min_organic_impressions=1000) allows positive integer review thresholds.
Outputs bind source, contract, policy and code hashes. Existing output files cannot
be overwritten. No credentials are needed. See [learning guide](learning-search.md).
