---
name: paper-deep-read
description: "Explain one paper, or one method section, equation set, algorithm, figure, or table from it (精读、讲解方法、公式、图表、实验). Returns a source-faithful analysis tied to page or section locations."
---

# Paper Deep Read

The single Skill for understanding one paper. It takes one complete or partial paper
artifact and explains only what that material supports. It is read-only and never
modifies code.

## Input

One primary input is enough: `paper_pdf`, `paper_text`, `method_section`,
`equations`, `algorithm`, `figure_image`, or `table_image`. A question, requested
mode, project context, caption or legend, page references, or an existing evidence
ledger help when present. Partial input is valid; narrow the scope and confidence of
the answer to match it.

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
- `full`: all applicable modes for a sufficiently complete paper. A partial artifact
  gets the modes it supports, and the answer says it is partial.

Legacy `deep` requests select the narrowest applicable mode or `full`. Legacy
`reproducibility` requests return source-bounded implementation requirements and open
questions, then hand implementation to `$paper-reproduction`.

## How to read

Identify what was actually supplied, which parts are readable, and what context is
missing. Read the relevant part of the
[mode analysis protocol](references/mode-analysis-protocol.md) and analyze only the
selected mode.

Quote claims, equations, labels, values, and captions as they appear, with their page
or section, rather than silently normalizing them. Keep three things apart: what the
paper states, interpretation the material supports, and inference it does not
confirm. When an image is blurry, cropped, or missing its caption or legend, lower the
confidence and say which region you could not read; a figure or table without its
context cannot support a paper-wide conclusion. Unreadable labels, equations, cells,
and connections stay unread rather than reconstructed.

## Evidence ledger

A narrow question cites its sources inline and needs no ledger. Build a structured
ledger with stable `CLM-*` IDs only for a `full` report or an actual handoff, and
reuse it if the user asks for another mode. Each material claim records:

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

If two modes seem inconsistent, record the conflict against their existing claim IDs
instead of replacing the earlier reading.

## Output

Follow [output voice](../_shared/output-voice.md); see
[output examples](references/output-examples.md). For a narrow question, answer it
directly with source locations and whatever uncertainty affects the answer; open
questions and handoffs appear only when they exist. The evidence classes above are
bookkeeping: in prose, say "论文写明……" or "这是我的推断，因为……" in the user's
language instead of printing class names. A `full` report covers scope and input
quality, the mode analyses, the evidence ledger, limitations, and real open
questions, drawing sections from
[paper-deep-read_report.md](templates/paper-deep-read_report.md) and covering only
what the material contains.

## Boundaries and handoff

Implementing the core method is `$paper-reproduction`; migrating a repository is
`$code-repo-adaptation`; minimal reproduction, tests, and patch verification are
`$code-debugging`; comparing several papers is `$literature-synthesis`. A supporting
`domain-*` Skill may add terminology or known constraints but cannot replace source
evidence or become primary.

Load only files linked by this `SKILL.md` for the current workflow.

A handoff to `$paper-reproduction` carries only the evidence ledger,
method/equation/architecture findings, tensor or interface facts, and unresolved
paper-to-code questions.

Stop when the selected mode is complete, the remaining material is unreadable or too
partial for the requested conclusion, or going further would require inventing
context. Shared rules: [evidence](../_shared/evidence-policy.md),
[failure](../_shared/failure-policy.md),
[operational boundaries](../_shared/operational-boundaries.md),
[output contracts](../_shared/academic-output-contracts.md).
