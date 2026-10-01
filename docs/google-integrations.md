# Google report extraction and activation boundary

M24 implements read-only REST report extractors, not a completed live integration.
Google Ads v25 campaign/date/device spend, GA4 date/channel/device session totals,
and Search Console date/query/device search reports are supported.

## Setup: what the operator needs to do

If you do not have these company accounts yet, no setup is required to run NEMO's lab.
Never send credentials in chat or commit them. For a live account:

1. Have the account owner approve the report scope and enable the corresponding API
   in an authorized Google Cloud project.
2. Obtain a short-lived OAuth access token through your organization's approved flow.
   Token refresh, OAuth consent and credential storage are not implemented by NEMO.
3. Grant the authenticated principal access to the actual Ads account, GA4 property
   or Search Console property. OAuth scope alone does not confer account access.
4. Set only the appropriate environment variables in the process running extraction.
5. Run a short historical window into an access-controlled directory outside Git.
6. Compare totals, dimensions, timezone, currency and coverage with the provider UI;
   record account, window, API version and discrepancies before calling it verified.

| Service | Environment variables | Non-secret identifier / scope |
| --- | --- | --- |
| Ads | NEMO_GOOGLE_ADS_ACCESS_TOKEN, NEMO_GOOGLE_ADS_DEVELOPER_TOKEN; optional NEMO_GOOGLE_ADS_LOGIN_CUSTOMER_ID | Numeric customer ID without hyphens; OAuth adwords scope |
| GA4 | NEMO_GOOGLE_GA4_ACCESS_TOKEN | Numeric property ID; analytics.readonly scope |
| Search Console | NEMO_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN | Exact URL-prefix or sc-domain: property; webmasters.readonly scope |

The Ads API scope permits more than reporting; this implementation only sends a fixed
search query and never calls mutation endpoints. Use the least account access the
organization can grant. No accounts, consent grants or credentials were created here.

## Commands

From the locked Python environment, with the relevant variables already configured:

```sh
uv run python -m nemo.google_ingestion ads --account 1234567890 --start 2026-01-01 --end 2026-01-07 --output /secure/stage/ads.json
uv run python -m nemo.google_ingestion ga4 --account 123456789 --start 2026-01-01 --end 2026-01-07 --output /secure/stage/ga4.json
uv run python -m nemo.google_ingestion search_console --account sc-domain:example.com --start 2026-01-01 --end 2026-01-07 --output /secure/stage/search.json
```

These are placeholder IDs, not configured accounts. Dates are inclusive in the source
timezone. Output parents must exist. Reports are atomically replaced only on success.
A failed extraction preserves the previous file: operators must check exit status and
revision, not interpret an old file as a fresh success.

## Contract

google-report-stage-1 preserves source/account, date window, timezone, report coverage,
page count, normalized rows, selected GA4 quality metadata and a content revision.
canonical_activation=false is unconditional. Source dimensions remain explicitly named
source_channel/source_device until an organization approves a canonical mapping.

Ads money is INR integer paise: cost_micros / 10000, requiring zero remainder.
Other currencies and fractional paise fail rather than silently round or apply FX.
Campaign IDs are scoped by the report's account. MOBILE is not inferred to mean Android.
GA4 reported_sessions cannot fabricate session identifiers, customer identities or orders.
Search Console query rows are partial visibility, use America/Los_Angeles dates and
preserve decimal position; they are not complete organic traffic or causal SEO effects.
No CAC, ROAS, acquired-customer or attributed-revenue definition is introduced.

Production activation needs account identity, coverage and reconciliation approval, plus
entity-level web/commerce data for existing canonical session/order contracts. A future
mapping step writes the existing checksummed observations, validates them and builds
the same warehouse. These staged aggregate reports are never automatically installed
as canonical observations or passed to downstream metrics.

## Operational limits

Fixed HTTPS provider endpoints, no redirects, 45 seconds per request, 8 MiB per page,
100,000 rows and at most 100 pages (default 20). Exceeding a limit fails the whole run.
No retries or token refresh are hidden inside extraction. Split windows or use external
orchestration after diagnosing quota/availability failures. Cross-page duplicates and
GA4 row-count changes fail closed; stable counts do not guarantee snapshot isolation.
Google may revise historical data between requests. Empty Ads reports have unknown
timezone because no customer metadata row was returned.

## Verification status and authoritative contracts

All three live integrations are **pending credentials and reconciliation**. Tests use
constructed response fixtures and fake transport only. No real company data was accessed.

- [Ads paginated search](https://developers.google.com/google-ads/api/rest/common/search)
- [Ads authorization](https://developers.google.com/google-ads/api/rest/auth)
- [GA4 report API](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport)
- [GA4 quality metadata](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/ResponseMetaData)
- [Search Console query and coverage](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)

Consult these contracts when API versions change. Offline tests are not evidence that
an account has quota, permission or compatible live report behavior.
