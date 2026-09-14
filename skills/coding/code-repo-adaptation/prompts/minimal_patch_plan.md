# Repo Adaptation - minimal_patch_plan Prompt

## Role
使用 `$code-repo-adaptation` 的 `compatibility-patch` 模式。此文件保留历史提示入口名称。

## Goal
说明最小兼容性补丁计划、范围、风险与验证步骤；仅计划请求不实施补丁。

## Required Output
遵循 `SKILL.md` 中 `compatibility-patch` 的范围和输出合同，只保留相关结论及重要不确定性。

## Constraints
- 不要大改 repo 架构
- 不要忽略 license
- 不要在未验证时声称可运行
- 不要混入无关重构

## Handoff
仅在当前请求需要下游工作时交接。复用已有证据与授权，不因阶段切换重新等待确认。
