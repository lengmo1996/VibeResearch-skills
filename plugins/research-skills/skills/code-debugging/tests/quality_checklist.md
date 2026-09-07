# Code Debugging Quality Checklist

- [ ] The failure or verification request is normalized.
- [ ] A minimal reproduction is present or the exact blocker is stated.
- [ ] Root cause is supported by discriminating evidence.
- [ ] Hypotheses, evidence, and tests use stable IDs.
- [ ] A failure baseline and counterfactual/discriminating check support root cause.
- [ ] Any fix is minimal and explicitly authorized.
- [ ] Focused and relevant regression tests are recorded.
- [ ] The original reproduction is compared before and after the final patch.
- [ ] Every expected invariant/output has an observed result.
- [ ] The verdict is exactly `verified`, `failed`, or `blocked`.
- [ ] A blocked verdict identifies reproduction, environment, assertion, or authorization.
- [ ] Compatibility migration is handed to `code-repo-adaptation`, not performed here.
