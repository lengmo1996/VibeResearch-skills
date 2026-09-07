# Operational Boundaries

These rules are canonical for active Skills' Cross-Skill contracts:

1. **Upstream input trust**: use only material supplied by the user, retrieved from an authorized source, or explicitly produced by an upstream Skill. Mark missing information `not provided / unclear`; do not fill it from assumption.
2. **Conflict handling**: select the smallest Skill that owns the current artifact and action. Use exactly one primary Skill and at most two supporting Skills; when composition is necessary, pass a single task-local handoff and never create an automatic loop.
3. **Evidence classification**: for judgments about papers, experiments, code, submissions, or project memory, distinguish `verified fact`, `reasonable inference`, and `unconfirmed hypothesis`. Preserve contrary evidence and uncertainty.
4. **Profile use**: load only stable fields relevant to the current decision (for example project, research direction, dataset, metric, venue, or environment). The current explicit request overrides Profile defaults; missing Profile fields are not required inputs.
5. **Unrelated-domain suppression**: do not invoke or hand off to geographic, sports, medical-review, or other unrelated domain capabilities merely because they are available. They enter the route only when the user's current task explicitly requires them.

Each Skill still owns its narrow primary scope, specific upstream requirements, downstream handoff, and prohibited overlap. User-provided material takes precedence, and supporting Skills reuse already-read files, retrieval results, terminology decisions, and evidence ledgers.

For details, follow the canonical [evidence](evidence-policy.md), [output](academic-output-contracts.md), [approval](approval-workflow.md), and [file mutation](file-mutation-safety.md) policies.
