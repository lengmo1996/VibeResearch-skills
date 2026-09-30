# Dataset Metric Protocols Quality Checklist

## Positive routing cases

- “按患者分组设计无泄漏 train/val/test。” → `split`
- “标准化统计应在哪个 partition 上拟合？” → `preprocessing`
- “精确定义 macro-F1、mAP 和聚合方向。” → `metric`
- “设计配对检验、置信区间和多重比较处理。” → `statistics`
- “检查近重复样本和 test-set tuning 泄漏。” → `leakage`
- “这些论文结果是否可直接放进同一张表？” → `comparability`

## Negative routing cases

- “设计完整实验和消融矩阵。” → `$research-experiment-design`
- “解释这些已完成实验为何变差。” → `$research-result-analysis`
- “实现 metric 代码。” → appropriate code Skill

## Required behavior

- [ ] Requires only task definition and dataset/evaluation setting.
- [ ] Selects one registered mode without assuming other modes.
- [ ] Defines stable dataset, split, and protocol identity or marks it unknown.
- [ ] Separates prediction, evaluation, grouping, and uncertainty units.
- [ ] Freezes split membership and preprocessing learned state.
- [ ] Defines every metric beyond its display name.
- [ ] Audits entity, duplicate, temporal, site, label, transform, tuning, and test reuse leakage.
- [ ] Matches statistical choices to sampling and pairing assumptions.
- [ ] Gives every comparison a three-state verdict and allowed claim.
- [ ] Uses optional RAG only for authoritative protocol verification.
- [ ] Does not interpret results or invent dataset/metric/source details.

## Automated check

```text
<python-command> <skill-root>/scripts/validate_evaluation_protocol.py --self-test
<python-command> <skill-root>/scripts/validate_evaluation_protocol.py <saved-protocol.md>
```
- [ ] Every metric has a stable `MET-*` ID and explicit validity conditions.
- [ ] No protocol mismatch is hidden by a shared metric name.
- [ ] A chat answer leads with the comparability verdict or the leakage risk that matters most; record fields stay in the saved protocol.
