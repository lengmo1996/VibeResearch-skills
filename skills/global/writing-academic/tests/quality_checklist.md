# Writing Academic Quality Checklist

General release checks moved from `SKILL.md`. Structure and naturalness specifics are
in `structure_quality_checklist.md` and `naturalness_quality_checklist.md`.

- [ ] Meaning, data, formulas, citations, and uncertainty are preserved.
- [ ] Mode and audience are explicit.
- [ ] Whole-paper work loaded the lifecycle reference without preloading every section guide.
- [ ] A paper-context patch contains only thin state and artifact references and is not persisted implicitly.
- [ ] Related work has an evidence map and required RAG.
- [ ] Terminology and symbols are consistent.
- [ ] No long-source imitation or fabricated content appears.
- [ ] De-template work consumed accepted findings without rerunning a full audit.
- [ ] Author-voice work used only an author-owned task-local sample or approved profile and did not persist it.
- [ ] High-risk rewrites passed literal protected-span validation or exposed the failed span IDs.
- [ ] A low-signal naturalness request was allowed to return `no change needed`.
- [ ] Compression measured the requested target and preserved protected scientific content.
- [ ] Revision patches use contained paths, unique block IDs, exact target/block hashes, atomic apply, and fail closed on drift.
- [ ] Patch validation and patch application are reported separately; validation never implies write authorization.
- [ ] Every prose mode ends with the brief pattern check from `_shared/output-voice.md`; notes around the text follow the same policy.
