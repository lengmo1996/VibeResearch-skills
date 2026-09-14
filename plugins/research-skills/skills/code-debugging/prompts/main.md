# Code Debugging Prompt

Run the smallest evidence-producing loop:

Execute only steps needed for the requested diagnosis, repair, or verification.
Tests and a verification verdict apply only when that verification work is required;
a narrow diagnosis or minimal-reproduction answer need not produce a full verdict.

1. Normalize the failure or verification request.
2. For defects, reproduce and minimize the symptom; for new candidates, exercise
   the declared target inputs and assertions.
3. When diagnosing a defect, rank hypotheses and run discriminating checks.
4. Support any root-cause claim or mark it unconfirmed; do not require a root-cause
   investigation for a new candidate with no original defect.
5. Apply only an explicitly authorized minimal fix.
6. Run focused tests and the smallest relevant regression suite.
7. Evaluate every declared invariant and expected output.
8. Return `verified`, `failed`, or `blocked`.

If the root cause requires compatibility migration, hand the diagnosis to
`$code-repo-adaptation`. When the current request authorizes migration and validation,
continue those stages and verify the returned patch in the same task. Otherwise
report the diagnosis and the additional scope required.
