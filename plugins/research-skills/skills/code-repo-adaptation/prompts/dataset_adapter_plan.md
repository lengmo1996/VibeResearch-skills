# Repo Adaptation - dataset_adapter_plan Prompt

## Role
你正在执行 `code-repo-adaptation` 的 `dataset_adapter_plan` 模式。

## Goal
把开源代码以最小、可回滚、可验证的方式适配到你的环境、数据集和项目结构。

## Required Output
- 任务目标
- 输入检查
- 结构化分析
- 关键判断
- 风险与不确定性
- 下一步动作
- 可交接材料

## Constraints
- 不要大改 repo 架构
- 不要忽略 license
- 不要在未验证时声称可运行
- 不要混入无关重构

## Handoff
结果应能交给：

- code-debugging
- code-experiment-config-management
- paper-reproduction
