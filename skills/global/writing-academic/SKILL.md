---
name: writing-academic
description: "Use when outlining, drafting, or revising academic manuscript prose or reviewer responses. Return a scoped plan, revised text, or requested revision patch while preserving scientific content. Diagnosis-only audits belong to writing-manuscript-audit."
---

# Academic Writing

## Purpose

Create or revise academic manuscript prose without changing scientific content. Use
`literature-synthesis` when finding or comparing literature is primary,
`writing-manuscript-audit` when the requested deliverable is a reverse outline,
defect list, or verdict,
and `research-result-analysis` when interpreting raw results is primary.

## Required and optional inputs

Required: writing goal, output language, and either target text or verified content
points.
Optional: venue/style, length, audience, manuscript context, terminology/symbol
table, citations, evidence map, reviewer comments, constraints, and an author-owned
voice sample or approved task-scoped voice profile. A `de-template` handoff may also
include accepted `AUD-*` findings, protected content, and verification methods.
`revision-patch` additionally requires a contained target manuscript, stable block
markers, exact pre-edit and reviewed replacement hashes, replacement artifacts, and explicit authorization
before application.

## Workflow

1. Bind the source material, requested operation, output language, and immutable
   items: claims, numbers, formulas, metric direction, citation keys, quotations,
   URLs, code, and user-designated text.
2. Select the smallest sufficient operation. Do not run a full rewrite for a grammar,
   translation, or local-clarity request.
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
4. Build or reuse terminology and symbol decisions. Identify claim-to-evidence gaps
   before drafting and mark unsupported claims `[citation needed]`.
5. Write at the requested structural level and claim strength. For related work,
   require a `literature-synthesis` evidence map and bind each comparative claim.
6. For `de-template`, read
   [naturalness rewrite](references/naturalness-rewrite.md), bind accepted `AUD-*`
   findings when supplied, and run its one-pass rewrite and residual check. For
   `author-voice`, instead read
   [author voice calibration](references/author-voice-calibration.md) and use only
   the user-owned task-local sample or approved profile. Do not load both references
   unless both outputs are explicitly requested; do not use either for authorship
   detection or detector optimization.
7. For `compress`, bind a measurable target when one is supplied, remove redundancy
   before evidence, and verify the before/after length plus protected scientific
   content. Use [compression-report.md](templates/compression-report.md) when the
   user requests an audit trail or the source is high risk.
8. Verify that meaning, data, formulas, references, uncertainty, protected spans, and
   source attribution are preserved. For high-risk text or an auditable handoff, use
   [protected-spans.json](templates/protected-spans.json) and run
   `<python-command> <skill-root>/scripts/verify_protected_spans.py --source <before> --revised <after>
   --manifest <protected-spans.json>`.
9. For `revision-patch`, read
   [revision patch protocol](references/revision-patch-protocol.md), create
   [revision-patch.json](templates/revision-patch.json), and run
   `<python-command> <skill-root>/scripts/apply_revision_patch.py --root <workspace-root> --manifest
   <revision-patch.json>`. This default validates and previews only. Add `--apply`
   solely when the user authorized that exact target; any target, block, path, or
   hash mismatch must stop without writing.
10. For `outline`, return the story map and paragraph plan. For prose operations,
   return revised text first. Follow with only useful decisions and unresolved
   evidence.

## Modes

- `outline`, `draft`, `rewrite`, `de-template`, `author-voice`, `compress`,
  `expand`, `clarify`, `venue-style`, `reviewer-response`, `revision-patch`.
- Section targets may include `abstract`, `introduction`, `method`, `experiments`, `discussion`, `limitations`, `conclusion`, and `related-work`.

## RAG policy

Ordinary draft/rewrite is `optional`; related work is `required`; terminology consistency is `recommended`; reviewer response is `optional`; pure translation, grammar, formatting, or user-restricted-source editing is `never`.

## Evidence policy

Never modify data, formulas, metric direction, citation keys, or supplied factual
claims. Do not invent experiments, references, names, dates, numbers, or quotations.
Candidate citations remain candidates until verified. Do not copy or closely imitate
long source passages or imitate a named author's distinctive style.

## Output contract

