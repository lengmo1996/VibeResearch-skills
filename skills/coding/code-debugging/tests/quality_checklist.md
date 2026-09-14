# Code Debugging Quality Checklist

Apply only checks relevant to the requested diagnosis, repair, or verification.
Failure baselines and causal claims apply to defect work; new candidates are checked
against target inputs, invariants/outputs, and relevant regression.

- [ ] The failure or verification request is normalized.
- [ ] Required target execution or defect reproduction is present, or its blocker is stated.
- [ ] Any claimed root cause is supported by discriminating evidence.
- [ ] Hypotheses, evidence, and tests use stable IDs.
- [ ] A claimed defect cause has a failure baseline and discriminating evidence.
- [ ] Any fix is minimal and explicitly authorized.
- [ ] Focused and relevant regression tests are recorded.
- [ ] A defect fix compares the original reproduction before and after the patch.
- [ ] Every expected invariant/output has an observed result.
- [ ] The verdict is exactly `verified`, `failed`, or `blocked`.
- [ ] A blocked verdict identifies reproduction, environment, assertion, or authorization.
- [ ] Compatibility migration is handed to `code-repo-adaptation`, not performed here.
