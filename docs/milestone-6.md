# Milestone 6 — Blind Evaluation Harness

## Outcome
The Blind Lab freezes the existing detector, materializes historical canonical
snapshots, produces isolated predictions, seals cases and dbt receipts, then scores
them against separately committed truth. All 27 scheduled predictions completed.

See [architecture and commands](blind-evaluation.md) and the
[evaluation learning guide](learning-blind-evaluation.md).

## Verified benchmark results
| Split | Exact diagnoses | Payment detection / localization | Healthy false alerts | Tracking routing | First correct payment checkpoint |
|---|---:|---:|---:|---:|---|
| Development | 8/9 | 1/2 | 0/5 | 2/2 | 14 days |
| Calibration | 8/9 | 1/2 | 0/5 | 2/2 | 14 days |
| Held out | 9/9 | 2/2 | 0/5 | 2/2 | 7 days |

Across this recipe: 25/27 exact diagnoses, 4/6 active-payment checkpoints detected and
correctly localized, 6/6 tracking checkpoints routed correctly, and 0/15 healthy
checkpoint alerts. No tracking case had an eligible investigation candidate.
Tracking failures were first detected at the seven-day checkpoint in all three worlds.

There are only three independent worlds, one per split. Overlapping windows and
pre-incident control copies are correlated. These are descriptive benchmark counts,
not production accuracy estimates, significance results or calibrated confidence.
Held-out success on one seed does not establish general reliability.

## What the misses teach
At the early development checkpoint, Android payment-stage evidence deteriorated but
overall CVR fell only about 0.98 percentage points (8.35% relative), below both M5 gates.
At the early calibration checkpoint, desktop payment evidence deteriorated while
overall CVR rose about 0.48 percentage points. The detector therefore emitted no_signal.

Both trajectories were detected at fourteen days. M5 requires an aggregate conversion
decline before issuing a payment-stage hypothesis; that design can delay a localized
problem masked by composition or other variation. This is an observed detector limitation,
not a harness failure. No thresholds or diagnostic logic were changed after seeing labels.

A future detector revision could test a separately defined local-stage alert policy,
but it must use a new frozen protocol and fresh held-out evaluation. M6 does not implement
that revision or claim an improvement from evaluating the same cases again.

## Implementation and boundaries
- blind_lab.py: generation-side recipe, event-time cropping, method/source commitments,
  worker orchestration, complete seals and evaluator-side scoring.
- blind_worker.py: fresh public-only workspace, private-file/import guards and unchanged
  warehouse/Decision Case execution.
- Tests: hand-authored canonical prediction, score denominators, localization misses,
  right censoring, cutoff exclusion, method drift and artifact tampering.

The worker receives no private path, seed, incident label, target device or onset.
The scorer verifies complete seals before reading truth. Predictions remain identical
when private truth contents are replaced with invalid text. The guards protect against
accidental coupling in trusted Python code; they are not an adversarial OS sandbox.

Cases and all 36 dbt build/test results per trial are checksummed. The implementation
does not silently omit failures or overwrite sealed predictions. Source data, truth and
generated evaluation artifacts remain outside Git; reproducible source and reports are published.

## Learning and validation
The new learning guide explains sealed holdouts, confusion/recall/false positives,
localization and checkpoint-based detection delay with the required eight-part format.
Architecture documentation includes the exact formulas, role boundaries, reproducible
commands, scope and limitations.

The suite contains 148 tests: all 133 previous tests plus 15 Blind Lab tests.
All 148 tests pass, along with Ruff lint and formatting. Wheel/source builds and archive
checks pass. The installed package reproduces all three score reports and the identical
held-out case from a fresh worker. All 27 sealed dbt receipts verify successful execution
of 11 models and 25 tests each. Original M1 source fingerprints and artifact checksums
are preserved. No type checker is configured.

## Limits
- Three short synthetic worlds, not real organizations or an exhaustive scenario suite.
- Fixed M5 thresholds, without calibration fitting, probability scores or confidence intervals.
- Only the existing healthy, tracking-loss and payment-failure mechanisms.
- Event-time snapshots, not original ingestion-arrival history.
- Scheduled checkpoint lag, not exact continuous detection latency.
- Snapshot perturbations do not resimulate later customer behavior.
- No causal-impact magnitude scoring, because the detector makes no such estimate.
- Snowflake and production connectors remain unverified future integration work.

## Next
Milestone 7 — Customer Economics. Stop until the user says proceed.
