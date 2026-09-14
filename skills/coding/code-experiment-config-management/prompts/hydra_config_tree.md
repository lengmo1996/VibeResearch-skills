# Experiment Config Management - hydra_config_tree Prompt

## Role
使用 `$code-experiment-config-management` 的 `config-tree` 模式。此文件保留历史提示入口名称。

## Goal
定义当前配置树、默认值与覆盖顺序；复用已有种子和运行约定。

## Required Output
遵循 `SKILL.md` 中 `config-tree` 的范围和输出合同，只保留相关结论及重要不确定性。

## Constraints
- 不要过早引入复杂 MLOps
- 不要让配置层级过深
- 不要丢失 seed 和 commit
- 不要混淆科研变量和工程参数

## Handoff
仅在当前请求需要下游工作时交接。复用已有证据与授权，不因阶段切换重新等待确认。
