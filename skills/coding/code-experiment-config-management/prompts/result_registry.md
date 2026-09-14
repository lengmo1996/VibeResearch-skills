# Experiment Config Management - result_registry Prompt

## Role
使用 `$code-experiment-config-management` 的 `result-registry` 模式。此文件保留历史提示入口名称。

## Goal
定义结果和日志记录、run/artifact 关联与失败状态。

## Required Output
遵循 `SKILL.md` 中 `result-registry` 的范围和输出合同，只保留相关结论及重要不确定性。

## Constraints
- 不要过早引入复杂 MLOps
- 不要让配置层级过深
- 不要丢失 seed 和 commit
- 不要混淆科研变量和工程参数

## Handoff
仅在当前请求需要下游工作时交接。复用已有证据与授权，不因阶段切换重新等待确认。
