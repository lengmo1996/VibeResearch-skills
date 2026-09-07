# Finding lifecycle

Load only for `closure` or an explicitly requested multi-pass audit. Do not load for
an initial one-pass audit.

## States

`open` → `accepted` → `fix-proposed` → `fix-applied` → `verified` → `closed`

Alternative states are `deferred` and `rejected`. A failed verification transitions
back to `open`; a new defect caused by a fix creates a linked `AUD-*` regression
record and prevents closure when it affects the original acceptance criterion.

## Preconditions

Require:

- the original `AUD-*` record and severity;
- original and revised locators or a traceable replacement;
- the claimed change and protected claims, data, formulas, citation keys, and
  uncertainty;
- the original verification method or an explicitly justified equivalent;
- revised material and any evidence required by the original audit mode.

An author's statement that a fix was made is not verification evidence.

## Closure procedure

1. Confirm the original finding still maps to the revised material.
2. Record the claimed change separately from the observed change.
3. Re-run the original verification method on the smallest sufficient scope.
4. Check protected content and neighboring text for regressions.
5. Record evidence references and one transition:
   - `verified` or `closed` only when the acceptance condition passes;
   - `open` when the defect remains or the fix regresses;
   - `deferred` when the owner accepts residual risk;
   - `rejected` only with a documented evidence-based disposition.
6. Preserve history. Do not overwrite the original finding or renumber its ID.

## Boundaries

Closure verifies a separately applied change. It does not apply the correction,
reinterpret raw experimental results, or certify manuscript areas outside the
original finding and regression scan.
