# Experiment Config Management Quality Checklist

Apply only checks relevant to the selected mode. Existing decisions may be reused;
a narrow policy question does not require a full run lifecycle or manifest.

- [ ] Scientific variables and infrastructure parameters are separate.
- [ ] Override precedence is deterministic.
- [ ] The fully materialized config has canonicalization and fingerprint rules.
- [ ] Seeds and nondeterminism sources are recorded.
- [ ] Run identity uses stable fields, not only timestamps.
- [ ] Checkpoint contents include RNG/data cursor and resume preconditions are explicit.
- [ ] Resume differences are classified `exact`, `compatible`, or `unsafe`.
- [ ] Results and artifacts link back to an immutable run manifest.
- [ ] Failed and interrupted runs remain in the result registry and lineage.
- [ ] No method implementation, migration, debugging, patch-verification or scientific
      verdict is performed; `run-lifecycle` may report its frozen protocol acceptance.
