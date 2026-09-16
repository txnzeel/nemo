# Milestone 8 — Journey Reconstruction

## Outcome
Implemented observation-only, multi-touch conversion windows with exact timestamps,
channel paths, campaign/device detail, touch counts, observed time to purchase,
path frequency, prior-channel appearances and distinct channel combinations.

Read [Journey contracts and commands](journeys.md) and the
[eight-part learning guide](learning-journeys.md).

## Architecture audit
- Current source boundary: validated canonical observations enter the existing dbt warehouse.
- Synthetic coupling discovered: none required by the journey layer.
- Changes made: one new reporting module, manually authored tests and documentation.
- Canonical boundary: ready fct_sessions and fct_orders, joined by canonical customer ID.
- Production extension: adapters normalize customer/session/order identifiers, dimensions
  and timestamps before the existing ingestion and dbt pipeline.
- Tests added: 11 cases covering hand-calculated paths/time, inclusive bounds, repeated
  orders/channels, timestamp ties, empty windows, identity isolation, future exclusion,
  reconciliation, invalid parameters, CLI overwrite safety and blocked private/source access.
- Existing tests affected: no existing test or metric contract changed.
- Milestone 3 scope remaining: its local warehouse remains complete; Snowflake is still
  not live-verified. No production connector is claimed.

No generator execution, generator object, private truth, seed, event feed or synthetic
configuration is needed to reconstruct journeys. No dbt model was changed.

## Semantics and evidence
A touch is an observed session start; conversion is a paid order. Default lookback is
30 elapsed days, inclusive at both ends. Repeated purchases use independent overlapping
windows. Equal-time sessions have deterministic lexical ordering with an uncertainty
flag. Missing prior history and purchase sessions outside the lookback are explicit.
The report retains zero-touch orders, with unknown elapsed time.

Identity uses the canonical ID exactly as supplied; no cross-device stitching is inferred.
Prior-channel counts are descriptive appearances, not attributed revenue or causal lift.
No money is allocated, no profit is claimed, and no existing economic definition changes.
Nonbuyer paths, attribution models and causal comparisons are outside this milestone.

## Reference demonstration
The original canonical M1 observations produce:
- 5,989 paid-order journeys.
- 592 windows containing more than one session.
- 322 windows limited by the snapshot's starting boundary.
- Zero empty windows and zero timestamp-tie windows in this reference world.

Outputs remain local in artifacts/milestone-8. Full-report equality is verified against
the installed wheel from outside the source checkout. The production-labelled manual
fixture is a contract test, not a live company integration.

## Validation
The complete suite contains 176 tests: 165 prior tests plus 11 journey tests.
Configured Ruff lint and format checks pass. Wheel/source builds pass; archives exclude
local runtimes, generated artifacts and private truth. The reference dbt build passes
11 models and 25 tests; source freshness, SQL compilation and docs generation pass.
Original M1 source/observation hashes and frozen M6 method/held-out scores are unchanged.
No type checker is configured.

Commands:
```powershell
.venv/Scripts/python.exe -m pytest --tb=short
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv build --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
.venv/Scripts/python.exe -m nemo.warehouse freshness --database artifacts/milestone-8/nemo.duckdb
.venv/Scripts/python.exe -m nemo.warehouse compile --database artifacts/milestone-8/nemo.duckdb
.venv/Scripts/python.exe -m nemo.warehouse docs --database artifacts/milestone-8/nemo.duckdb
```

## Limits and next step
Only observed session starts are reconstructed. Source identity/tracking coverage remains
unverified; buyer-only paths cannot estimate conversion propensity. Memory usage grows
with supplied sessions and emitted paths; production-scale materialization is future work.
A full path is not evidence of a full human journey.

Next: Milestone 9 — Attribution Lab, after the user says proceed.
