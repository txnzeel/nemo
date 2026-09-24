# Retention / Expansion contracts

M16 reads verified canonical customer/order facts and matching public order items.
It never uses simulation state. Customer identifiers remain local analytical identities;
there is no delivery, consent management or authenticated customer activation service.

## State contract
Both dates are exclusive business-day boundaries inside the source observation window.
Only earlier paid orders enter a state. Evaluate each cutoff independently.
Precedence: NO_OBSERVED_PURCHASE; DORMANT at >=180 days; AT_RISK at >=90;
REACTIVATED after an observed >=180-day gap with recency <=30; NEW with one
order and recency <=30; LOYAL with >=3 orders spanning >=60 days; REPEAT with
>=2 orders; otherwise ACTIVE. The first matching purchase state wins.
NOT_YET_OBSERVED represents customers first seen on/after baseline. Customers first
seen on/after the final cutoff are excluded. CHURNED is unsupported without a
termination contract. Labels describe observed history, not lifetime behavior.

The report retains exact paid-order counts and gross tax-exclusive merchandise
receipts. Refunds do not erase purchase events. Forward value at risk, profit, causal
retention effect and economic ranking remain unknown.

## Expansion contract
Complete order items must reconcile exactly to every canonical paid order, with unique
item IDs, valid order IDs, positive quantities/prices and exact line amounts.
For each ordered product pair A/B, first A must have a complete 30-day follow-up.
Exclude customers who first bought B at or before first A. Success requires first B
strictly after A and before the exclusive 30-day boundary. Each customer counts once.
No future purchases or products enter current sequences. Time comparisons use UTC
instants, not ambiguous same-day sorting.

At most 500 observed products are supported locally to bound pair enumeration.
Default minimum support is 20 eligible customers and 20 sequential customers; callers
may select an explicit integer >=2 for manual examples. This is a review screen, not
significance, propensity or a recommended offer. Pair order reflects observed support,
not expected profit or causal return.

## Review cases
AT_RISK and DORMANT cohorts produce investigation/test-design cases. Supported pairs
produce cross-sell experiment-review cases. Stable case IDs bind dataset/mode/kind/
state or product pair; revisions bind current evidence and cutoffs.
Cases retain source hashes and prerequisites for measurement, consent, stock, costs
and controlled evidence. They are not the M5 conversion diagnosis schema and are
not imported automatically into the decision ledger. No outward messages are sent.

## Run
    python -m nemo.retention --warehouse verified.duckdb --observations observations --baseline 2025-01-01 --as-of 2025-07-01 --min-customers 20 --output retention.json

Python report(warehouse, observations, baseline=date(...), as_of=date(...),
min_customers=20) returns a versioned report. Existing output files are protected.
See [learning guide](learning-retention.md).
