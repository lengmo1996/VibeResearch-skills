---
name: paper-deep-read
description: "Use when understanding one paper, method section, equation set, algorithm, figure, or table from supplied paper material. Produces a source-faithful analysis and shared evidence ledger. Do not use for implementation, repository migration, or multi-paper synthesis."
---

# Paper Deep Read

## Purpose

`paper-deep-read` is the single multi-mode Skill for understanding one paper. It
accepts one complete or partial paper artifact, explains only what the available
evidence supports, and never modifies code.

Read the shared [evidence](../_shared/evidence-policy.md),
[failure](../_shared/failure-policy.md), [operational
boundaries](../_shared/operational-boundaries.md), and [output
contracts](../_shared/academic-output-contracts.md).

## Input contract

Exactly one primary input is sufficient:

```yaml
one_of:
  - paper_pdf
  - paper_text
  - method_section
  - equations
  - algorithm
  - figure_image
  - table_image
```

Optional inputs are a question, requested mode, project context, caption or legend,
page references, and an existing evidence ledger. Partial input is valid, but the
output scope and confidence must be reduced accordingly.

## Modes

- `overview`: background, motivation, problem, contributions, method overview,
  experiments, and limitations.
- `method`: technical logic, module roles, interfaces, and data flow.
- `equations`: symbols, dimensions, derivation boundary, numerical meaning, and
  stability assumptions.
- `figure`: modules, arrows, data flow, encoding conventions, caption claims, and
  unreadable or cropped regions.
- `table`: metrics, direction, comparison relationships, key conclusions, and
  fairness or protocol caveats.
- `experiments`: datasets, splits, preprocessing, metrics, baselines, settings,
  ablations, variance, and claim support.
- `limitations`: stated limitations, evidence-backed inferred limitations, failure
  modes, and external-validity risks.
- `full`: all applicable modes for a sufficiently complete paper. Never imply a full
  read from a partial artifact.

Legacy requests for `deep` select the narrowest applicable mode or `full`.
Legacy `reproducibility` requests return source-bounded implementation requirements
and open questions, then hand off method implementation to `paper-reproduction`.

## Workflow

1. Identify the exact supplied artifact, selected mode, readable regions, and missing
   context.
2. Read [mode analysis protocol](references/mode-analysis-protocol.md). Create or
   reuse one evidence ledger for the entire task; assign stable `CLM-*` IDs.
3. Extract claims, equations, labels, values, captions, and page/section anchors
   without silently normalizing them.
4. Separate `paper states`, `supported interpretation`, and `unconfirmed inference`.
5. Analyze only the selected mode; reuse the same ledger if another mode is requested.
6. Degrade conclusions when an image is blurry, cropped, missing a legend/caption, or
   does not expose the referenced context.
7. Return the analysis, uncertainties, open questions, and optional downstream handoff.

## Evidence ledger

Each material claim records:

```yaml
evidence:
  claim_id:
  source_artifact:
  location:
  observed_content:
  evidence_class: paper_states | supported_interpretation | unconfirmed_inference
  confidence: high | medium | low
  limitations:
```

Do not invent unreadable labels, equations, cells, page numbers, citations, metrics,
or architecture connections. A figure or table with missing context cannot support a
paper-wide conclusion. If two modes appear inconsistent, record the conflict against
their existing claim IDs instead of silently replacing the earlier interpretation.

## Output contract

Every mode includes Scope and Input Quality, Mode Analysis, Evidence Ledger,
Limitations and Uncertainty, and Open Questions. `full` additionally includes paper
identity, problem, contributions, method flow, equations, experiments, results, and
limitations when present in the supplied material.

## Boundaries and handoff

- `paper-deep-read` is read-only and never modifies code.
- Core-method implementation belongs to `paper-reproduction`.
- Repository compatibility migration belongs to `code-repo-adaptation`.
- Minimal reproduction, tests, and patch verification belong to `code-debugging`.
- Multiple-paper synthesis belongs to `literature-synthesis`.
- A supporting Domain Skill may add terminology or known constraints, but it may not
  replace source evidence or become primary.

Load only files linked by this `SKILL.md` for the current workflow.

When handing off to `paper-reproduction`, pass only the shared evidence ledger,
method/equation/architecture findings, tensor or interface facts, and unresolved
paper-to-code questions.

## Stop conditions

Stop when the selected mode is complete, the remaining artifact is unreadable, the
source is too partial for the requested conclusion, or proceeding would require
fabricating context. Mark missing material `not provided / unclear`.
