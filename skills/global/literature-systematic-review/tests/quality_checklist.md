# Systematic Review Quality Checklist

## Positive routing cases

- “按 PRISMA 做系统综述并记录全文排除理由。” → `full`
- “先起草 systematic review protocol，不要声称已经检索。” → `protocol`
- “检查这些 effect definitions 能否进行 meta-analysis。” → `meta-analysis`
- “对纳入研究做 risk-of-bias 和证据确定性评估。” →
  `risk-of-bias` / `certainty`

## Negative routing cases

- “比较这五篇论文。” → `$literature-synthesis`
- “写 related work。” → `$writing-academic`
- “每周找新论文。” → `$literature-monitor`

## Required behavior

- [ ] Freezes protocol and records amendments.
- [ ] Accounts for every declared source and search batch.
- [ ] Preserves unresolved deduplication and screening conflicts.
- [ ] Requires full-text exclusion reasons.
- [ ] Reconciles flow counts against study decisions.
- [ ] An included title/abstract awaiting full text prevents complete coverage.
- [ ] Never claims independent screening without isolated decisions.
- [ ] Keeps bias and certainty judgments evidence-bound.
- [ ] Gates meta-analysis on conceptual and numeric compatibility.
- [ ] Quantitative counts bind unique included study IDs with available effect data;
      incompatible qualitative-only studies do not invalidate a compatible subset.
- [ ] Uses protocol-only, partial, or complete without universalizing coverage.

## Automated check

```text
<python-command> <skill-root>/scripts/validate_systematic_review.py --self-test
<python-command> <skill-root>/scripts/validate_systematic_review.py <systematic-review-ledger.json>
```
