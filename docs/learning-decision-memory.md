# Learning guide — Decision Memory

## Meaning
Decision memory retrieves prior decisions, outcomes and lessons for a new case.
It is evidence retrieval, not a learned causal model.

## Business purpose
Teams should see earlier failures and uncertainty as well as apparent successes.
A prior investigation can suggest what to check next without dictating a new action.

## Example
A new conversion case for Android can surface a previous Android conversion target
that was missed. The lesson prompts a review of measurement and population differences.
It does not prove the same cause occurred again.

## Formula
Eligibility = same dataset and source mode AND relevant metric/scope AND prior window
end <= new baseline start AND events recorded <= knowledge cutoff.
Choose the latest decision revision per opportunity, then order by prior window end
and stable decision ID. This is an explicit retrieval rule, not a similarity probability.

## Data requirements
A valid existing conversion Decision Case, an audited ledger, and an explicit UTC
knowledge cutoff. Current support is cvr with whole-dataset scope or a supported device.
Channel/campaign-specific histories are not silently treated as dataset-wide evidence.

## Implementation
Replay the ledger prefix visible at the cutoff. Preserve the selected decision, outcome,
lesson and audit references. Collapse revisions of the same opportunity to prevent
counting them as independent experiments. Attach memory beside the original case;
do not change its finding, evidence level, blockers or recommendations.

## Failure modes
Late recording differs from event occurrence. Retrospective plans are not preregistered.
Changed measurement definitions, incompatible populations and overlapping windows
invalidate naive reuse. A limit truncates retrieval and does not establish consensus.
Latest unresolved results must not be replaced with an earlier successful revision.
Ledger hashes bind records but do not authenticate actors or source assertions.

## Interview explanation
“I implemented point-in-time, scope-aware retrieval with explicit exclusion reasons.
Prior results inform review questions while the current detector remains unchanged.
I preserve failures and uncertainty and never turn repeated correlations into causality.”
