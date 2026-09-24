# Milestone 15 — Search Intelligence

Connects paid and organic search through a public canonical query supplement.
No generator changes, private truth access or live connector claims are introduced.
See [contract](search-intelligence.md) and [learning guide](learning-search.md).

## Delivered
Exact CTR/CPC, impression-weighted organic rank, source-defined conversion counts,
brand segmentation, keyword/campaign/page drilldown identities and same-date overlap.
Three bounded review paths cover paid queries with no reported conversion, low organic
CTR and cannibalization hypotheses. Economic effects and action execution remain unknown.
The public extension is optional: absence is not_assessed. Malformed declared inputs fail.

## Source boundary
Analytics uses the existing canonical snapshot loader and a checksummed public supplement.
Future Ads/Search Console adapters aggregate source-specific grains into date/surface/
query/device rows, convert money exactly, normalize queries and declare reporting scope.
Source completeness and brand labels are assertions retained for review. M24 owns live
extraction. Existing canonical marketing and commerce contracts are unchanged.

## Validation
Sixteen new tests pass with manually authored canonical fixtures, including exact ratios,
weighted position, missing conversion coverage, nonoverlapping dates, malformed inputs,
duplicate grain, checksums and CLI overwrite protection.
The complete suite passes: 343 tests in 426.33 seconds, including existing M1/M2 tests.

The local demonstration passes all 36 dbt build/test nodes, compile and docs generation.
Its empty ad_performance table has one expected full-freshness error; the other four
sources pass. No freshness rule was relaxed.
Ruff lint/format and package build pass. Installed-wheel output reproduces the complete
demo JSON outside the checkout; archives exclude local runtimes and private/generated
data. M1 hashes, frozen M6 code/dbt/dependencies and M12 ledger replay remain unchanged.
Validation uses approved Ubuntu WSL because Windows DuckDB remains blocked. Historical
M6 Windows held-out scoring is not relabelled as Linux scoring. No type checker configured.

## Limits and next step
This is query review, not proof of wasted spend, true cannibalization or profitable action.
Lists do not attribute query metrics to individual keywords/pages. Fractional conversion
counts and vendor extraction need explicit later contracts.
M16 follows under the user's authorization for all remaining milestones.
