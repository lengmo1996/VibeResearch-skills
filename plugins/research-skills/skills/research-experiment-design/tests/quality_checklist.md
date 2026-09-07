# Experiment Design Quality Checklist

## Positive routing cases

- “设计验证这个假设的完整实验。” → `full`
- “baseline 怎样比较才公平？” → `baseline`
- “哪些正负控制能排除数据规模影响？” → `control`
- “设计组件和交互消融。” → `ablation`
- “按两周和四张 GPU 排实验顺序。” → `schedule`

## Negative routing cases

- “定义无泄漏 split 和统计检验。” → `$research-dataset-metric-protocols`
- “解释已经跑完的指标和曲线。” → `$research-result-analysis`
- “复现这篇论文的官方结果。” → `$paper-reproduction`
- “实现训练代码并运行实验。” → appropriate code Skill

## Required behavior

- [ ] Requires only hypothesis/question and target system/method.
- [ ] Selects one registered mode without silently expanding scope.
- [ ] Maps each hypothesis to a discriminating experiment.
- [ ] Registers variables, controls, interactions, invariants, and confounds.
- [ ] Documents baseline fairness and exceptions.
- [ ] Uses optional RAG only for comparability evidence.
- [ ] Defines supportive, null, adverse, and inconclusive branches.
- [ ] Separates pilot, must-run, conditional, and optional runs.
- [ ] Gives every experiment a resource estimate, dependency, artifact, and decision rule.
- [ ] Does not invent results, effect sizes, significance, runtime, or success probability.
- [ ] Produces a bounded scaffold when critical optional protocol fields are unknown.
- [ ] Hands detailed split/metric/statistical work to the protocol Skill.

## Automated check

```text
<python-command> <skill-root>/scripts/validate_experiment_plan.py --self-test
<python-command> <skill-root>/scripts/validate_experiment_plan.py <saved-plan.md>
```
