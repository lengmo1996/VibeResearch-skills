# Repo Adaptation - dataset_adapter_plan Prompt

## Role
使用 `$code-repo-adaptation` 的 `dataset-compatibility` 模式。此文件保留历史提示入口名称。

## Goal
说明所需 Dataset/DataLoader 接口、预处理、路径和模态布局适配。

## Required Output
遵循 `SKILL.md` 中 `dataset-compatibility` 的范围和输出合同，只保留相关结论及重要不确定性。

## Constraints
- 不要大改 repo 架构
- 不要忽略 license
- 不要在未验证时声称可运行
- 不要混入无关重构

## Handoff
仅在当前请求需要下游工作时交接。复用已有证据与授权，不因阶段切换重新等待确认。
