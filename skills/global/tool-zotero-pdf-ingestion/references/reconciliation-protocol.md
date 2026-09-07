# Zotero–PDF Reconciliation Protocol

## Inventory identities

Assign separate IDs to bibliographic records, attachment relations, and physical PDF
files. A Zotero item without a PDF and a loose PDF without a record remain valid
inventory entries.

## Evidence classes

1. relationship evidence: Zotero attachment link or verified record key;
2. byte identity: SHA-256 content hash;
3. stable metadata: normalized DOI, arXiv ID/version, ISBN, or another source ID;
4. descriptive metadata: title, authors, year, venue;
5. filename/path similarity.

Classes 4–5 rank candidates but do not prove identity. Contradictory stable metadata
forces conflict/review even when another field matches.

## Relationship types

Record one-to-one, one-record-many-files, many-records-one-file, version-of,
supplementary-to, duplicate-record, duplicate-bytes, candidate, and unresolved. Do
not collapse versions, supplementary files, or duplicate records into deletion.

## Decision ledger

Every decision records method, evidence items, confidence, alternative candidates,
review requirement, and actor/source when manually resolved. Automated fuzzy matching
always retains `review_required: true`.

## KB handoff

Pass only validated approved relationships as KB-ready. Pass loose PDFs with explicit
metadata uncertainty when allowed by the downstream policy. Keep missing PDFs,
conflicts, ties, and candidate matches in the unresolved queue.

`kb_ready: true` is allowed only for `matched` or an explicitly admitted `loose_pdf`
with a PDF/hash, no remaining conflicts, and `review_required: false`. The match
decision must carry an `approval` object with `status: approved`, `actor`,
`approved_at`, and an `evidence` reference to the actual record-specific or scoped
manifest approval. Never fill these fields from a validator pass. The example record
is unapproved and therefore defaults to `kb_ready: false`.
Approval actor, time, and evidence cannot be blank or placeholders such as
`unresolved`, `unknown`, `TBD`, or `<actual approval reference>`. Rejecting placeholders
does not authenticate an approval; it only prevents incomplete records from asserting
KB readiness.

Automated fuzzy methods remain review candidates even if an approval field is
present. After actual manual identity verification, record `method: manual-review`,
retain the former method/evidence, and cite the decision before considering KB-ready.
Duplicate groups require choosing and approving the concrete relationship; do not
send an unresolved group wholesale. The validator checks supplied fields and state
consistency only; it does not inspect PDF bytes or authenticate the user's approval.
