# Learning guide — observed journeys

## Meaning
A journey is an ordered sequence of observed sessions associated with a customer's
paid order. It describes recorded interactions, not all interactions a person had.

## Business purpose
Compare common paths, repeated channel visits and observed delays before purchase.
This helps formulate acquisition and measurement questions without claiming that a
channel caused a sale.

## Example
A customer visits Paid Social, then Direct, then Organic Search and pays an order.
The path has three touches, three distinct channels, and two prior channels. If the
first session starts Monday noon and payment is Wednesday noon, observed time to
purchase is 48 hours. This is not necessarily the person's full consideration period.

## Formulas
For order o paid at t, select sessions for its canonical customer ID whose starts
are in [t - lookback_days, t]. Default lookback is 30 elapsed 24-hour days.
Touch count = number of selected sessions; journey length uses the same session unit.
Time to purchase = payment time minus earliest selected session start, in exact
integer microseconds; no selected touches means unknown, not zero.
Path frequency = orders with an exact ordered channel sequence, retaining repeats.
Channel combination = sorted distinct channels on the path.
Prior (assisting) channels = distinct channels on all touches except the last.
A channel may be both prior and final. Counts describe appearances, not revenue credit.

## Data requirements
Validated canonical customers, sessions and paid orders, UTC timestamps and the existing
source manifest. Campaign and device are carried on each touch. No event feed, seed,
private truth, costs or simulation configuration is needed. Anonymous IDs must already
be mapped by an ingestion adapter; the engine does not infer identity.

## Implementation
nemo.journeys reads the ready dbt warehouse. Sessions are indexed per customer and
ordered by timestamp then session ID. Binary search applies each order's bounded
window. Orders use payment time then order ID. Repeated orders have overlapping
lookbacks and can reuse sessions; these are independent conversion windows, not
mutually exclusive acquisition episodes. A canonical purchase session may be outside
the window; this is flagged, never silently included. Equal-time sessions are sorted
deterministically, but their true relative order is unknown and flagged.

## Failure modes
Cookie loss, shared IDs, cross-device gaps, offline touches and source misclassification
distort paths. A history-boundary flag means the lookback extends before snapshot
coverage. Even an unflagged path has no guarantee of complete tracking. Future sessions
are excluded. Conversion paths select buyers only and cannot establish conversion
probability, nonbuyer behavior or causal channel importance. Snapshot corrections
restate reports; there is no historical arrival-as-of view. No attribution or profit
metric is implemented.

## Interview explanation
"I joined canonical customer sessions to each paid order under a versioned lookback
contract, preserved time and identity uncertainty, and reconciled path counts to order
counts. I separated descriptive channel appearances from attribution and causality.
Manual fixtures prove that this works without the synthetic generator."

## Practice
Run the command in [Journey contracts](journeys.md). Change lookback from 30 to 7 days
and explain why touches may disappear while the number of paid orders stays constant.
Find a repeated channel, a repeated buyer and a history-boundary flag. Explain why none
of those observations proves incremental marketing impact.
