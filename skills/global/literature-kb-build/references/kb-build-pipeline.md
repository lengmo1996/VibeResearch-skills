# Literature KB Build Pipeline

## Generation layout

Keep source and derived state separate:

```text
<target>/
  generations/<generation-id>/
    source-inventory.jsonl
    kb_manifest.jsonl
    chunks/
    chunk-manifest.jsonl
    index/
    validation-report.json
  current
  rollback
```

The project may choose different names, but it must preserve generation isolation and
an explicit current/rollback mapping. Resolve paths before writes.

## Paper manifest minimum

Each JSONL record includes:

- `paper_id`, `source_path`, `source_sha256`, and `generation_id`;
- `metadata` plus field-level `metadata_provenance`;
- `metadata_confidence` and conflict/review status;
- `extraction_status`, parser/version, page coverage, and defect notes;
- eligibility and reason for chunking/indexing.

## Chunk contract

Chunk IDs derive deterministically from paper ID, policy version, ordered source span,
and content hash. Store section, pages, character/token span when available, source
hash, and content hash. Policy changes create a new generation.

## Promotion gate

Promotion requires:

1. manifest structural validation;
2. inventory/paper/chunk/index count reconciliation;
3. zero unexplained duplicate IDs or broken provenance;
4. thresholds for extraction and chunk coverage;
5. representative positive, section-specific, and negative retrieval probes;
6. a preserved previous generation and documented rollback.

Never promote from a partially failed command merely because some artifacts exist.
