# Literature KB Build Quality Checklist

- [ ] All seven Registry modes are present.
- [ ] Required source approval, target authorization, and indexing requirements gate writes.
- [ ] Source and derived generation paths are separate.
- [ ] Paper records include stable ID, source path/hash, generation, provenance, and status.
- [ ] Chunks include stable IDs, source spans/hashes, and policy version.
- [ ] Manifest validator self-test and target validation pass.
- [ ] Counts reconcile across inventory, eligible papers, chunks, and index.
- [ ] Representative retrieval probes include positive and negative cases.
- [ ] Failed records are quarantined and partial generations are not promoted.
- [ ] Prior generation and rollback instructions remain available.
- [ ] Metadata fields retain provenance and confidence; conflicts enter review instead of being chosen silently.
