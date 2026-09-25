# Learning guide — Response Curves

## Meaning and business purpose
A response curve describes how a measured outcome varies with spend. Diminishing
returns means the next unit of spend has a smaller modelled return than earlier units.
This supports bounded scenario planning, not automatic reallocation from correlation.

## Example and formula
Use the transparent saturating family y = A*x/(B+x), with A>0 and B>0.
A is the asymptotic outcome scale; B is spend at half that scale.
Marginal response = A*B/(B+x)^2, decreasing as spend grows.
At x=B, predicted outcome is A/2; doubling spend to 2B predicts 2A/3, not A.
This is a modelling assumption, not a universal law of advertising.

## Data requirements
A public canonical weekly response supplement with channel, week start, spend and
explicit merchandise receipts, refunds and all five variable-cost components.
Contribution before media = receipts - refunds - sum(variable costs); media is excluded
so scenario net contribution can subtract it exactly once. Costs are complete declared
observations, not synthetic truth. Each scope must retain its definition and lineage.
Require at least 24 complete weeks, substantial spend variation and enough distinct
spend levels. These are minimum screens, not proof of causal identification.

## Implementation
Fit A by least squares for each candidate B on a fixed log-spaced grid derived from
training spend. Select minimum training error, then compare predictions on a later
chronological holdout with a constant training-mean baseline. Withhold curve use if
it does not beat that baseline, lacks variation, or lands on a grid boundary.
Publish empirical holdout error bands and supported spend range. Never extrapolate.
Keep observed money exact; numerical fitted parameters are labelled model estimates.

## Failure modes
Spend follows demand; seasonality, targeting, promotions and selection can confound
response. A good holdout prediction does not identify incremental contribution.
Flat or nearly linear ranges weakly identify saturation. Boundary fits and insufficient
data must withhold curves. Error bands are not posterior credible intervals or
guaranteed future coverage. No curve converts attribution into causality.

## Alternatives and trade-offs
A constant baseline is cheap and falsifies unjustified complexity. More flexible curves
need more data and stronger validation. Randomized budget experiments offer stronger
identification but must cover the intended spend range. This milestone fits a bounded
descriptive model; causal transport and economic action remain gated.

## Interview questions and answers
1. Why diminishing returns? It expresses a testable saturation assumption.
2. Why holdout? Training fit alone rewards complexity without future evidence.
3. Why no extrapolation? Data does not identify behavior beyond observed support.
4. Is it incremental contribution? No, observational fit cannot establish intervention effect.
5. What makes optimization trustworthy? Valid response evidence, uncertainty, constraints,
   costs and controlled outcome evaluation—not only a mathematically optimal allocation.
