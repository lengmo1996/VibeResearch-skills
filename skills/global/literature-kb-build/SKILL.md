---
name: literature-kb-build
description: "Use when an approved PDF corpus must be inventoried, metadata-reconciled, extracted, deterministically chunked, indexed, or verified as a reproducible local literature knowledge base. Produces versioned corpus artifacts, manifests, and a quality report. Do not use to query an existing library, reconcile Zotero alone, or synthesize papers."
---

# Literature KB Build

## Purpose

Turn an approved source corpus into a local, evidence-preserving, versioned retrieval
artifact. Source files remain immutable; every derived record retains provenance; a
new generation is promoted only after validation.

Use `$tool-zotero-pdf-ingestion` when record/attachment reconciliation is primary,
`$literature-synthesis` for analysis, and `$paper-deep-read` for one paper. This Skill
never writes to the read-only KnowledgeHub service.

## Inputs and authorization gate

Required:

- approved source corpus and confirmed rights/scope;
- target local artifact location with write authorization;
- indexing requirements, including retrieval unit and acceptance needs.

Optional: metadata records, chunk policy, parser/runtime choices, embedding model,
vector store, deduplication keys, prior generation, resource budget, and retention
policy.

Before any write, resolve source roots, target root, exclusions, expected artifact
classes, overwrite/promotion behavior, and rollback generation. Missing rights,
target authorization, or storage safety stops mutation.

## Modes

| Mode | Deliverable |
|---|---|
| `inventory` | immutable source inventory and hashes |
| `metadata` | field-level metadata candidates, provenance, conflicts, review queue |
| `extract` | evidence-preserving text/structure extraction and quality statuses |
| `chunk` | deterministic chunks with source spans and policy version |
| `index` | staged index and index manifest |
| `verify` | structural, coverage, provenance, and retrieval quality report |
| `full` | all phases in order, ending in validated promotion |

## Workflow

1. Read [KB build pipeline](references/kb-build-pipeline.md). Freeze a generation ID,
   source snapshot, policies, tool/runtime versions, and acceptance thresholds.
2. Inventory files without modifying them. Record normalized relative source path,
   size, mtime as observation, and SHA-256; detect unreadable/unsupported inputs.
3. Reconcile metadata field by field. Preserve every candidate source and confidence;
   quarantine conflicts instead of choosing silently.
4. Extract text/structure into staging. Record parser, version, page coverage,
   extraction defects, OCR need, and evidence spans.
5. Chunk deterministically. Every chunk carries stable paper/chunk IDs, source hash,
   section/page/span, content hash, and chunk-policy version.
6. Build the requested index only inside the generation staging area. Keep embedding
   model identity/version and index parameters in the manifest.
7. Run structural validation with
   `scripts/validate_kb_manifest.py`, then coverage, provenance, duplicate, and
   representative retrieval checks.
8. Promote the generation only when acceptance passes and authorization covers the
   target update. Keep the prior generation and rollback pointer.

Run only the phase selected by the narrowest mode. A later phase requires validated
artifacts from its predecessors; never simulate them.

## Artifact contract

Use [kb-build-report.md](templates/kb-build-report.md). A full build normally includes:

- source inventory and `kb_manifest.jsonl`;
- metadata provenance/conflict and manual-review records;
- extracted paper artifacts and chunk manifest/content;
- index manifest and retrieval usage notes;
- validation report, generation metadata, promotion state, and rollback target.

Artifact names may follow project requirements, but their schema/version and mapping
must be explicit. Missing metadata does not discard a source PDF.

## Validation

Structural checks are necessary but insufficient. Acceptance also covers:

- inventory count/hash reconciliation and source immutability;
- metadata conflict and unresolved-record accounting;
- extraction/page coverage and parser/OCR failure rates;
- chunk uniqueness, span provenance, deterministic rebuild sample;
- index/document/chunk count reconciliation;
- representative known-item, section, and negative retrieval probes;
- prior-generation preservation and rollback instructions.

Do not describe an index as verified when only files exist or embeddings completed.

## Side effects and recovery

All derived writes occur under the approved target staging generation. Never overwrite
source PDFs. Never delete duplicates by default. On failure, preserve sources and the
prior promoted generation, quarantine failed records, and report the exact resumable
phase. Cleanup of staging artifacts requires separate target confirmation.

## Failure behavior

Stop the affected phase on corrupt inputs, metadata ambiguity that changes identity,
unsafe target resolution, missing parser/index runtime, validation failure, or
insufficient storage. Return partial artifact status without promoting it.

## Validation checklist

- [ ] Source rights/scope, target, generation, policies, and acceptance thresholds are fixed.
- [ ] Source PDFs are immutable and inventoried by hash.
- [ ] Metadata fields retain provenance/confidence and conflicts enter review.
- [ ] Extraction and chunks retain exact source spans and policy/tool versions.
- [ ] Index counts reconcile with eligible papers/chunks.
- [ ] Structural and representative retrieval validation both run.
- [ ] Failed records are quarantined and no partial generation is promoted.
- [ ] Prior generation and rollback path remain intact.

## Shared contracts and stop conditions

Follow [approval](../../_shared/approval-workflow.md),
[file safety](../../_shared/file-mutation-safety.md),
[operational boundaries](../../_shared/operational-boundaries.md), and
[evidence](../../_shared/evidence-policy.md). RAG policy is `never`: this Skill builds
local artifacts and does not retrieve from or write to KnowledgeHub. Stop when the
selected phase passes acceptance or any source-rights, target, runtime, storage, or
validation gate fails.
