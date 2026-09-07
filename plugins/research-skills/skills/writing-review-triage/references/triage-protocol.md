# Review Triage Protocol

Load this reference after normalizing received comments.

## Contents

- [Preserve the source](#1-preserve-the-source)
- [Classify the concern](#2-classify-the-concern)
- [Cluster root issues](#3-cluster-root-issues)
- [Score decision axes](#4-score-separate-decision-axes)
- [Select response posture](#5-select-response-posture)
- [Build the plan](#6-build-a-dependency-aware-plan)
- [Resolve conflicts and hand off](#7-resolve-conflicts-and-hand-off)

## 1. Preserve the source

Assign atomic IDs such as `R1-C01`, `META-C02`, or `EDITOR-C01`. Store the source
label, a short exact excerpt, and the full concern scope. Split compound comments only
when the parts can receive different actions. Never convert a reviewer question into
a factual accusation or infer hidden intent.

Coverage status is one of:

- `actionable`: requires a response, revision, evidence, or experiment;
- `informational`: positive feedback or context with no action;
- `duplicate`: fully represented by another atomic record;
- `unclear`: cannot be safely interpreted from supplied material.

## 2. Classify the concern

Choose one primary type and optional secondary types:

- `central-claim`: novelty, validity, soundness, or contribution risk;
- `missing-experiment`: ablation, baseline, robustness, generalization, or statistics;
- `fairness-protocol`: tuning, compute, split, metric, implementation, or comparison;
- `clarification`: motivation, assumption, method, detail, limitation, or scope;
- `misunderstanding`: demonstrable mismatch between the review and supplied paper;
- `writing-presentation`: structure, language, notation, figure, or table clarity;
- `citation-positioning`: missing citation or unclear prior-work relationship;
- `scope-request`: request beyond the stated contribution or evaluation scope;
- `ethics-compliance`: ethics, data rights, disclosure, or responsible-use concern.

Do not use `misunderstanding` without a manuscript passage or supplied evidence that
shows the mismatch.

## 3. Cluster root issues

Create stable cluster IDs such as `CL-01`. Cluster comments when one underlying
revision or evidence package can answer them together. Keep separate records when:

- reviewers make incompatible requests;
- the same topic has different evidence needs;
- one comment challenges validity and another only presentation;
- one action can complete while another remains blocked.

Record all member IDs and any decision-authority source such as meta-review or editor
guidance. Authority affects urgency, not factual correctness.

## 4. Score separate decision axes

- Severity: `critical`, `high`, `medium`, or `low` manuscript/decision impact.
- Urgency: `now`, `before-draft`, `before-revision`, or `later`.
- Confidence: `high`, `medium`, `low`, or `unclear`.
- Evidence readiness: `ready`, `partial`, `missing`, or `not-applicable`.
- Effort: `small`, `medium`, `large`, or `unclear`.
- Dependency: IDs that must complete first.

Do not collapse these into one opaque score. A low-effort clarification can be urgent;
a critical experiment can remain blocked; repeated comments can raise priority
without increasing evidentiary certainty.

## 5. Select response posture

Use one posture:

- `acknowledge-and-correct`;
- `clarify-with-existing-evidence`;
- `add-evidence-or-experiment`;
- `soften-or-bound-claim`;
- `explain-scope-with-evidence`;
- `request-clarification`;
- `no-response-action`.

Disagree only when supplied evidence supports the distinction. State the evidence and
avoid predicting how the reviewer will react. Low-cost actions are fast opportunities,
not guaranteed score gains.

## 6. Build a dependency-aware plan

Order work by:

1. meta-review/editor requirements and central-claim blockers;
2. shared clusters affecting multiple comments;
3. evidence or experiment prerequisites;
4. response drafting after claims and evidence are stable;
5. independent presentation fixes.

For every actionable item, specify the next action, destination, required inputs,
completion evidence, and verification criterion.

## 7. Resolve conflicts and hand off

Keep contradictory reviewer requests visible in an unresolved-conflicts section.
Prefer a solution that preserves the paper's verified contribution and satisfies the
decision authority; otherwise present alternatives and the missing decision.

Handoff readiness:

- `$writing-academic`: posture, verified facts, protected claims, evidence, and length;
- `$research-experiment-design`: hypothesis, requested comparison, constraints, and
  affected IDs;
- `$research-result-analysis`: completed result artifacts and target claim;
- `$writing-manuscript-audit`: manuscript location and concern requiring independent
  diagnosis.
