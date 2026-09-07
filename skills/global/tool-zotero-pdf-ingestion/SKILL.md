---
name: tool-zotero-pdf-ingestion
description: "Use when Zotero records and a PDF source set must be inventoried, reconciled, deduplicated, exported, or prepared as safe inputs for a local literature corpus. Produces a provenance-rich reconciliation manifest, duplicate/missing-attachment report, and clean export. Do not use to build an index, analyze papers, or modify Zotero/PDFs without explicit authorization."
---

# Tool Zotero PDF Ingestion

## Purpose

Reconcile bibliographic records and physical PDF identities without treating Zotero,
filenames, or fuzzy similarity as unquestioned truth. Preserve ambiguous matches,
versions, loose PDFs, and missing attachments for review.

Use `$literature-kb-build` after the manifest is approved for corpus construction.
This Skill does not embed, index, read papers scientifically, or mutate Zotero by
default.

## Inputs

Required: Zotero export or accessible local library metadata and a PDF source set.
Optional: collection filter, attachment roots, citation-key policy, deduplication
rules, export format, prior reconciliation manifest, and authorized output target.

Resolve source roots, exclusions, read access, output path, and whether Zotero is
read-only before work. Never assume access to a local library or storage directory.

## Modes

| Mode | Deliverable |
|---|---|
| `inventory` | Zotero record and PDF/attachment inventories |
| `reconcile` | record ↔ PDF match candidates, decisions, conflicts, missing sides |
| `deduplicate` | duplicate/version groups without destructive merge |
| `export` | authorized clean manifest/export |
| `prepare-kb` | validated downstream manifest and unresolved-review queue |

## Workflow

1. Read [reconciliation protocol](references/reconciliation-protocol.md). Freeze
   source identities, collection/exclusion scope, and output policy.
2. Inventory Zotero items, attachments, and loose PDF files separately. Hash PDFs
   without modifying them; retain normalized and original paths.
3. Normalize DOI, arXiv ID, ISBN/other identifiers, title, authors, year, and citation
   key while preserving original values and provenance.
4. Apply exact evidence first: attachment relation, content hash, stable identifier,
   or verified record key. Record conflicts even when an exact field matches.
5. Generate fuzzy title/author/year candidates only for review. A similarity threshold
   ranks candidates; it never proves identity.
6. Preserve one-to-many attachments, versions, supplementary files, duplicate records,
   loose PDFs, and missing PDFs as explicit relationship/status types.
7. Record each match/merge/keep-separate decision with evidence, confidence, method,
   reviewer requirement, and alternatives. Never delete or move originals.
8. Validate the proposed JSONL manifest with
   `scripts/validate_reconciliation_manifest.py`.
9. Write/export only after exact target and format authorization. `prepare-kb` passes
   approved records and a separate unresolved queue to `$literature-kb-build`.

## Match and deduplication policy

Exact evidence can establish a relationship only when contradictory identity fields
are resolved or retained as conflict. Fuzzy similarity is a candidate. Duplicate
records and duplicate PDF bytes are different concepts; version relationships are
not duplicates by default.

Every decision is one of `matched`, `loose_pdf`, `missing_pdf`, `conflict`,
`candidate_match`, `duplicate_group`, or `needs_review`. Low-confidence records are
kept, not discarded.

## RAG and side effects

RAG is `never`. Use Zotero/local metadata and PDFs only within the authorized scope.
Read-only Zotero access does not authorize writes, collection edits, attachment
changes, item merge, deletion, or metadata correction.

An export or corpus manifest is a local write requiring an authorized target.
Preserve originals and prior exports. Never include credentials, private notes, or
unrequested attachment contents.

## Output contract

Use [reconciliation-report.md](templates/reconciliation-report.md) and
[record example](templates/reconciliation-record.example.json). Return:

- scoped record/PDF inventories and source counts;
- relationship and duplicate/version groups with evidence;
- missing attachment, loose PDF, metadata conflict, and review queues;
- validated clean export/KB-ready subset when authorized;
- decisions not applied to Zotero or original files.

## Failure behavior

If library metadata or PDF access fails, report which inventory is incomplete and do
not infer the missing side. If identities conflict or fuzzy candidates tie, keep them
unresolved. A validator failure blocks export/prepare-kb completion.

## Validation checklist

- [ ] Canonical mode, sources, collection/exclusions, and output policy are explicit.
- [ ] Zotero items, attachments, and loose PDFs are inventoried separately.
- [ ] Original and normalized identifiers retain provenance.
- [ ] Exact, contradictory, and fuzzy evidence are distinct.
- [ ] Fuzzy matches and ties require review.
- [ ] Duplicates, versions, supplementary files, and one-to-many relations are preserved.
- [ ] Manifest validation passes before export or KB handoff.
- [ ] No Zotero or PDF mutation occurs without separate explicit authorization.

## Shared contracts and stop conditions

Follow [approval](../../_shared/approval-workflow.md),
[file safety](../../_shared/file-mutation-safety.md),
[operational boundaries](../../_shared/operational-boundaries.md), and
[evidence](../../_shared/evidence-policy.md). Stop when records are reconciled or
conflicts isolated, or when source access/authorization is unavailable.
