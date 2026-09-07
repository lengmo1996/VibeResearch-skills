# Result Analysis Quality Checklist

## Positive routing cases

- “总结这些表格和曲线中的稳定模式。” → `summary`
- “结果是否支持我们的核心 claim？” → `claim-check`
- “为什么这些 run 失败，下一步怎么区分原因？” → `failure-analysis`
- “分析组件消融和交互作用。” → `ablation-analysis`
- “检查这些结果的统计假设、多重比较和 best-seed 选择风险。” →
  `statistical-audit`
- “核对冻结配置、seed 覆盖和重复运行是否支持可复现性。” →
  `reproducibility-check`
- “预算有限，下一项最有信息量的实验是什么？” → `next-step`

## Required behavior

- [ ] Uses supplied experimental artifacts as the only required input.
- [ ] Uses RAG `never`.
- [ ] Gates comparisons on protocol compatibility.
- [ ] Separates observations, explanations, attribution, and recommendations.
- [ ] Uses five-state claim support.
- [ ] Preserves null/adverse/failed/missing runs.
- [ ] Accounts for ablation interactions and compute/capacity confounds.
- [ ] Does not invent variance, significance, effect size, or causal mechanism.
- [ ] Hands off verified wording separately from unresolved explanations.
- [ ] Preserves upstream `CLM/EXP/RUN/protocol/MET` identities.
- [ ] Emits a shared-schema claim-evidence patch with the five-state verdict retained
      in the evidence note.
- [ ] Statistical and reproducibility checks never convert missing assumptions,
      variance, denominators, seeds, or runs into a pass.

## Automated check

```text
<python-command> <skill-root>/scripts/validate_result_analysis.py --self-test
<python-command> <skill-root>/scripts/validate_result_analysis.py <saved-report.md> --claim-patch <patch.json>
```
