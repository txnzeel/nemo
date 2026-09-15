# Milestone 4 — Measurement Integrity

## Status and purpose
Source reconciliation and dependency-specific Measurement Confidence are implemented.
The local system compares canonical purchase events with canonical paid orders.
It reduces purchase-tracking confidence when their declared relationship fails and
filters affected candidate recommendations. It does not implement an attribution
model, optimizer, causal diagnosis, Decision Case generator, or production connector.

A business needs this distinction because lost tracking can resemble lost sales.
Commercial facts and instrumentation observations have different dependencies.
NEMO retains the observed paid-order metrics while exposing tracking discrepancies.

## Contract and source boundary
A public observation manifest may contain:

```json
"measurement_contract": {
  "version": "1",
  "purchase_semantics": "one_purchase_event_per_paid_order",
  "max_delay_seconds": 300,
  "complete_through": "2025-01-01T18:30:00Z"
}
```

The events entry in tables contains its row count and SHA-256, just like other
canonical tables. Each event has event_id, name, session_id and an aware UTC
occurred_at; purchase events additionally require a nonempty canonical order_id.
Adapters must map external IDs and semantics before this boundary. Replayed identical
event IDs are counted as defects; they are not silently deduplicated.

The contract explicitly declares one purchase observation per paid order, with the
same session and a timestamp from paid_at through paid_at + max_delay_seconds,
inclusive. Version 1 allows an integer delay from zero to 86,400 seconds. Five minutes
is the lab scenario policy, not a claim about any real provider's SLA.

complete_through is the producer's declared historical completeness cutoff, inside
the observation window. This contract exports events only through that cutoff.
An order is mature when paid_at + allowed delay is at or before the cutoff.
Pending orders are counted separately and are not classified as missing tracking.
The cutoff is not the wall clock or proof of live ingestion freshness.

Missing contracts or event feeds remain not_assessed. Corrupt files, invalid identity
schemas and invalid cutoff contracts raise errors instead of yielding a trust score.
Identity, count and timing discrepancies in valid observations produce low confidence.

The assessment reads public canonical files through the existing source validator.
It does not import the generator or lab injector and does not read parent/private files.
Purchase events remain a separate canonical integrity input in M4; they are not yet
persisted as a dbt event fact. Existing dbt acquisition models remain unchanged.

## Reconciliation and Measurement Confidence definitions
1. **Business question:** do observed purchase events satisfy their declared relationship
   to paid orders, sufficiently to pass the measurement prerequisite for event-based analysis?
2. **Inputs:** the complete canonical order/session snapshot, checksummed event feed,
   matching IDs, UTC times and the public reconciliation contract.
3. **Calculation:** exact integer counts of missing mature purchases, duplicate purchases,
   duplicate event IDs, unmatched purchases, session mismatches, invalid session links,
   timing violations and events beyond the declared cutoff. Matched counts are by order ID.
   Missing purchases are also grouped by channel and device for investigation.
4. **Units and grain:** counts at the complete snapshot grain; the missing-order sample
   is capped at 20 IDs. Confidence is categorical, with no numeric probability or score.
5. **Decision rule:** any observed defect gives low. Zero defects with at least one order
   and all orders mature gives high for these checks only. Empty or partially pending
   coverage gives not_assessed. Unknown dependencies always block the recommendation gate.
6. **Interpretation:** high means the declared checks pass. Low establishes a discrepancy,
   not its cause. Tracking loss, delayed ingestion or mapping/contract errors remain
   possible explanations until further evidence distinguishes them.
7. **Limitations:** agreement cannot establish independent corroboration or detect shared
   omissions. Orders are a reference, not independently audited financial truth. No
   currency conversion, event revenue, refunds, profit, causal effect or live freshness
   is inferred. Existing exact INR paise metric contracts are preserved.
8. **Validation:** manually authored production-labelled observations, missing/duplicate/
   mismatched/timing cases, pending orders, invalid watermarks, corrupt/absent feeds,
   generator import blocking, private-truth independence, and report/warehouse binding.

An all-snapshot assessment is deliberately conservative: a localized defect reduces
the purchase-tracking dependency for the whole snapshot. Filtering a measurement report
does not narrow its integrity assessment. Segment-level trust and multi-source freshness
contracts are future work. The report exposes the separate integrity window.

## Downstream gate and evidence levels
The gate uses registered dependencies, not dependency lists supplied by a candidate:

| Candidate kind | Required measurement dependencies |
|---|---|
| event_based_funnel_diagnosis | purchase_tracking |
| attribution | purchase_tracking, attribution_contract |
| budget_optimization | purchase_tracking, paid_media, incremental_economics |

Only purchase_tracking is assessed in M4. Attribution and budget optimization remain
blocked even for the healthy control because their other prerequisites are unknown.
Unknown candidate kinds are suppressed. The gate returns measurement_eligible candidates
and separately suppressed candidates with reasons. Passing it is not causal or economic
validation and never authorizes execution.

