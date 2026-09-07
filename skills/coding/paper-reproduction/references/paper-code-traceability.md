# Paper–Code Traceability Protocol

## Innovation evidence

Record the paper's claimed contribution, its exact page/section/equation anchor,
the changed mechanism or assumption, and what the supplied evidence demonstrates.
Separate author-stated novelty from an independently established novelty claim.
List material unknowns. An innovation-only report requires no repository search,
code mapping, implementation specification, or verification request.

## Repository provenance

For each candidate repository, record its URL/identity, the inspected paper/project
page or author link establishing ownership, inspected revision/date, scope covered,
and confidence. Use `official`, `author-maintained`, `third-party`, or `uncertain`
only with the corresponding evidence. Record inaccessible candidates and conflicting
ownership evidence. A bounded unsuccessful search supports "no official code found
within this search", not "no official implementation exists".

Return these records as Repository Provenance. No code-map or implementation
sections are required when discovery is the entire request.

## Mapping rule

Assign a stable `MAP-*` ID to each paper-to-code relationship. A mapping is complete
only when it records:

- exact paper anchor and observed statement;
- method, equation, algorithm, or architecture role;
- repository identity and revision when available;
- file and symbol, or an explicit `not mapped`;
- evidence class: paper fact, code fact, or mapping inference;
- confidence and the missing evidence that could change it.

Naming similarity alone is not mapping evidence.

For `code-mapping`, include the observable invariant for each decision-relevant
mapped module and the unresolved links. Stop at the map; a runnable implementation
or a full tensor specification is not required unless separately requested.

## Implementation specification

Reuse accepted paper anchors and mapping IDs. Specify only the requested module,
loss, or algorithm: inputs/outputs, tensor shapes, state, pseudocode, error cases,
integration points, and observable invariants. Keep unresolved paper choices visible.
Do not regenerate unrelated paper analysis or repository discovery. For a blocked
or unchanged implementation request, report the exact status and remaining work.

## No official code

Bind the supplied no-code premise or bounded discovery result. Distinguish paper
fact, design inference, and engineering choice; identify unknowns that could change
behavior. A specification may be complete while implementation remains unauthorized
or blocked. Do not claim semantic/numerical equivalence to an unavailable official
implementation. Any authorized patch follows the same candidate and handoff rules.

## Engineering decisions

Assign `DEC-*` to any implementation choice the paper or verified code does not fix,
including tensor layout, default value, initialization, interpolation, numerical
stabilizer, error behavior, or integration surface.

Each decision records alternatives, selection reason, affected `MAP-*` IDs, and one
observable invariant. Unknown choices remain unresolved; do not hide them behind a
reasonable-looking default.

## Patch trace

Load this section only when an implementation patch was produced. Without changed
code, there is no patch verification request to emit.

Every changed core-method file must cite the mapping or decision IDs it realizes in
the report. The verification handoff carries those IDs so failure can be traced back
to evidence, inference, or engineering choice without reopening the full paper.
