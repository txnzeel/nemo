# NEMO repository workflow

## User-authorized milestone publishing
The user requested that verified milestone updates be committed and pushed to
https://github.com/txnzeel/nemo.git on main.

After completing each authorized milestone:
- Update README milestone status, the milestone report, and relevant learning guides.
- Run the repository's configured validation and report material limitations honestly.
- Review the diff and commit the completed milestone with a descriptive message.
- Push to origin/main without requesting permission again for this authorized workflow.
- Preserve remote history; do not force-push.
- Keep generated artifacts, private lab truth, credentials and local runtimes out of Git.

Complete one milestone at a time, then stop until the user says proceed.
Publishing authorization does not authorize starting additional milestones automatically.

## Architectural and evidence boundaries
Analytics consumes canonical observations or warehouse models, never generator internals,
private truth, seeds or simulation parameters. Production adapters must map into the
canonical contracts. Preserve exact-money and existing metric definitions. Distinguish
observations, descriptive metrics, diagnostic hypotheses and causal evidence.
Do not call merchandise receipts profit.

## Learning and validation
Provide learning guides with implemented milestones. Before introducing a major new
concept, explain its meaning, business purpose, example, formula, data requirements,
implementation, failure modes and interview explanation.

Use configured pytest, Ruff lint/format, package builds and applicable dbt checks.
No type checker is currently configured. Keep external integration claims separate
from verified local behavior.