For a whole-paper `outline`, output the paper story, section dependency order, stable
claim IDs, evidence gaps, and locked/open decisions; emit only a task-local
paper-context patch unless persistence is separately authorized. For a section
`outline`, output the story map and paragraph plan. For prose operations, output the
revised text first. Add only useful sections: Change rationale; Terminology decisions;
Claims requiring evidence; Candidate evidence; Unresolved questions. For related work,
include or reference the evidence map. For `compress`, report target attainment and
preservation failures when a compression report is required. For a naturalness rewrite, use
[rewrite-invariant-report.md](templates/rewrite-invariant-report.md) only when an
audit trail is useful; otherwise keep the checks internal.
For `de-template`, preserve incoming `AUD-*` IDs and state which accepted findings
were resolved, unchanged, or blocked. For `author-voice`, state the sample/profile
scope and confidence without persisting it. A protected-span validator pass proves
literal preservation only; it never certifies semantic equivalence.
For `revision-patch`, return the manifest, target/source hash, per-block validation,
protected-span result, preview or apply status, output hash, and unresolved conflicts.
Validation success is not write authorization. An applied patch must preserve all
bytes outside declared block interiors and use atomic replacement.

## Failure behavior

If evidence required for a claim is unavailable, keep a neutral supported claim or
mark `[citation needed]`; never fill the gap from memory. If the input is too
incomplete for a requested draft, provide a scaffold and list missing verified facts.
If a voice sample is too short or inconsistent, state that voice matching is
low-confidence and use the requested academic register. If no material naturalness
problem is present, preserve the text and report that no rewrite is needed.
If a protected-span check fails, do not present the revision as final: restore the
span or return the candidate with the failed IDs. Perform at most one corrective
rewrite pass; do not loop against an AI detector or style score.
If a revision target, marker, replacement, or hash differs from the manifest, stop
with a conflict report. Do not rebase, fuzzy-match, overwrite, or silently regenerate
hashes. Rebuild the manifest from the newly reviewed target instead.

## Composition rules

May follow `literature-synthesis` or precede `writing-manuscript-audit`. Use no more than two supporting Skills. Reviewer response mode does not replace comment prioritization by `writing-review-triage`.

## Examples

- “把这个 introduction 改成更清晰的学术英语，不改变引用和数据。”
- “根据这些已接受的 AUD findings 去掉模板化表达，返回修改后的段落。”
- “参考我提供的本人论文样本改写这段，保持术语和引用不变。”
- “根据这些已验证的贡献点，规划 introduction 的故事线和段落功能。”
- “根据已有 evidence map 写 related work。”
- “把已接受的 AUD-001 修订做成带原文 hash 的可审查 patch，先校验不要应用。”

## Non-examples

- “核验这些引用是否支持 claim。” → `writing-manuscript-audit`.
- “反向梳理这篇论文的段落功能并找出结构缺陷。” → `writing-manuscript-audit`.
- “判断这段有多大概率由 AI 生成。” → unsupported authorship
  classification, not this Skill.
- “改写到可以绕过 AI detector。” → refuse detector-evasion optimization.
- “解释这些实验为何提升。” → `research-result-analysis`.

## Validation checklist

- [ ] Meaning, data, formulas, citations, and uncertainty are preserved.
- [ ] Mode and audience are explicit.
- [ ] Structural references were loaded only for the matching section and operation.
- [ ] Whole-paper work loaded the lifecycle reference without preloading every section guide.
- [ ] A paper-context patch contains only thin state and artifact references and is not persisted implicitly.
- [ ] An outline has one story function per paragraph and explicit claim-evidence gaps.
- [ ] Unsupported claims are marked or weakened.
- [ ] Related work has an evidence map and required RAG.
- [ ] Terminology and symbols are consistent.
- [ ] No long-source imitation or fabricated content appears.
- [ ] Naturalness work preserved protected spans and passed a residual-pattern check.
- [ ] De-template work consumed accepted findings without rerunning a full audit.
- [ ] Author-voice work used only an author-owned task-local sample or approved
      profile and did not persist it.
- [ ] High-risk rewrites passed literal protected-span validation or exposed the
      failed span IDs.
- [ ] A low-signal naturalness request was allowed to return `no change needed`.
- [ ] Compression measured the requested target and preserved protected scientific content.
- [ ] Revision patches use contained paths, unique block IDs, exact target/block
      hashes, atomic apply, and fail closed on drift.
- [ ] Patch validation and patch application are reported separately; validation
      never implies write authorization.

## Shared contracts and stop conditions

Follow the canonical [RAG](../../_shared/rag-retrieval/CAPABILITY.md),
[evidence](../../_shared/evidence-policy.md), [failure](../../_shared/failure-policy.md),
[outputs](../../_shared/academic-output-contracts.md),
[style](../../_shared/academic-style-policy.md),
[terminology](../../_shared/terminology-policy.md),
[citations](../../_shared/citation-format.md),
[paper context](../../_shared/contracts/paper-context.schema.json),
[claim evidence](../../_shared/contracts/claim-evidence.schema.json),
[platform compatibility](../../_shared/platform-compatibility.md), and
[file safety](../../_shared/file-mutation-safety.md) contracts. Stop when the requested
text and checks are complete, required evidence is unavailable, or continuing would
change unsupported scientific content or exceed the authorized artifact scope.
