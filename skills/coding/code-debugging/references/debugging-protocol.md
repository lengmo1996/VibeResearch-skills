# Debugging Protocol

## Evidence identities

- `HYP-*`: a causal hypothesis with a predicted observation.
- `EV-*`: one command/input/observation tied to an environment.
- `TST-*`: one assertion-bearing reproduction or regression check.

Preserve IDs across iterations so rejected explanations and changed assumptions remain
auditable.

## Root-cause gate

A root-cause claim needs:

1. a reproducible failure baseline, or a precise reason reproduction is impossible;
2. a mechanism linking state/control/data to the symptom;
3. a check whose outcome differs across competing hypotheses;
4. evidence against the strongest alternative;
5. confidence and the condition that would overturn the finding.

Temporal proximity, suspicious code, or “the patch made it pass” alone is insufficient.

## Fix-causality sequence

Use this sequence for a defect fix or root-cause claim. For a new candidate without
an original defect, execute its target inputs and invariant/output assertions plus
relevant regression; do not fabricate a failure baseline or causal investigation.

1. Capture the failing `TST-*` baseline.
2. Use temporary diagnostics one variable at a time when feasible.
3. Remove diagnostics from the final patch unless intentionally retained.
4. Apply the minimal authorized fix.
5. Rerun the exact baseline, focused invariant tests, then relevant regression.
6. If multiple material changes were necessary, narrow the root-cause claim.

## Verdict classes

- `verified`: target behavior, declared invariants/outputs, and relevant regression
  pass with no invalidating unresolved item; defect fixes also require the original
  failure to be resolved. New candidates do not need a nonexistent old failure.
- `failed`: an assertion fails or the original symptom remains.
- `blocked`: required reproduction, environment, assertion, or authorization is
  unavailable; name which and what would unblock it.
