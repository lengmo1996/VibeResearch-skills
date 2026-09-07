# Submission Preflight Protocol

## Stable identities

- `RULE-*`: one current authoritative requirement with official source, cycle/track/
  phase, retrieval date, applicability, and hard/soft class.
- `ART-*`: one exact candidate artifact with role, version/hash, destination, and
  inspected/not-provided status.
- `CHK-*`: one automated or manual check with expected and observed result.
- `FIND-*`: one actionable discrepancy linked to rules, artifacts, checks, and recheck.

## Rule hierarchy

Prefer the most specific current official source: portal/track/cycle instructions,
then official author kit/template readme, then general venue policy. Preserve
conflicts. Prior-year pages are historical and cannot clear a current hard rule.

## Severity

- `Blocker`: likely prevents valid submission or violates a hard rule, including
  anonymity leaks, page/template/package failure, or missing required artifact.
- `Major`: material cross-artifact inconsistency or compliance risk likely to require
  substantial rework.
- `Minor`: bounded issue unlikely to invalidate submission by itself.
- `Polish`: optional clarity or presentation improvement.

Severity is based on the cited rule and consequence, not generic fear.

## Finding contract

Every finding records:

| Field | Requirement |
|---|---|
| IDs | FIND, RULE, ART, and CHK IDs |
| Location | file:line, PDF page/object, archive member, or portal field |
| Observation | exact inspected evidence |
| Consequence | rule-specific risk |
| Action | smallest repair or confirmation |
| Owner | agent/user/portal/manual |
| Recheck | command or observable pass condition |

## Final-candidate rule

A locally repaired artifact is not the submitted artifact until its identity is
confirmed. Before submission, compare the final local candidate with the portal
preview/download and recheck page count, anonymity, metadata, references, and package
contents.

## Machine-readable manifest

The companion manifest does not replace official rule evidence or the human report.
It makes the current rule, artifact, check, finding, and verdict mappings
deterministic. Paths are relative to an explicitly supplied package root. A manifest
may validly describe `Blocked` or `Not ready`; structural validity is not readiness.

`Ready` additionally requires all applicable hard rules and required artifacts to
pass, every hard rule to have a passed check, no Blocker/Major finding, no unresolved
material, and confirmed final local-versus-portal candidate identity.

`Ready` and `Conditionally ready` both require non-empty rule, artifact, and check
ledgers plus resolved venue/channel, cycle, track, phase, and portal. Use an explicit
`not applicable` for scope fields that the channel genuinely does not have; missing
or unchecked fields cannot establish readiness. Every applicable hard rule must
pass with source-backed checks, and all required artifacts must be inspected. A
passed check cannot cancel a current failed or incomplete check for the same hard
rule. Resolve the discrepancy and update its evidence before issuing a positive
verdict.

`Conditionally ready` cannot carry a Blocker or defer hard-rule/material inspection.
It may defer a bounded non-hard confirmation or the final portal identity comparison;
state the exact remaining condition in the verdict rationale. `Ready` still requires
that identity confirmation and excludes Major findings. Empty or unresolved drafts
remain representable as `Blocked` or `Not ready`, never as a vacuous `Ready`.
