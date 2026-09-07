# Migration Decision Protocol

## Stable identities

- `SURF-*`: one compatibility surface and axis, such as Python runtime, dependency API,
  data layout, launch contract, inference interface, or checkpoint schema.
- `DEC-*`: one migration choice with alternatives and constraints.
- `INV-*`: one observable target invariant for downstream verification.

Each changed path maps to at least one decision; each decision maps to source/target
evidence, affected surfaces, rollback, and verification invariants.

## Contract comparison

For each surface record:

1. observed source contract and repository anchor;
2. explicit target contract and authoritative evidence;
3. incompatibility, or `compatible-no-change`;
4. hard constraints and acceptable deviations;
5. smallest migration decision;
6. expected invariant and rollback.

Do not infer target behavior only from a migration error or a dated internal reference.

## Axis isolation

Prefer one axis at a time: environment, dependency, framework API, dataset, training,
inference, or checkpoint. When axes are coupled, explain the dependency and keep
separate decision IDs. An unrelated defect is handed to `$code-debugging`.

## Candidate status

Repository inspection and a coherent patch establish only a candidate migration.
Downstream `$code-debugging` owns reproduction and all `INV-*` verdicts. A rollback
description is required even when the patch is small.
