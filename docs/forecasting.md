# Forecasting and Scenario Lab

M17 uses canonical warehouse facts and explicit source coverage. No synthetic parameters
or generator dependencies enter forecasts or scenario arithmetic.

## Forecast contract
Supported metrics are existing registry definitions: orders, sessions and revenue
(tax-exclusive merchandise receipts in paise). Daily aggregation is SQL over canonical
facts. forecast_contract in the public manifest must equal:

    {"version":"1","daily_coverage_complete":true,"coverage_end_exclusive":"<snapshot end>"}

Coverage is an adapter assertion. Without it, forecasts are not_assessed: missing
activity cannot silently be filled with zeros. The exclusive cutoff is inside the
snapshot and no later than the current business date.

## Method and evaluation
Horizon is 1–14 days. Candidates are last-value naive and weekly seasonal naive.
Training starts with 14 observed days. Backtest origins require at least
40 + 2*(horizon-1) positions. Split origins in half for selection and later audit,
purging horizon-1 origins between them so selection targets do not overlap audit targets.
Choose smallest selection MAE with deterministic name tie-breaking.
The selected method is fixed before the audit period. Later origins may use earlier
audit observations as history, reproducing rolling forecasts, not reselecting a model.

Audit outputs include MAE, signed bias and empirical band coverage. Bands use the
90th percentile selection absolute error separately by horizon, with lower bounds
clipped at zero. No 90% future-coverage guarantee is asserted; overlapping origins are
not independent trials. A perfect deterministic fixture may have a zero-width band,
which says nothing about real-world certainty. Structural-break tests expose failure.

## Conditional scenarios
scenario(baseline, changes) requires positive integer totals: spend_paise, clicks,
sessions, purchasing_sessions, orders, merchandise_receipts_paise, plus source_reference.
The caller must supply comparable population/window totals; the function does not
independently verify that assertion. Purchasing sessions cannot exceed sessions/orders.
Supported multipliers are spend_multiplier, cpc_multiplier and cvr_multiplier, each
an exact positive numerator/denominator object. Conversion probability cannot exceed one.

Clicks = changed spend / changed CPC.
Sessions = clicks * baseline sessions per click.
Orders = sessions * changed purchasing-session rate * baseline orders per purchasing session.
Receipts = orders * baseline average paid merchandise amount.
Outputs preserve rational estimates and source/method references. Zero-denominator
baselines fail rather than fabricate estimates. No refunds, cost, auction or saturation
response is inferred. Incremental profit is null. A scenario is not a causal counterfactual.

## Commands
    python -m nemo.forecasting --warehouse verified.duckdb --observations observations --metric revenue --horizon 7 --output forecast.json

Python report(warehouse, observations, metric="orders", horizon=7, cutoff=None) and
scenario(baseline, changes) are the programmatic interfaces. Existing output files are
protected. See [learning guide](learning-forecasting.md).
