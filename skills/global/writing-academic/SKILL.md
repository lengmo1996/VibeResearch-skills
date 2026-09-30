---
name: writing-academic
description: "Outline, draft, revise, polish, compress, translate, or de-template academic manuscript prose and reviewer responses while preserving scientific content (论文写作、润色、改写、压缩、去 AI 味、回复审稿意见). Returns revised text, a section plan, or a reviewable revision patch."
---

# Academic Writing

Creates or revises manuscript prose without changing its science. Finding or
comparing literature is `$literature-synthesis`; a reverse outline, defect list, or
verdict is `$writing-manuscript-audit`; interpreting raw results is
`$research-result-analysis`.

Needed: the writing goal, output language, and either the target text or verified
content points. Venue and style, length, audience, manuscript context, a terminology
and symbol table, citations, an evidence map, reviewer comments, constraints, and an
author-owned voice sample or approved task-scoped voice profile help when given. A
`de-template` handoff may carry accepted `AUD-*` findings, protected content, and
verification methods. `revision-patch` also needs a contained target manuscript,
stable block markers, exact pre-edit and reviewed replacement hashes, replacement
artifacts, and explicit authorization before anything is applied.

## Modes

- `outline`, `draft`, `rewrite`, `de-template`, `author-voice`, `compress`,
  `expand`, `clarify`, `venue-style`, `reviewer-response`, `revision-patch`.
- Section targets may include `abstract`, `introduction`, `method`, `experiments`,
  `discussion`, `limitations`, `conclusion`, and `related-work`.

## Workflow

1. Pin down the source material, the operation, the output language, and what must
   not change: claims, numbers, formulas, metric direction, citation keys,
   quotations, URLs, code, and text the user marks as fixed.
2. Pick the smallest operation that does the job. A grammar, translation, or
   local-clarity request does not need a full rewrite.
3. For an explicit whole-paper `outline` or structural `draft`, load
   [full-manuscript lifecycle](references/manuscript-lifecycle.md), use
   [paper-outline](templates/paper_outline.md), and create or patch the shared
   [paper-context](../../_shared/templates/paper-context.yaml) only when a
   cross-section state index is useful. For a scoped abstract, introduction, or
   method `outline` or structural `draft`, instead load exactly one matching guide:
   [abstract](references/abstract-structure.md),
   [introduction](references/introduction-structure.md), or
   [method](references/method-structure.md), then use
   [section-structure-plan.md](templates/section-structure-plan.md). Do not load the
   full-paper and section guides together, and do not load either for local rewrite,
   grammar, translation, or naturalness-only requests.
4. Build or reuse terminology and symbol decisions. Find claim-to-evidence gaps before
   drafting and mark unsupported claims `[citation needed]`.
5. Write at the requested structural level and claim strength. Related work needs a
   `$literature-synthesis` evidence map, with each comparative claim tied to it.
6. For `de-template`, read [naturalness rewrite](references/naturalness-rewrite.md),
   use accepted `AUD-*` findings when supplied, and run its one-pass rewrite and
   residual check. For `author-voice`, instead read
   [author voice calibration](references/author-voice-calibration.md) and use only the
   user-owned task-local sample or approved profile. Load both only when both outputs
   are requested. Neither is for authorship detection or detector optimization.
7. For `compress`, set a measurable target when one is given, cut redundancy before
   evidence, and check the before/after length and protected content. Use
   [compression-report.md](templates/compression-report.md) when the user wants an
   audit trail or the source is high risk.
8. Before returning any prose, reread it against the pattern tables in
   [output voice](../../_shared/output-voice.md) (English or Chinese, matching the
   text) and fix clusters in one pass. Field conventions win: established phrasing,
   necessary parallelism, and venue boilerplate stay. This is a brief check, not the
   full `de-template` workflow.
9. Verify that meaning, data, formulas, references, uncertainty, protected spans, and
   attribution are preserved. For high-risk text or an auditable handoff, use
   [protected-spans.json](templates/protected-spans.json) and run
   `<python-command> <skill-root>/scripts/verify_protected_spans.py --source <before> --revised <after>
   --manifest <protected-spans.json>`.
10. For `revision-patch`, read
   [revision patch protocol](references/revision-patch-protocol.md), create
   [revision-patch.json](templates/revision-patch.json), and run
   `<python-command> <skill-root>/scripts/apply_revision_patch.py --root <workspace-root> --manifest
   <revision-patch.json>`. The default validates and previews only. Add `--apply`
   only when the user authorized that exact target; any target, block, path, or hash
   mismatch stops without writing.

