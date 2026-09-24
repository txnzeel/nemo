# Learning guide — Retention and Expansion

## Meaning and purpose
Retention measures observed customer purchase continuity. Reactivation is a purchase
after a long observed gap. Expansion examines sequences of product purchases.
These help teams design retention investigations and controlled offers without
equating inactivity with true churn or association with incremental sales.

## Example and formulas
At an exclusive cutoff, recency is business days since the last paid order.
A customer inactive for 100 days is AT_RISK under the explicit 90-day rule; after
180 days the label is DORMANT. These are operational review labels, not probabilities.
Historical merchandise receipts = sum of paid order amounts in integer paise.
They are neither customer value at risk nor profit.
A-to-B sequence rate = eligible customers buying B strictly after first A and within
30 days / eligible customers with 30 days of follow-up and no prior B.
Each customer counts once per pair. Same-time purchases do not establish order.

## Data requirements
A verified canonical warehouse and matching observations; baseline and as-of dates
inside the snapshot. Only purchases before a cutoff enter its states. Order items
must completely reconcile with canonical orders for expansion analysis.
The observation window may omit older customer history: labels describe observed
history only. No subscription cancellation or confirmed churn input exists yet.

## Implementation and state precedence
No purchase: NO_OBSERVED_PURCHASE. Otherwise DORMANT at recency >=180 days, AT_RISK
at >=90; REACTIVATED when last purchase followed >=180-day gap and recency <=30;
NEW for one order and recency <=30; LOYAL for >=3 orders spanning >=60 days;
REPEAT for >=2 orders; otherwise ACTIVE. First-match precedence is deliberate.
Compare independently computed baseline/as-of states; customers first observed after
baseline enter as NOT_YET_OBSERVED. CHURNED is unsupported, never inferred.
Generate review cases for AT_RISK/DORMANT and sufficiently supported product sequences.
Forward economic ranking stays unavailable until costs, causal response and applicable
uncertainty are present; observed receipts may prioritize investigation only.

## Failure modes
Left-truncated history makes first observed purchase differ from acquisition.
Right censoring inflates sequence rates if follow-up is ignored. Marketing consent,
stock, returns, seasonality and shared preferences matter before outreach.
Refunded purchases remain purchases, not ownership or satisfaction. Multiple testing
and sparse products make associations unstable; minimum support is a screen,
not significance or a propensity model. No automatic campaigns are sent.

## Alternatives and trade-offs
Use explicit state rules before fitting churn or propensity models without labels.
Use customer-level temporal sequences before basket association, because simultaneous
items do not show future demand. Use complete follow-up before complex survival models.
This is a bounded descriptive system with unknown causal/economic effects.

## Interview questions and answers
1. Is dormant churned? No, inactivity lacks a confirmed termination event.
2. Is historical spend value at risk? No, forward value needs costs and response.
3. How avoid future leakage? Filter purchases independently at each exclusive cutoff.
4. Why a follow-up denominator? Incomplete windows cannot be treated as failures.
5. Why not recommend every product pair? Support, consent and a causal test are
   prerequisites; observed sequences alone do not establish profitable interventions.
