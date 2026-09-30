---
name: code-debugging
description: "Reproduce, diagnose, and verify a concrete code failure, minimally fixing it when authorized: tracebacks, NaN/OOM, shape/dtype/device errors, deadlocks, regressions, or candidate patches (报错排查、训练 NaN、显存溢出、修 bug). Returns an evidence-backed root cause and a verification verdict."
---

# Code Debugging

## Purpose

`code-debugging` owns the complete defect and verification loop:
minimal reproduction → evidence → root cause → minimal fix → focused tests → verdict.
It is also the final verifier for candidate code produced by `paper-reproduction` and
`code-repo-adaptation`.

Apply the shared [evidence](../../_shared/evidence-policy.md) rules to reproductions and
root-cause claims. Use the [approval workflow](../../_shared/approval-workflow.md) and
[file mutation safety](../../_shared/file-mutation-safety.md) before patching, while
[operational boundaries](../../_shared/operational-boundaries.md) constrain diagnostic
commands and environment access.

## Inputs

At least one of: failing behavior, traceback, logs, failing test, reproduction steps,
candidate patch, or a unified `verification_request`. Useful context includes relevant
code/config, environment facts, recent changes, expected behavior, and resource
constraints.

Applying a fix requires explicit authorization. Read-only reproduction and diagnostics
do not authorize repository migration.

## Modes

- `minimal-reproduction`: reduce the failure to the smallest deterministic example,
  input, command, or test that preserves the symptom.
- `traceback`: trace exception origin, state, control flow, and causal code path.
- `numerical`: diagnose NaN/Inf, OOM, shape, dtype, device, precision, gradient, or
  stability failures.
- `runtime`: diagnose performance, deadlock, DDP, synchronization, I/O, memory, or
  resource anomalies.
- `regression`: identify the change or invariant break that caused behavior to regress.
- `patch-verification`: execute the declared reproduction steps and assertions for a
  candidate patch, then issue an evidence-backed verdict.

## Workflow

Execute only steps needed for the requested analysis, repair, or verification.
A traceback explanation or minimal-reproduction request does not authorize a fix
or require a full patch-verification report.

1. Normalize the failure or `verification_request` and note which fields are
   missing.
2. For a defect, reproduce before diagnosing whenever feasible. For a new candidate,
   exercise the declared target inputs and assertions. Record commands, inputs,
   observed outputs, determinism, and relevant environment facts.
3. Minimize a failing reproduction without changing the failure mechanism. A new
   candidate with no original defect does not require a manufactured failure baseline.
4. Read [debugging protocol](references/debugging-protocol.md). Assign stable
   `HYP-*`, `EV-*`, and `TST-*` IDs; rank hypotheses and run checks that distinguish
   them rather than merely collect compatible observations.
5. Identify the root cause only when evidence includes a failure baseline and a
   discriminating or counterfactual check. Otherwise mark it unconfirmed.
6. If authorized, apply the smallest fix that addresses the proven cause; avoid
   opportunistic refactoring.
7. For defect fixes, compare the original reproduction before/after. For new
   candidates, check target behavior and declared invariants/outputs. Run the
   smallest relevant regression checks; reuse completed checks that cover the same
   assertions instead of repeating them under another label. Separate diagnostics
   from the final patch.
8. For a handoff, compare actual behavior with every expected invariant/output and
   return `verified`, `failed`, or `blocked`.

## Compatibility boundary

Do not perform Python/PyTorch/CUDA/dependency/framework migration, dataset-layout
migration, training/inference pipeline porting, or checkpoint-format conversion.

If evidence shows the root cause is a compatibility mismatch:

1. report the minimal reproduction and diagnosis evidence;
2. hand off the source/target compatibility facts to `code-repo-adaptation`;
3. after adaptation, resume with `patch-verification`.

Do not hide a repository migration inside a “minimal fix.”

## Unified verification request

```yaml
verification_request:
  source_skill:
  changed_paths: []
  target_behavior:
  reproduction_steps: []
  expected_invariants: []
  expected_outputs: []
  known_risks: []
  unresolved_items: []
```

Reject or mark blocked any verdict whose required paths, reproduction steps, expected
invariants, or environment prerequisites are unavailable.

## Output contract

In a chat answer, lead with the root cause (or the best-supported hypothesis, labeled
as such) and the fix, then the evidence that confirms it, per
[output voice](../../_shared/output-voice.md) and the
[output examples](references/output-examples.md). `HYP-*`, `EV-*`, and `TST-*` IDs
belong in saved reports, not in a short reply. Use the following as section sources
for the requested scope. Narrow explanations
may use concise prose with evidence and uncertainty; patch verification includes the
tests, invariant results, and verdict. Omit unrelated or nonexistent sections.

1. Failure or Verification Scope
2. Inputs and Environment Checked
3. Minimal Reproduction
4. Observed Evidence
5. Root Cause and Confidence
6. Minimal Fix — only when authorized
7. Tests Executed and Results
8. Invariant/Expected-Output Matrix
9. Verdict: `verified`, `failed`, or `blocked`
10. Residual Risks and Prevention
11. Compatibility Handoff — only when migration is required

A successful command alone is not verification, and a passing patched run alone does
not prove a stated root cause. Verification covers target behavior, invariants,
expected outputs, and relevant regression. An original failure baseline and causal
evidence are required for defect-fix/root-cause claims, not for a new candidate with
no original defect. `reproduction_steps` may describe how to exercise that candidate.

Stop when the requested diagnosis, reproduction, or verification is complete.
Missing authorization or required evidence blocks only the dependent action.
Compatibility causes move to `$code-repo-adaptation`; when migration and validation
are already authorized, continue those stages and verify the returned patch.
