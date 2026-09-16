# Learning guide — attribution and model disagreement

## Meaning
Attribution divides credit for an observed paid order among recorded touches.
Attribution is a model of credit assignment, not proof of causation.

## Business purpose
Compare how assumptions change channel credit before interpreting marketing reports.
Disagreement reveals sensitivity to a model choice; it does not identify the best
channel or justify changing a budget.

## Example
Paid Social → Organic Search → Direct ends in a 101-paise paid order.
First touch assigns 101 to Paid Social; last touch assigns 101 to Direct.
Linear assigns 34, 34, 33 paise after deterministic rounding.
Position based assigns 41, 20, 40 paise: ideal 40.4, 20.2, 40.4 has one remaining
paise, which goes to the first touch under the tie rule. This illustrates why the rounding rule must be declared.
Conversion credit remains exact fractions: linear gives each touch 1/3 of one order.
Money is rounded separately, so a credited fractional conversion is not an order count.

## Formulas
All models use the same canonical M8 session window, default 30 elapsed days.
- First touch: weight 1 for the earliest ordered session, 0 for others.
- Last touch: weight 1 for the latest ordered session, including Direct.
- Linear: each of n sessions gets 1/n.
- Position based: one session gets 1; two get 1/2 each; for n >= 3, endpoints
  each get 2/5 and each interior touch gets 1/[5(n-2)].
- Time decay: raw weight is 2^(-age/half_life); normalize by sum of raw weights.
  Default half-life is 7 elapsed days. Subtracting the latest touch's age from all
  ages preserves normalized ratios and avoids all weights underflowing.

For reproducibility, time decay computes scores with 50-digit Decimal precision,
rounds scores to integer units of 10^-24, then normalizes with exact rational arithmetic and apportions normalized credit
to 10^24 integer units using the same largest-remainder rule. This bounds aggregate
denominators; final credit is represented exactly as fractions of those units.
Very small relative scores round to zero; at least the latest score is nonzero.
Money allocation floors amount × weight, then gives the remaining paise to the
largest fractional remainders; ties follow journey order (timestamp, then session ID).
Per-order allocations always sum to the original integer amount.

## Data requirements
Ready canonical session/order warehouse models and M8 journey contracts. The money
basis is paid tax-exclusive gross merchandise receipts in INR paise, before refunds.
No spend, cost feed, tracking event feed, generator parameters or hidden truth is needed.
The source must already supply customer identities and channel/campaign mappings.

## Implementation
nemo.attribution calculates rational conversion credit, integer paise allocations,
channel/campaign aggregates and channel-level cross-model ranges. It binds the journey
report and order amounts to the same manifest. The CLI produces JSON and an optional
standalone HTML comparison with a visible evidence warning.
Empty paths receive all credit in an explicit unassigned bucket, never a fabricated
Direct touch. Repeated channels receive the sum of their touch allocations.

## Failure modes
Incomplete identities, lookback truncation and timestamp ties change credit. The
lexical tie-break is reproducible, not evidence of relative chronology. Repeat-order
windows can reuse sessions. Last touch here includes Direct and is not a vendor's
last-non-direct model. Position and half-life choices are assumptions, not estimates.
No model measures incrementality. Gross merchandise credit is not net revenue,
contribution or profit. These outputs do not redefine existing acquisition metrics.
Zero paise can still carry fractional conversion credit. Missing touches remain visible.

## Interview explanation
"I implemented five versioned credit rules over one canonical journey population,
kept fractional conversion credit separate from integer money, and reconciled every
order with deterministic remainder allocation. A comparison view exposes model
sensitivity and identity limitations without presenting attribution as causality."

## Practice
Run the [walkthrough](attribution.md). Compare first and last touch for a repeated
channel path. Change the half-life and lookback separately, explain which assumption
changed, and verify each model still conserves all gross merchandise receipts.
