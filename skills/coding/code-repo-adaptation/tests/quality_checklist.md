# Code Repo Adaptation Quality Checklist

- [ ] Source and target compatibility contracts are explicit.
- [ ] Surfaces, migration decisions, and expected invariants use stable IDs.
- [ ] The selected mode is compatibility-specific.
- [ ] Multiple compatibility axes are isolated or their coupling is justified.
- [ ] Repository understanding is limited to migration-relevant surfaces.
- [ ] Patch scope is minimal, reversible, and authorized.
- [ ] No ordinary bug, paper method, or unrelated refactor was absorbed.
- [ ] No minimal reproduction or final verification was performed.
- [ ] Changed paths, risks, deviations, and rollback notes are complete.
- [ ] Version-specific references match the target contract or are explicitly only hints.
- [ ] The unified verification request is complete and targets `code-debugging`.
