# Review panel protocol

Load only for `panel-review`. This protocol separates reviewer observations from
synthesis; it does not manufacture independent agents when the runtime cannot isolate
contexts.

## Freeze the shared input

Record one immutable manuscript snapshot, supplied supplementary artifacts, venue
assumptions, review questions, and unavailable evidence. Every reviewer receives the
same snapshot and may receive only the evidence required by that review focus.

## Declare execution status

Use exactly one status:

- `independent`: each reviewer used an isolated context, could not inspect other
  reviewer outputs before submitting, and returned a sealed record;
- `simulated-separation`: one context produced role-scoped passes sequentially.

Never infer independence from different role labels. If isolation cannot be
established, use `simulated-separation`.

## Collect reviewer records

Use at least two justified roles; prefer three to five when scope and runtime permit.
Possible focuses include contribution, methods, experimental validity,
reproducibility, ethics/limitations, and presentation. Each reviewer records:

- reviewer ID, role, focus, materials and evidence available;
- strengths, location-specific findings, and author questions;
- severity, evidence state, uncertainty, and recommendation rationale;
- checks not performed.

Do not expose one reviewer record to another before all records are sealed.

## Synthesize after collection

Map reviewer-local findings to stable `AUD-*` records. Assign one status:

- `consensus`: at least two reviewers independently support the same root cause;
- `single-supported`: one reviewer provides sufficient location-specific evidence;
- `conflict`: reviewer verdicts disagree on the same question;
- `unresolved`: required evidence is absent or contradictory.

Agreement count does not replace evidence quality. Preserve a `single-supported`
finding when it is material, and preserve both sides of a conflict with their
evidence and uncertainty.

## Close the loop

Send accepted `AUD-*` records to `$writing-academic` only after synthesis. For a
separately revised manuscript, use `closure` and retain reviewer IDs in verification
provenance. Do not rerun a whole panel when the original verification method requires
only one bounded check.