The demonstration passes an explicitly illustrative event-based candidate through this
real filter. It is measurement-eligible in the healthy control and absent from the
eligible output after failure. No recommendation generator or optimizer is fabricated.

Assessment claim_type is measurement_assessment. Existing metrics remain descriptive.
No discrepancy is presented as a confirmed deployment failure or causal effect.
Order-based CVR and purchase-session ROAS retain their original definitions and values:
purchase tracking is not one of their inputs. Future event-based metrics must declare
their own dependencies rather than inherit a global trust label.

## Deterministic lab scenario and verified evidence
The lab-only injector copies canonical observations into new healthy and failure folders.
It deletes selected purchase events, recomputes checksums, and preserves commerce,
sessions and advertising bytes. It never overwrites the source or an existing output.
Injection details are stored separately under private/tracking-truth.json.

The reference scenario removes 36 Android purchase events from June 1–7, 2026.
Healthy: 5,989 paid orders and 5,989 matching purchase events; confidence high.
Failure: the same 5,989 orders and 5,953 purchase events; confidence low.
The missing events comprise 18 Paid Search, 11 Organic Search and 7 Direct purchases.
All order-based report totals and metric values match between healthy and failure.
The illustrative event-based candidate passes the healthy measurement gate and is
suppressed with purchase_tracking:low after injection. The detector
receives only the resulting observations; changing private truth does not affect output.
This is a controlled test, not a full Blind Lab evaluator (Milestone 6).

Generated artifacts are under artifacts/milestone-4:
- healthy/integrity.json and failure/integrity.json
- healthy/measurement.json and failure/measurement.json
- gate-demonstration.json
- separate dbt warehouses and build/test artifacts for both snapshots

The complete suite contains 116 tests (98 retained plus 18 integrity tests).
All 116 tests pass. Ruff lint and format checks pass. Both demonstration warehouses
passed all 11 models and 25 dbt data tests. dbt freshness, compilation and documentation
generation also pass. The source distribution and wheel build successfully, exclude
runtime caches/generated artifacts, and include the dbt project and new modules.
An installed-wheel report outside the source checkout reproduces low tracking
confidence and 5,953 purchase events. Original M1 artifact checksums and the five
generator module fingerprints are unchanged. No configured type-check command exists.

## Run
Use the repository's locked environment. Module commands work even when Windows blocks
a generated console launcher.

```powershell
.venv/Scripts/python.exe -m nemo.lab_tracking --observations artifacts/milestone-1-verified/observations --output artifacts/m4-new-run --device android --start 2026-06-01 --end 2026-06-08
.venv/Scripts/python.exe -m nemo.integrity --observations artifacts/m4-new-run/failure/observations --output artifacts/m4-new-run/failure/integrity.json
.venv/Scripts/python.exe -m nemo.warehouse build --observations artifacts/m4-new-run/failure/observations --database artifacts/m4-new-run/failure/nemo.duckdb
.venv/Scripts/python.exe -m nemo.measurement --warehouse artifacts/m4-new-run/failure/nemo.duckdb --integrity-observations artifacts/m4-new-run/failure/observations --output artifacts/m4-new-run/failure/report.json
uv run pytest --tb=short
uv run ruff check .
uv run ruff format --check .
uv build
```

The observation-based measurement API automatically assesses the supplied snapshot.
Persistent warehouse reports require --integrity-observations to perform reconciliation;
without it, measurement_health remains not_assessed. Its manifest fingerprint must
match the built warehouse exactly, preventing healthy evidence from being attached to
another snapshot. Full integrity details and the policy source hash accompany the report.

## Alternatives and trade-offs
An arbitrary weighted confidence score would imply calibration we do not have.
Explicit categorical rules are inspectable and fail closed on unknown prerequisites.
Comparing raw aggregate ad conversions, customers and orders would conflate different
definitions; this milestone reconciles only the explicitly compatible event/order pair.
Dropping a purchase event in a lab copy preserves the original M1 reproducibility contract.
It also avoids teaching the detector about generator parameters.

## Interview questions
1. **Why can revenue remain unchanged while confidence falls?** Revenue comes from paid
   orders; the failure removes tracking events. Source dependencies differ.
2. **Is a missing purchase proof of tracking loss?** No. It establishes a discrepancy;
   delay, identity mapping and incompatible definitions are competing explanations.
3. **Why not compare GA4 purchases directly with CRM customers?** Their grains, definitions
   and windows differ. A reconciliation contract must establish comparability first.
4. **Does high confidence permit budget optimization?** No. Media and incremental economics
   remain unassessed, and passing a measurement gate does not authorize an action.
5. **How is hidden truth protected?** The injector writes it separately; the detector
   accepts only canonical observations. Tests block lab/generator imports and mutate truth.

## Next milestone
Stop before Milestone 5 — First Decision Case until the user says proceed.
Snowflake remains unverified deployment templates, as documented in Milestone 3.
