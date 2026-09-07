# Paper Triage Rubric

## Evidence levels

| Level | Available material | Maximum defensible claim |
|---|---|---|
| E0 | title only | topic guess; `insufficient-material` |
| E1 | title plus useful metadata | scope and provenance estimate |
| E2 | abstract | author-claimed problem, method outline, and claimed result |
| E3 | relevant full-paper sections | source-bounded fit and risk assessment |

Confidence follows evidence quality and identity consistency, not priority.

## Priority

- `P0`: directly changes an immediate research decision and has enough material to
  justify reading now.
- `P1`: likely useful soon, but not blocking the current decision.
- `P2`: plausible future reference with no near-term decision value.
- `P3`: outside scope, redundant for the objective, or too costly relative to value.

A high-priority low-confidence item is possible when resolving uncertainty is urgent.
A high-confidence P3 is possible when irrelevance is clear.

## Value roles

Choose one primary role: related-work context, baseline, method mechanism, dataset or
metric reference, negative evidence, reproduction candidate, or idea stimulus.
Secondary roles may appear in rationale.

## Next-action rule

Choose exactly one: obtain abstract/full text, deep read, inspect code provenance,
inspect dataset/protocol, retain for later, or skip. The action must resolve the
largest decision-relevant uncertainty or spend the next unit of reading budget.

## Batch calibration

Rank all candidates using the declared objective. Tie-break in order by immediate
decision value, evidence quality, information gain, then lower reading cost. Do not
force a quota, but explain why any large P0/P1 group is justified.