## RAG policy

Ordinary draft/rewrite is `optional`; related work is `required`; terminology
consistency is `recommended`; reviewer response is `optional`; pure translation,
grammar, formatting, or user-restricted-source editing is `never`.

## Evidence

Data, formulas, metric direction, citation keys, and supplied factual claims pass
through unchanged. Experiments, references, names, dates, numbers, and quotations
come from the user or verified sources, never from memory. Candidate citations stay
candidates until verified. Long source passages are not copied or closely imitated,
and a named author's distinctive style is not imitated.

When evidence for a claim is missing, keep a neutral supported version or mark
`[citation needed]`. When input is too thin for the requested draft, give a scaffold
and list the verified facts still needed. A short or inconsistent voice sample means
low-confidence voice matching in the requested academic register; say so. If the text
has no real naturalness problem, keep it and say no rewrite is needed.

## Output

Revised text comes first. After it, add only what the user needs: why a change was
made where it is not obvious, terminology decisions, claims that still need evidence,
candidate evidence, open questions. Follow [output voice](../../_shared/output-voice.md)
for these notes.

- Whole-paper `outline`: the paper story, section dependency order, stable claim IDs,
  evidence gaps, and locked/open decisions; emit only a task-local paper-context patch
  unless persistence is separately authorized.
- Section `outline`: the story map and paragraph plan.
- Related work: include or reference the evidence map.
- `compress`: target attainment and preservation failures when a compression report
  is required.
- Naturalness rewrite: [rewrite-invariant-report.md](templates/rewrite-invariant-report.md)
  only when an audit trail is useful; otherwise keep the checks internal.
- `de-template`: keep incoming `AUD-*` IDs and say which accepted findings were
  resolved, unchanged, or blocked.
- `author-voice`: state the sample or profile scope and confidence; do not persist it.
- `revision-patch`: the manifest, target/source hash, per-block validation,
  protected-span result, preview or apply status, output hash, and unresolved
  conflicts. Validation success is not write authorization. An applied patch
  preserves all bytes outside declared block interiors and uses atomic replacement.

A protected-span validator pass proves literal preservation only, not semantic
equivalence. If it fails, the revision is not final: restore the span or return the
candidate with the failed IDs. Allow at most one corrective pass, and never loop
against an AI detector or style score. If a revision target, marker, replacement, or
hash differs from the manifest, stop with a conflict report rather than rebasing,
fuzzy-matching, overwriting, or regenerating hashes; rebuild the manifest from the
newly reviewed target instead.

## Composition

May follow `$literature-synthesis` or precede `$writing-manuscript-audit`, with at
most two supporting Skills. Reviewer-response mode does not replace comment
prioritization by `$writing-review-triage`.

Examples: “把这个 introduction 改成更清晰的学术英语，不改变引用和数据”；“根据这些已接受的
AUD findings 去掉模板化表达”；“参考我提供的本人论文样本改写这段，保持术语和引用不变”；
“根据这些已验证的贡献点，规划 introduction 的故事线和段落功能”；“根据已有 evidence map
写 related work”；“把已接受的 AUD-001 修订做成带原文 hash 的可审查 patch，先校验不要应用”。

Not this Skill: checking whether citations support claims or reverse-outlining a
paper (`$writing-manuscript-audit`); explaining why experiments improved
(`$research-result-analysis`). Judging whether text was AI-generated is unsupported
authorship classification, and rewriting to evade an AI detector is declined.

Stop when the requested text and checks are complete, required evidence is
unavailable, or continuing would change unsupported scientific content or exceed the
authorized artifact scope. Shared rules: [RAG](../../_shared/rag-retrieval/CAPABILITY.md),
[evidence](../../_shared/evidence-policy.md), [failure](../../_shared/failure-policy.md),
[outputs](../../_shared/academic-output-contracts.md),
[style](../../_shared/academic-style-policy.md),
[terminology](../../_shared/terminology-policy.md),
[citations](../../_shared/citation-format.md),
[paper context](../../_shared/contracts/paper-context.schema.json),
[claim evidence](../../_shared/contracts/claim-evidence.schema.json),
[platform compatibility](../../_shared/platform-compatibility.md),
[file safety](../../_shared/file-mutation-safety.md).
