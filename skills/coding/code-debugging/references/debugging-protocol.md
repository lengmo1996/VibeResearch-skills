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

1. Capture the failing `TST-*` baseline.
2. Use temporary diagnostics one variable at a time when feasible.
3. Remove diagnostics from the final patch unless intentionally retained.
4. Apply the minimal authorized fix.
5. Rerun the exact baseline, focused invariant tests, then relevant regression.
6. If multiple material changes were necessary, narrow the root-cause claim.

## Verdict classes

- `verified`: target behavior, original reproduction, declared invariants/outputs, and
  regression surface pass with no invalidating unresolved item.
- `failed`: an assertion fails or the original symptom remains.
- `blocked`: required reproduction, environment, assertion, or authorization is
  unavailable; name which and what would unblock it.
