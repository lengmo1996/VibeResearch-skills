# Debugging and Verification Report

Use only sections needed for the requested mode. A new candidate can replace
Minimal reproduction with Target execution and omit defect hypotheses/root cause;
record its target assertions, observed results, and relevant regression. Failure
baselines and causal evidence remain required for defect-fix/root-cause claims.

## Scope and inputs

## Minimal reproduction

- Command/input:
- Observed symptom:
- Determinism:
- Environment facts:

## Evidence and hypotheses

| Hypothesis ID | Hypothesis | Predicted observation | Discriminating check | Evidence IDs | Status |
|---|---|---|---|---|---|
| HYP-001 | | | | EV- | open / supported / rejected / unconfirmed |

### Evidence ledger

| Evidence ID | Command/input | Observed output | Environment | Supports/rejects |
|---|---|---|---|---|

## Root cause

- Finding:
- Confidence:
- Counterfactual or discriminating evidence:
- Competing cause excluded:

## Minimal fix

- Authorized:
- Changed paths:

## Tests executed

| Test ID | Phase | Test/step | Expected | Observed | Result |
|---|---|---|---|---|---|
| TST-001 | candidate conformance / failure baseline / after fix / regression | | | | |

## Invariant and output matrix

| Invariant/output | Evidence | Result |
|---|---|---|

## Verdict

`verified | failed | blocked`

- Blocker class when blocked: reproduction / environment / assertion / authorization

## Residual risks and prevention

## Compatibility handoff

Only when the proven cause requires `code-repo-adaptation`.
