# Learning guide — Forecasting and Scenario Lab

## Meaning and business purpose
A forecast is an expectation conditional on observed history and a method.
A scenario is a calculation conditional on explicit changed assumptions.
Neither proves a causal counterfactual. They support planning and comparisons.

## Example and formulas
Last-value naive predicts tomorrow as today's value. Weekly seasonal naive predicts
a day from its most recent same-weekday observation. Compare both using rolling origins:
MAE = mean absolute error; bias = mean(predicted - actual). Avoid MAPE when zeros occur.
Reserve later origins to audit the selected model instead of reporting selection error
as untouched evaluation. Forecast bands use historical horizon-specific absolute errors;
they are empirical error bands, not guaranteed future coverage.
With fixed spend B and CPC C, expected clicks = B/C. If CPC rises by factor 1.15,
expected clicks become B/(1.15*C), conditional on the constant-spend model.
Expected orders = clicks * landing-session-per-click * session conversion.
Expected merchandise receipts = expected orders * average paid merchandise amount.
Every equation is a stated scenario assumption, not causal evidence.

## Data requirements
Verified canonical daily measures, a complete declared daily observation window,
sufficient past days and comparable reporting. Metric definitions retain their scope.
Missing coverage is not a zero day. Spend/CPC/click counts are not interchangeable
with sessions, customers or orders. Zero denominators withhold scenario estimates.

## Implementation
Use bounded naive candidates first, chronological selection and held-out audit origins,
and horizon-specific errors. Never fit on held-out or future observations.
Keep exact integer/rational observed money. Forecast estimates can be fractional but
must be labelled estimates, not settled transactions. Store method/source versions.
No complexity is justified merely by smaller training residuals.

## Failure modes
Structural breaks, partial days, holidays and changes in acquisition mix violate naive
continuation. Error bands can fail under shifts. A CPC change may also change intent,
conversion and auction volume; a fixed-parameter scenario cannot capture these effects.
No causal or profit claim follows from a receipt forecast.

## Alternatives and trade-offs
Naive baselines are transparent and cheap. More complex seasonal/regression models
need enough backtesting evidence to beat them. Prefer a disclosed weak forecast over
an impressive unvalidated model. Economic optimization must retain these limitations.

## Interview questions and answers
1. Why baseline first? It makes added model complexity accountable to measured error.
2. Why chronological validation? Random splitting leaks future conditions into training.
3. Why not MAPE? Zero outcomes make percentage errors undefined or unstable.
4. Are intervals guaranteed? No, empirical past errors need stable future conditions.
5. Is a scenario causal? No, it is algebra under explicitly conditional assumptions.
