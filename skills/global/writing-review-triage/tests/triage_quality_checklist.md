# Review Triage Quality Checklist

## Positive routing cases

- “把这些 OpenReview comments 按根因聚类并排回复顺序。” →
  `response-plan`
- “期刊大修意见中哪些必须修改，依赖什么材料？” → `revision-plan`
- “先分诊这些 reviewer comments，不要写 rebuttal。” → `triage`

## Negative routing cases

- “模拟 NeurIPS reviewer 审查这篇草稿。” → `$writing-manuscript-audit`
- “把已有回复策略写成正式 rebuttal。” → `$writing-academic`
- “设计 reviewer 要求的消融实验。” → `$research-experiment-design`
- “新增实验是否支持我们的 claim？” → `$research-result-analysis`

## Required behavior

- [ ] Uses only reviewer comments as a required input.
- [ ] Selects `triage`, `response-plan`, or `revision-plan`.
- [ ] Does not call RAG or external evidence retrieval.
- [ ] Gives every atomic comment a source-preserving stable ID.
- [ ] Maps every source comment to exactly one coverage status.
- [ ] Clusters shared root issues without hiding contradictory requests.
- [ ] Keeps decision authority separate from factual correctness.
- [ ] Separates severity, urgency, confidence, evidence readiness, effort, and
      dependency.
- [ ] Labels `misunderstanding` only from supplied evidence.
- [ ] Does not treat low effort as guaranteed score improvement.
- [ ] Gives every actionable item a destination and verification criterion.
- [ ] Does not draft final prose, execute experiments, invent results, or predict
      acceptance.
- [ ] Produces a minimal downstream handoff with ready and blocked items separated.
