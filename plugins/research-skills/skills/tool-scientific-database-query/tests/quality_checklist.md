# Quality Checklist

- Target, identifiers, constraints, fields, scope, and deduplication key are frozen.
- Source API capability/version and documentation are recorded.
- Server and local filters remain distinct.
- Query values are structurally encoded and metadata is untrusted data.
- Pagination, ordering, rate limit, request/record budgets, and retry are planned.
- Every page has position, counts, status, and next state.
- Expected, retrieved, filtered, deduplicated, and final counts reconcile.
- Secrets never appear in the ledger.
- Zero hit and failures remain distinct.
- Completeness is source- and scope-specific.
