# Milestone 10 — Experimentation Engine

## Outcome
Implemented fixed-horizon customer experiments with prospective plan registration,
saved 50/50 Bernoulli assignments, conservative sample planning, intention-to-treat
outcomes, explicit readiness gates, uncertainty, statistical/practical significance,
economic guardrails and immutable result memory.

See [the contracts and walkthrough](experiments.md) and the
[eight-part learning guide](learning-experiments.md).

## Architecture
- experiment_design.py validates plans, computes targets and creates assignment ledgers.
- experiments.py consumes canonical customer/order models plus public plan, population
  and assignment contracts. Refunds and costs use the existing M7 validated boundary.
- lab_experiments.py produces separate effect, null-effect and allocation-failure worlds;
  hidden seeds/probabilities and assumed costs stay in private evaluation files.
- tests/test_experiments.py builds a hand-authored production-labelled canonical fixture,
  including assigned nonbuyers with no sessions, without running M1.

No existing generator, dbt model, analytical module or metric definition changed.
New source integration still means normalization into canonical contracts, not a
redesign of downstream analysis. No live connector or treatment deployment is claimed.

## Statistical and accounting scope
The primary outcome is a customer's purchase indicator within the fixed common window.
It is not attributed credit, paid-order count or first-ever acquisition.
Inference uses conservative Hoeffding bounds with a fixed three-metric Bonferroni family.
MDE determines planning; a separate practical threshold determines business significance.

The two economic outcomes are explicitly capped customer gross merchandise and capped
scoped contribution. Point estimates are rational; customer money totals remain integer
paise. Confidence limits are numerical approximations. Uncapped revenue/contribution
effects remain unknown, and merchandise is never labelled profit.

Causal output is conditional on declared randomization, coverage, independent customer
units and no interference. Source assertions and historical registration are not
independently verified by content hashes. Missing readiness keeps incrementality unknown.
No sequential peeking, model attribution or automatic recommendation is introduced.

## Verified synthetic scenarios
Each scenario enrolls 4,000 customers. The declared design plans at least 299 per arm
over seven days for a 20-percentage-point MDE, 80% power and a 5% family error rate.

| Scenario | Control / treatment | Observed buyers, control / treatment | Result |
|---|---:|---:|---|
| Effect | 2077 / 1923 | 301 / 775 | positive_with_guardrails |
| No effect | 2077 / 1923 | 301 / 287 | inconclusive |
| Allocation mismatch | 383 / 3617 | 57 / 1448 | not_ready; no incremental estimate |

In the effect world, estimated purchase-probability lift is about 25.81 percentage
points, with a simultaneous-family interval of about 20.91 to 30.71 points.
Estimated incremental buying customers among treated customers is about 496.32,
with bounds about 402.16 to 590.47. Fractional estimates are not counts of identifiable
counterfactual people. Synthetic effects are demonstrations, not company evidence.

The null scenario remains inconclusive rather than being declared proof of no effect.
The allocation-failure world is rejected despite a positive observed difference.
Assumed cost provenance is retained. Results and verification receipts remain local
under artifacts/milestone-10; private truth is excluded from Git and analytics.

## Validation
The suite contains 228 tests: 198 prior tests and 30 experiment cases.
Coverage includes hand-calculated ITT effects, sample planning and intervals, absent
buyers, exact large money, invalid designs, pre/post-window exclusion, duplicate/missing/
late/unknown assignments, SRM, missing follow-up, incomplete coverage, low sample size,
unknown costs, caps, harm, source binding, immutable memory, prospective registration,
saved randomness, private-import/file blocking and tiny tail-probability underflow.

Ruff lint/format and wheel/source builds pass. The installed wheel reproduces all three
complete reports exactly outside the checkout. Archives exclude generated artifacts,
private truth and local runtimes. Original M1 source/observation hashes and the M6 frozen
method/held-out score are unchanged. No type checker is configured.

All three lab dbt builds pass 11 models and 25 tests. SQL compilation and docs generation
pass. Customer, session and order freshness pass. **The full freshness command returns
errors for the intentionally empty campaign and ad-performance sources in each world.**
The existing freshness rules are preserved, and this limitation is not hidden or
relabelled as a complete freshness pass.

Configured checks:
```powershell
.venv/Scripts/python.exe -m pytest --tb=short
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv build --offline --python .tools/python/cpython-3.12.13-windows-x86_64-none/python.exe --cache-dir .tools/uv-cache
.venv/Scripts/python.exe -m nemo.warehouse freshness --database artifacts/milestone-10/effect/verified.duckdb
.venv/Scripts/python.exe -m nemo.warehouse compile --database artifacts/milestone-10/effect/verified.duckdb
.venv/Scripts/python.exe -m nemo.warehouse docs --database artifacts/milestone-10/effect/verified.duckdb
```

## Limits and next milestone
This implementation supports one fixed-cohort customer design, not cluster/geo,
sequential or adaptive experiments. It does not verify external treatment delivery,
provide an assignment service, estimate uncapped economics, or retrieve prior results
automatically into Decision Cases. The preserved M3 Snowflake configuration is still
not live-verified.

Next: Milestone 11 — Opportunity Engine, after the user says proceed.
