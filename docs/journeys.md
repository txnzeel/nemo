# Journey reconstruction contracts and walkthrough

M8 consumes only the existing ready dbt warehouse. A production adapter supplies
canonical customer, campaign, session and paid-order observations through the existing
validated ingestion boundary. There is no generator, event-feed or private-truth
dependency and no new connector. Read [the learning guide](learning-journeys.md) first.

## Version 1 semantics
The report population is all paid orders in the supplied snapshot. Each order has its
own inclusive UTC interval from payment minus lookback_days through payment; the default
is 30 elapsed days, configurable from 1 through 3650. Identity is equality of canonical
customer_id. Every session start in that interval is a touch, including repeated channels,
with campaign and device retained. No ad impression, click or event is synthesized.

Orders sort by payment timestamp then order ID; touches sort by timestamp then session
ID. A timestamp_ties flag warns that this lexical order is not temporal evidence.
Independent repeat-order windows may reuse sessions, including earlier purchase sessions.
A purchase session starting outside the lookback is excluded and explicitly flagged.
Zero-touch orders remain in totals and have an empty path and unknown time to purchase.

Time to purchase is exact integer microseconds from first included session to payment.
Journey length and touch count both use session units. Path frequency preserves repeated
channels. Channel combinations are sorted unique channel sets. prior_channel_appearances
counts an order once for each channel appearing before the final selected touch; the
same channel can also be final. These are descriptive assists only, not revenue weights.

history_boundary_limited compares requested lookback with the snapshot's Asia/Kolkata
start boundary converted to UTC. It flags insufficient supplied history, not the full
extent of identity or tracking loss. No completeness claim is made for unflagged paths.

## Run
Build a ready warehouse from canonical observations, then reconstruct journeys:
```powershell
.venv/Scripts/python.exe -m nemo.warehouse build --observations artifacts/milestone-1-verified/observations --database artifacts/milestone-8/nemo.duckdb
.venv/Scripts/python.exe -m nemo.journeys --warehouse artifacts/milestone-8/nemo.duckdb --lookback-days 30 --output artifacts/milestone-8/journeys.json
```
Use a new output filename for another run; the CLI refuses to overwrite reports.
The API is nemo.journeys.report(Path(database), lookback_days=30). The warehouse must
have passed the existing dbt build and match its current model fingerprint.

Output includes journeys, path frequencies, channel combinations, prior-channel
appearances, versioned metric definitions, parameters, input hashes and method hash.
It contains customer and session identifiers: treat production reports as company data.
No money is allocated or converted. Existing exact-money and measurement contracts
remain unchanged.

## Limitations and extension
Canonical customer IDs are supplied identity assertions. The engine does not stitch
cookies, infer people, resolve shared accounts or bridge devices. Ad views, offline
interactions and missing sessions remain unobserved. A producer must normalize channels
and campaigns before ingestion. Future channels work through the existing schema-2
channel registry.

The conversion-only population does not include open/nonbuyer paths, so it cannot be
used to estimate channel conversion probabilities or compare buyer and nonbuyer paths.
Touch reuse also prevents summing journey touches as unique traffic. The report loads
sessions and emits full paths in memory; production scale will require pagination or
materialization while preserving this contract. Snapshot corrections restate results.

M9 may add explicitly named attribution models over declared journey contracts.
Attribution still will not imply causality. M8 adds no credit model, incremental
estimate, budget recommendation or profit claim.
