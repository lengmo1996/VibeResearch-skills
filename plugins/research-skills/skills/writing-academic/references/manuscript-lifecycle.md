# Full-manuscript lifecycle

Load this reference only when the user asks to plan or draft a whole paper, coordinate
several manuscript sections, or reconcile an existing full-paper plan. Do not load it
for one-section outlines, local rewrites, grammar, translation, naturalness, or
reviewer-response work.

## Establish a thin context

Use the shared `paper-context` contract as a task-local index. Record only the problem,
gap, contribution candidates, claim IDs, section order, decisions, and references to
artifacts. Do not copy the manuscript, private reviews, raw logs, unpublished results,
or source documents into the context. Persistence remains false unless the user
separately authorizes their own project-memory workflow.

## Build the paper in evidence order

1. **Frame provisionally.** Draft a compact problem–gap–contribution map and a
   provisional introduction plan. Treat it as revisable, not as locked prose.
2. **Plan evidence-bearing sections.** Order method, experiments, analysis, related
   work, limitations, and other sections according to their actual dependencies.
   Evaluation may precede method prose when results determine safe claim strength;
   method may precede evaluation when interfaces must be fixed first.
3. **Bind claims.** Give each central claim a stable ID and attach verified evidence,
   a visible missing-evidence marker, or an explicit assumption.
4. **Draft one section at a time.** Load at most one applicable section guide. Give
   every paragraph one dominant function and keep terminology, symbols, component
   order, and claim strength consistent with the current context.
5. **Rewrite the framing.** After evidence-bearing sections stabilize, revisit the
   introduction and contribution list. Draft the abstract last unless the user needs
   an earlier provisional abstract.
6. **Integrate and compress.** Reconcile cross-references, figures, tables, terminology,
   limitations, and claim strength before reducing length.

This sequence is a dependency-aware default, not a mandatory five-stage ritual. Skip
stages that do not serve the requested deliverable.

## Lock and reopen decisions

- Lock only user-confirmed terminology, symbols, contribution identity, immutable
  facts, citation keys, and venue constraints.
- Keep unsupported mechanism claims, missing comparisons, unresolved section order,
  and tentative wording open.
- Reopen a decision when later evidence contradicts it; record the conflict instead
  of silently rewriting history.

## Stop and recovery

Stop when the requested plan or draft is complete, evidence needed for the next claim
is missing, or continuing would require scientific invention. If two consecutive
passes only rearrange prose without improving evidence coverage, section function, or
constraint satisfaction, report `no material progress` and list the blocking decision.
