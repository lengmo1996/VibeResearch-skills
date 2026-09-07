# Manuscript Audit Quality Checklist

## Positive routing cases

- “检查表 3 的数值、排名和正文结论是否一致。” → `table-data`
- “逐条核验 related work 的引用是否支持对应 claim。” →
  `citation-evidence`
- “做一次投稿前 mock review，重点看实验公平性和复现性。” → `reviewer`
- “全面审计论文，但不要直接改写。” → `full` with a planned subset
- “反向梳理 introduction 每段功能，检查 claim-evidence 依赖。” →
  `structure`
- “让三个评审视角先独立给意见，再综合共识、冲突和少数意见。” →
  `panel-review`

## Negative routing cases

- “把这段改得更自然。” → `$writing-academic`
- “根据贡献点规划 introduction 的故事线。” → `$writing-academic`
- “分析这些实验日志说明了什么。” → `$research-result-analysis`
- “检查页数、匿名和附件格式。” → `$publish-preflight`
- “整理收到的 reviewer comments。” → `$writing-review-triage`

## Required behavior

- [ ] Declares reviewed, missing, and unreadable material.
- [ ] Selects the smallest justified set of modes.
- [ ] Structure mode maps paragraph functions and dependencies before findings.
- [ ] Does not retrieve for language or supplied table-data checks.
- [ ] Gives every finding a stable ID and exact location.
- [ ] Separates verified defects, suggestions, and unresolved questions.
- [ ] Calibrates severity by manuscript impact rather than editing effort.
- [ ] Merges only findings with the same actionable root cause.
- [ ] Uses required retrieval for citation-support verdicts.
- [ ] Does not infer venue rules, reviewer opinions, or inaccessible evidence.
- [ ] Preserves claims, data, formulas, citations, and uncertainty.
- [ ] Does not present suggested corrections as already applied.
- [ ] Allows a bounded no-finding result without certifying the whole manuscript.
- [ ] Runs the final coverage and contradiction pass.
- [ ] Hands accepted findings to the correct downstream Skill.
- [ ] Closure mode preserves the original `AUD-*` record, distinguishes claimed from
      observed changes, and requires verification evidence before `closed`.
- [ ] Failed or regressive fixes reopen the finding or create a linked regression.
- [ ] Panel review freezes one shared snapshot, collects at least two reviewer
      records before synthesis, and declares `independent` only for isolated
      contexts.
- [ ] Panel synthesis retains evidence-backed single-reviewer and conflicting
      opinions instead of majority-vote deletion.

## Automated check

Run:

```text
<python-command> <skill-root>/scripts/validate_audit_report.py --self-test
<python-command> <skill-root>/scripts/validate_audit_report.py <saved-report.md> --closure-ledger <ledger.md>
<python-command> <skill-root>/scripts/validate_audit_report.py --panel-report <review-panel-report.md>
```
