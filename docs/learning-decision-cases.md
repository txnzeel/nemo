# Learning guide — From measurements to a Decision Case

Read this after docs/metric-registry.md and docs/milestone-4.md. This guide covers
only the new concepts used in Milestone 5. Work the exercises before reading their answers.

## 1. A practical anomaly rule
1. **Plain English:** a rule marks an observed change that is large enough to investigate.
2. **Business purpose:** focus an analyst's attention without pretending every movement
   proves a business incident.
3. **Simple example:** 40 of 200 sessions purchased last period (20%); 10 of 200 purchased
   this period (5%). The absolute drop is 15 percentage points and the relative drop is 75%.
4. **Formula:** rate = purchasing_sessions / sessions. Absolute drop = baseline rate minus
   current rate. Relative drop = absolute drop / baseline rate; undefined at a zero baseline.
5. **Required data:** equal adjacent windows, session starts, paid orders linked to sessions,
   and the existing CVR contract. Do not use purchase events as a substitute for paid orders.
6. **NEMO implementation:** flag only when both windows contain at least 100 sessions,
   baseline CVR is positive, absolute decline is at least 2 percentage points and relative
   decline at least 25%. These versioned rules are fixed before inspecting the demo.
7. **Failure modes:** seasonality, promotions, traffic mix and random variation may trigger
   the rule. Sample-size thresholds are operational safeguards, not power calculations.
   This is not a significance test, forecast interval, calibrated alarm or causal result.
8. **Interview explanation:** “I implemented an interpretable investigation rule with
   declared thresholds and an insufficient-data result. I do not call it statistical proof.”

Exercise: baseline CVR is 4%, current CVR 3%. Does the rule flag?
Answer: no. The 25% relative decline passes, but the 1 percentage-point absolute decline fails.

## 2. Exact KPI decomposition
1. **Plain English:** split a count change into movement in volume and movement in its rate.
2. **Business purpose:** distinguish fewer visiting sessions from fewer purchasing sessions
   per visit before choosing an investigation.
3. **Simple example:** baseline has 1,000 sessions at 10% CVR = 100 purchasing sessions.
   Current has 800 sessions at 5% = 40. The total decline is 60.
4. **Formula:** let S be sessions and r be CVR. P = S × r.
   Volume component = (S1 − S0) × (r0 + r1) / 2.
   Rate component = (r1 − r0) × (S0 + S1) / 2.
   Their sum is exactly P1 − P0: the two cross terms cancel on expansion.
   In the example, volume = −15 and rate = −45, summing to −60.
5. **Required data:** comparable period session and purchasing-session counts.
   Multiple orders from one session still contribute only one purchasing session.
6. **NEMO implementation:** use exact rational arithmetic, expose numerator/denominator
   pairs, and also show each device's additive change in purchasing sessions.
   A missing denominator makes that rate decomposition unavailable.
7. **Failure modes:** these components allocate an observed arithmetic difference.
   They are not lost orders, incremental impact or recovered revenue forecasts.
   Traffic mix can change conversion rate without a checkout defect.
8. **Interview explanation:** “The midpoint identity explains the count change without
   choosing an arbitrary calculation order. It is descriptive, not causal attribution.”

Exercise: can you multiply the −45 rate component by average merchandise receipts and
call it incremental profit?
Answer: no. The decomposition is not causal, merchandise receipts are not profit, and
costs and the counterfactual response to intervention are unknown.

## 3. Observed payment success
1. **Plain English:** among sessions with one observed payment attempt, how many have
   one observed successful terminal outcome?
2. **Business purpose:** locate an observed deterioration within the funnel after checking
   whether purchase tracking reconciles with paid orders.
3. **Simple example:** 40 successes out of 50 attempts becomes 10 out of 50: 80% becomes 20%.
4. **Formula:** successful_payment_sessions / attempting_sessions. Zero attempts gives
   unknown, never zero success. A decline is expressed in percentage points.
5. **Required data:** canonical sessions, paid orders, attempt/success/failure events,
   their timestamps and an explicit one-attempt/one-terminal-outcome contract.
6. **NEMO implementation:** SQL aggregates event stages by session, joins canonical
   warehouse facts and checks uniqueness, stage ordering and order/success correspondence.
   Compare device rates only with at least 30 attempts in each window and at least a
   20 percentage-point decline. This policy supports a hypothesis, not causal certainty.
7. **Failure modes:** retries violate this first contract; production adapters must not
   silently collapse them. Missing attempt/outcome telemetry blocks stage interpretation.
   Agreement among events emitted by one system does not prove independent accuracy.
8. **Interview explanation:** “Payment-stage evidence narrows the investigation only when
   its structural contract passes. It does not establish which release or provider caused it.”

## 4. Evidence-ranked Decision Cases
1. **Plain English:** a structured record connects a business question to observations,
   measurement checks, hypotheses and a proportionate next step.
2. **Business purpose:** make reasoning reviewable and prevent an AI or UI from silently
   turning a correlation into a confident financial recommendation.
3. **Simple example:** order-based CVR falls, Android payment success falls, and purchase
   events still reconcile. Investigate Android payment processing; do not assert a bad release.
4. **Formula:** there is no evidence-strength equation here. Keep observed facts,
   descriptive decompositions, diagnostic hypotheses and causal claims distinct.
5. **Required data:** source hashes, scope/cutoff, versioned method, measurement assessment,
   observations, competing explanations and recommendation prerequisites.
6. **NEMO implementation:** generate deterministic case and revision IDs, retain immutable
   JSON revisions, gate payment-investigation candidates on purchase and payment telemetry
   checks, and keep economic/attribution actions blocked on missing prerequisites.
7. **Failure modes:** polished prose can hide weak data; source agreement may share errors;
   the largest contributing device need not be the causal origin. A healthy control on one
   world does not measure the detector's false-positive rate (Milestone 6 will address that).
8. **Interview explanation:** “My case records why an investigation is warranted, what is
   unknown, and what evidence would distinguish alternatives. It does not overclaim a cause.”

## Trace the code
After implementation, follow: decision_case.py → existing measurement reports → funnel.sql
→ integrity gates → immutable case output. The lab_payment module is on the producer side;
the diagnosis never imports it or reads private truth.

## Practice interview
- Why count purchasing sessions rather than assume every order is a different session?
- How could unchanged payment success contradict a payment-stage explanation?
- Why should missing purchase telemetry produce a measurement investigation first?
- What would you need before recommending a budget change?
- Why is an analysis cutoff different from a reconstruction of what was known at that time?

Answers: session CVR has a distinct-session numerator; unchanged stage evidence weakens
that hypothesis; broken telemetry undermines event-based diagnosis; budget changes need
valid media and incremental economics; latest corrected snapshots are not arrival-as-of history.

## Learning path through implemented milestones
1. Read docs/synthetic-business.md: exact-money accounting and deterministic generation.
2. Read docs/metric-registry.md: acquisition metric contracts and denominator discipline.
3. Read docs/warehouse.md: grains, joins, incremental corrections and dbt guarantees.
4. Read docs/milestone-4.md: source reconciliation, confidence and dependency gates.
5. Work this guide's examples, then inspect the healthy/tracking/business-problem cases.
Keep source assertions, observed consistency, statistical evidence and causality separate.
