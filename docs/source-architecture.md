# Source architecture and the role of M1

NEMO is a growth and marketing decision-intelligence platform. M1 is its reference
producer, development/demo world and future controlled evaluation laboratory. It is
not a mandatory production dependency or the analytical engine.

External source → source-specific extraction → normalization/mapping → canonical
NEMO observations → warehouse/trust → metric semantics → marketing analytics →
diagnosis/experimentation/economics → decisions → UI/AI.

## Audit findings and minimal corrections
M2 did not import the generator, use simulation objects, read seeds/private state or
require a generated path. Its hand-authored fixtures already tested source independence.
Genuine coupling remained: the input gate required synthetic schema 1, reports forced
a synthetic label, and paid classification/channel/device options were hard-coded.
These restrictions are now isolated in backward-compatible schema 1 normalization.

Canonical schema 2 declares dataset_id, mode (synthetic/production provenance),
channels mapping canonical names to boolean paid-media flags, and unique device names.
Campaigns declare their canonical channel. Sessions and paid advertising reference
those campaigns. Downstream paid credit uses normalized paid classification, not
a provider name or a hard-coded Paid Search channel. Existing schema 1 remains valid.
The exact-money contract remains tax-exclusive INR integer paise. Currency conversion,
multiple reporting currencies and costs need explicit future contracts.

A production label does not enable or verify a production connector. Tests author
canonical rows manually under that label to prove the same downstream logic works.
No production authentication or remote ingestion is implemented.

## Extension point
A future adapter owns authentication, provider pagination/checkpoints, identifier
namespacing, unit conversion, timestamp normalization and source provenance. It maps
provider fields (such as cost_micros or event_params) into canonical customers,
campaigns, ad performance, sessions, events, orders, order items and refunds.
It supplies an observation manifest and declared coverage. The current acquisition
consumer requires five tables; events/items/refunds remain part of the M1 contract
for later funnel/refund measures, without inventing those measures now.

Schema versions represent contracts, not vendors. Adapters must not put provider
payloads or private simulator configuration into analytical tables. Dataset identifiers
prevent accidental mixing; they are not a replacement for tenant authorization.

## Evidence and accounting
Current outputs are descriptive_metric claims. Purchase-session credit is a named
descriptive assignment rule, not last-touch attribution or causality. An eventual
attribution result, causal estimate and economically justified recommendation require
separate contracts, validity checks and evidence. Full CAC remains unavailable without
complete acquisition costs. Merchandise payments minus refunds are not profit.

## Isolation guarantees and limits
No downstream generator imports. No private/run.json, seed or probability input.
A manual schema-2 paid-social/tablet fixture works in a new process that forbids
generator module imports. All original M1/M2 tests are retained.
This is an architectural boundary, not an OS sandbox. Future Blind Lab must expose
only canonical observations to analytics and reserve truth for the evaluator.

## Milestone 4 integrity extension
The optional public measurement_contract declares purchase-event/order comparability,
allowed delay and a completeness cutoff. Events use canonical IDs and UTC timestamps;
provider payloads and generator internals remain outside the detector. The integrity
module reads checksummed public observations and reports explicit dependency confidence.
The warehouse report requires an identical manifest fingerprint for its integrity input.

The lab_tracking module creates separate perturbed observations and private injection
truth. Analytics never imports it. Production sources can supply the same public
contract without running the lab or M1. See milestone-4.md for exact semantics and
unassessed areas; this is not a live connector or a claim of causal evidence.

## Milestone 5 Decision Cases
decision_case consumes the existing canonical warehouse plus matching checksummed
observations. A public funnel_contract declares the supported one-attempt/one-terminal
session semantics. The detector never imports lab_payment or lab_tracking.
External sources require canonical mapping, not generator execution.

Diagnostic cases preserve metric contracts, source/method hashes, comparison scope,
measurement prerequisites and competing explanations. An observed device payment
decline is a hypothesis, not a known deployment cause. Incremental profit remains null.
Read learning-decision-cases.md and milestone-5.md for exact rules and limits.

## Milestone 6 Blind Lab roles
blind_lab is an evaluation-side module allowed to generate worlds and read private labels.
blind_worker receives a copied canonical snapshot in a generic temporary workspace;
it blocks private reads and lab/evaluator imports while running the unchanged detector.
Historical cropping precedes warehouse creation. Source/method fingerprints and complete
prediction seals are verified before the evaluator joins truth. These trusted-code
guards are not an OS sandbox. See blind-evaluation.md for the exact boundary and limits.

## Milestone 7 economics extension
economics uses existing canonical dbt order facts plus matching, checksummed supplemental
order-item, refund and optional order-variable-cost observations. A public economics
contract declares money/cost scope and the matching coverage cutoff. Missing values
remain unknown; source assertions do not establish independent financial truth.

lab_economics produces explicitly labelled cost assumptions on the lab side. The
analytical module does not import it or read its private recipe. Production adapters
can supply observed costs through the same supported canonical fields. The M1–M6
analytical modules and frozen detector are unchanged.

## Milestone 13 outcomes and ledger boundary
Outcome measurement consumes ready canonical warehouse models and matching public
observations through the existing acquisition metric registry. It binds source identity,
window, filters and evidence to a versioned decision record. It never reads lab truth,
generator objects or seeds. The ledger imports immutable opportunity evidence and
appends human action records, planned targets and descriptive measured outcomes.

Company adapters continue to normalize external data into canonical contracts; they do
not require changes to target arithmetic or outcome lifecycle logic. An observed target
comparison and its lesson are not causal evidence or economic action authorization.
