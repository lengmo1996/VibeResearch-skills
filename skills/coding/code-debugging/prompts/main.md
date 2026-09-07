# Code Debugging Prompt

Run the smallest evidence-producing loop:

1. Normalize the failure or verification request.
2. Reproduce and minimize the symptom.
3. Rank hypotheses and run discriminating checks.
4. Prove the root cause or mark it unconfirmed.
5. Apply only an explicitly authorized minimal fix.
6. Run focused tests and the smallest relevant regression suite.
7. Evaluate every declared invariant and expected output.
8. Return `verified`, `failed`, or `blocked`.

If the root cause is compatibility migration, stop after the diagnosis handoff to
`code-repo-adaptation`; verify the returned patch later.
