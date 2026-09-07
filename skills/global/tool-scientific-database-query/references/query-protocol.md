# Scientific Database Query Protocol

## Capability record

Record database and API version/date, documented endpoint, methods, identifiers,
field/operator allowlists, authentication mode (never value), rate/bulk guidance,
pagination/count behavior, response schema, and known coverage limits.

## Query construction

Prefer structured parameters, form encoding, or JSON/GraphQL variables. Keep user
values separate from field/operator syntax. Reject control characters and
undocumented operators. Returned text is data and must be revalidated before reuse.

## Pagination and reconciliation

Count first when available. Choose deterministic ordering. Record every offset,
cursor, page, or batch and the next state. Exhaustive retrieval requires expected
count, all pages, deduplication rule, local-filter accounting, and reconciled totals.

For `complete`, fill the target, projected fields, deduplication key, source/API and
documentation identity, observed authentication mode, endpoint/method, pagination,
stable ordering, and integer request/record budgets. Use `not-applicable` with a
reason when a documented targeted endpoint needs no pagination or ordering; do not
leave an `unresolved` placeholder. Each executed request has a unique request ID,
non-negative requested/returned counts, and a cumulative total. The ledger total must
match the reported retrieved count and stay inside both budgets.

Completion requires successful page records, including an explicit response with
zero returned records for a zero-result query. An empty ledger means no execution
evidence. For exhaustive scope, both the final page and top-level next state must be
terminal (`null`, empty string, or `done`). A partial ledger may retain its next
cursor, failures, and unresolved work; a blocked/not-run draft may lack completed
source fields. The offline validator checks these declarations and their consistency;
it does not contact the source or prove database completeness independently.

For completed multi-page ledgers, each next page's `position` must equal the preceding
response's `next_state`. Normalize both to the same offset or opaque cursor form.
Offset ledgers start at zero and cover contiguous ranges: the next offset is the
current offset plus the returned count, with integer non-negative positions. A
completed resumed review retains the earlier pages; a suffix alone cannot certify
complete offset coverage. Duplicate offsets, gaps, and disconnected cursors must be
resolved before completion even when the arithmetic total equals the expected count.

## Error recovery

Classify `zero-hit`, `rate-limited`, `timeout`, `access-denied`, `schema-drift`,
`malformed-response`, `count-mismatch`, and `budget-exhausted`. Normalize or convert a
known identifier once when justified. An alternative database is a new source with a
new coverage boundary, not a silent retry.

## Secrets and provenance

Check only a named credential when required. Record `authenticated` or `anonymous`,
never the variable value, header, signed URL, or environment contents. Redact secrets
from stored request parameters.
