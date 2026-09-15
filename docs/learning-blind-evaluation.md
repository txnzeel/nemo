# Learning guide — Blind evaluation

## 1. Sealed predictions and held-out worlds
1. Meaning: produce an answer before the scorer reveals the planted label.
2. Purpose: avoid judging a detector on answers it was allowed to inspect.
3. Example: predict from event/order observations, seal the case hash, then compare
   with a private label saying payment deterioration affected Android.
4. Formula: SHA-256 fingerprints bind observations, method, cases and evaluation truth.
   Hashes are integrity checks, not encryption or proof against a malicious file owner.
5. Data: canonical observations, frozen method/runtime versions, opaque trial IDs,
   historical cutoffs and separately stored labels.
6. NEMO: development, calibration and held-out worlds use different seeds. The detector
   is frozen before all predictions; M6 does not tune it against calibration results.
   A fresh worker receives copied public observations only. Labels join after sealing.
7. Failure modes: repeated tuning on held-out results contaminates the holdout; scenarios
   from the same underlying world are correlated; a few synthetic worlds do not represent
   real clients. A local audit hook is not an adversarial OS sandbox.
8. Interview: “My pipeline seals source-bound predictions before label joins and records
   the method fingerprint. The holdout is isolated by world, not random rows.”

## 2. Confusion, detection and false positives
1. Meaning: distinguish a correct alert, a missed condition and an alert without that condition.
2. Purpose: quantify both useful detection and unnecessary investigations.
3. Example: detect 3 of 4 payment incidents and falsely alert on 1 of 8 healthy cases.
   Recall is 3/4; healthy false-positive rate is 1/8. Report the denominators.
4. Formula: recall = true positives / planted positives.
   False-positive rate = false positives / relevant negatives.
   Exact diagnosis accuracy = exact label matches / all scored cases.
5. Data: sealed finding, privately declared expected finding and device, explicit
   inclusion rules. Empty denominators produce null, not zero.
6. NEMO: report exact numerator/denominator pairs, class confusion, payment detection,
   tracking routing, exact device localization and healthy false-positive counts.
   A correctly detected payment decline with the wrong device fails localization.
7. Failure modes: accuracy can hide missed rare incidents; scoring localization only
   among hits hides misses; a tiny correlated benchmark cannot justify statistical
   certainty. Abstentions count as incorrect for class accuracy, not discarded cases.
8. Interview: “I separate diagnosis, localization, false alerts and missed cases.
   I retain every planned case and do not report a flattering subset.”

## 3. Historical cutoffs and detection delay
1. Meaning: evaluate only observations available through each supplied event-time cutoff.
2. Purpose: avoid using later events to diagnose an earlier snapshot.
3. Example: incident starts May 29; checkpoints are May 29, June 5 and June 12.
   First detection at June 5 has a seven-day scheduled detection lag.
4. Formula: lag = first correctly detected checkpoint minus known onset.
   If no checkpoint detects it, lag is null and the observed horizon is reported.
5. Data: onset held by the evaluator, cropped canonical snapshots and complete checkpoint
   schedules. Do not copy future orders, purchase events, session first-seen records or ads.
6. NEMO: source snapshots are cropped before warehouse building, and comparison windows
   end exactly at each snapshot's exclusive cutoff. Seals cover the full planned split.
7. Failure modes: sparse checkpoints cannot establish the exact day the detector could
   have fired. Rolling windows can dilute an early incident. Latest corrected snapshots
   are event-time reconstructions, not ingestion-arrival history.
8. Interview: “Undetected incidents are right-censored rather than assigned zero delay.
   I report checkpoint lag and horizon, not an invented continuous detection time.”

## Exercises
- If every case is healthy, what is payment recall? Null: there are no planted positives.
- If the stage is right but device wrong, is localization correct? No.
- If a held-out case file changes after sealing, should it be rescored silently? No.
- Do 27 related snapshots mean 27 independent worlds? No.
- Does 100% on one held-out seed establish real-world reliability? No.

See blind-evaluation.md for commands, exact scope, verified results and limitations.
