# Visual story contract

Load only when an artifact belongs to a manuscript, report, or multi-figure family.
Do not load for a truly standalone visual with no declared claim or companion.

## Narrative role

Assign one primary role:

- `overview`: orient the reader to the whole system or argument;
- `problem`: expose the limitation, setting, or research question;
- `method`: explain components, data flow, or mechanism without asserting results;
- `evidence`: visualize protocol-valid observations supporting or challenging a claim;
- `diagnostic`: expose failure, sensitivity, ablation, or uncertainty;
- `limitation`: communicate scope, boundary, or unresolved risk;
- `standalone`: no paper-level sequence or companion relation is supplied.

A figure may support several claims, but it should have one primary narrative job.

## Claim and evidence linkage

Reuse upstream `CLM-*` and supplied artifact/result references. Each visual assertion
must map through `SRC-*` to one or more `ELEM-*` or `PAN-*` records. A method schematic
may link to an assumption or user-provided specification; an evidence figure requires
verified result data. Do not convert a candidate or missing evidence record into a
visual assertion.

## Cross-figure relationships

Use `precedes`, `follows`, `elaborates`, `contrasts`, `shares-encoding`, or
`independent`. Record terminology, color, symbol, scale, ordering, and entity identity
that must remain consistent. A relation is not an instruction to duplicate content.

If a companion artifact is unavailable, record the expected invariant as unchecked
instead of claiming consistency.

## Caption boundary

The specification may state the figure's factual message, referenced IDs, and claims
the evidence permits. Final manuscript caption wording belongs to
`$writing-academic`; claim auditing belongs to `$writing-manuscript-audit`.
