# Code Repo Adaptation Quality Checklist

Check only selected-mode requirements. Decision IDs, patch paths, rollback details,
and verification handoffs apply to actual patches or an explicitly requested plan.

- [ ] Source and target compatibility contracts are explicit.
- [ ] Surfaces, migration decisions, and expected invariants use stable IDs.
- [ ] The selected mode is compatibility-specific.
- [ ] Multiple compatibility axes are isolated or their coupling is justified.
- [ ] Repository understanding is limited to migration-relevant surfaces.
- [ ] Patch scope is minimal, reversible, and authorized.
- [ ] No ordinary bug, paper method, or unrelated refactor was absorbed.
- [ ] Verification belongs to the `$code-debugging` stage; an already-authorized
      implementation and validation task continues through that stage without waiting.
- [ ] Changed paths, risks, deviations, and rollback notes are complete.
- [ ] Version-specific references match the target contract or are explicitly only hints.
- [ ] Any required verification request is complete and targets `$code-debugging`.
