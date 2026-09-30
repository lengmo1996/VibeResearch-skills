---
name: code-repo-adaptation
description: "Migrate an existing repository across Python/CUDA environments, dependencies, framework APIs, dataset layouts, training or inference pipelines, or checkpoint formats (环境迁移、升级 PyTorch、适配新数据集格式、跑通旧仓库). Returns a compatibility patch and a verification handoff."
---

# Code Repo Adaptation

## Purpose

`code-repo-adaptation` owns compatibility migration for an existing repository. It
may understand the repository and modify compatibility surfaces, but it does not
diagnose unrelated defects and never decides that the migration passed.

Read the shared [approval workflow](../_shared/approval-workflow.md), [file
mutation safety](../_shared/file-mutation-safety.md), [environment
compatibility](../_shared/environment-compatibility.md), and [operational
boundaries](../_shared/operational-boundaries.md).

## Inputs

Required: existing repository or supplied repository files, target compatibility goal,
source and target constraints, and requested mode. A patch additionally requires
explicit workspace-write authorization.

Optional: dependency manifests, environment inventory, framework versions, dataset
layout, current training/inference entry points, checkpoints, migration errors,
licenses, prior paper-reproduction handoff, and immutable target constraints.

## Modes

- `repo-understanding`: map directories, entry points, modules, data flow,
  configuration, and compatibility-sensitive surfaces.
- `environment-compatibility`: reconcile Python, OS, accelerator, CUDA/driver,
  build-tool, and runtime constraints.
- `dependency-compatibility`: migrate dependency ranges, removed packages, imports,
  and package interactions without silent downgrades.
- `framework-compatibility`: migrate PyTorch, Lightning, Diffusers, Transformers, or
  adjacent framework APIs.
- `dataset-compatibility`: adapt Dataset/DataLoader contracts, preprocessing, paths,
  splits, collate behavior, and modality layout.
- `training-pipeline-compatibility`: adapt existing training/validation entry points,
  hooks, launch semantics, logging interfaces, and distributed assumptions.
- `inference-compatibility`: adapt existing prediction, evaluation, export, or batch
  inference entry points.
- `checkpoint-compatibility`: map state dictionaries, metadata, serialization, key
  names, component layouts, and resume-loading compatibility.
- `compatibility-patch`: implement the smallest reversible compatibility change
  authorized by the user.

## Workflow

Execute only steps needed by the selected mode and request. `repo-understanding`
returns relevant surfaces and compatibility risks; it does not require a patch,
implementation decision ledger, or verification handoff. Create a handoff only for
an actual candidate patch or an explicitly requested downstream plan.

1. Record the source repository/revision, target compatibility contract, hard
   constraints, and known unknowns.
2. In `repo-understanding`, map only the surfaces needed for the migration.
3. Read [migration decision protocol](references/migration-decision-protocol.md).
   Assign stable `SURF-*`, `DEC-*`, and `INV-*` IDs. Build a Compatibility Matrix:
   current behavior, target behavior, evidence, incompatibility, planned change,
   risk, invariant, and rollback.
4. Select the narrowest compatibility mode and isolate compatibility axes when
   feasible; do not combine unrelated cleanup or hide a second migration.
5. Before writes, identify the affected paths and check the existing request/session
   authorization. Record its basis and apply covered minimal reversible changes
   directly. Ask only for scope or controlled actions not already authorized.
6. Apply a minimal reversible patch and document every compatibility deviation,
   affected decision IDs, and hard-constraint exception.
7. Produce a `Verification Handoff` for `$code-debugging`; the patch remains a
   candidate until verified. If the current request includes implementation and
   validation, continue with `patch-verification` in the same task and context.

## Allowed work

- Understand directories, entry points, module relationships, and compatibility
  surfaces.
- Modify dependencies and compatibility code.
- Migrate framework APIs and component interfaces.
- Adapt Dataset/DataLoader, existing training/validation/inference entry points, and
  checkpoint loading to the target environment.
- Produce a migration patch, compatibility matrix, changed-path list, risk notes, and
  rollback guidance.

## Out of scope

Each of these has an owner, and mixing them into a migration hides changes from
review:

- Minimal reproductions, ordinary bugs unrelated to compatibility, regression tests,
  and the final pass/fail judgment belong to `$code-debugging`; a handoff does not
  need another user turn when that work is already authorized.
- Paper-method implementation belongs to `$paper-reproduction`.
- A compatibility patch stays a candidate until `$code-debugging` verifies it.

If investigation shows the root cause is an ordinary defect rather than an
environment, dependency, API, data-layout, pipeline, or checkpoint incompatibility,
hand off evidence to `code-debugging` without applying an unrelated fix.

## Output contract

In a chat answer, lead with what was changed or what blocks the migration, then the
risks, per [output voice](../_shared/output-voice.md). Use these sections only as
needed for the selected mode. A narrow answer may combine
them in prose; omit absent patches and handoffs rather than manufacturing artifacts.

1. Scope Decision
2. Repository Compatibility Map
3. Source/Target Compatibility Matrix
4. Migration Decisions and Evidence
5. Compatibility Patch and Changed Paths — when authorized
6. Deviation and Rollback Notes
7. Known Risks and Unresolved Items
8. Verification Handoff

Use the canonical `verification_request` schema in
[repo-adaptation_plan.md](templates/repo-adaptation_plan.md); do not redefine it in
prompts or references.

`reproduction_steps` are recommended steps for the downstream verifier; this Skill
does not execute them to establish acceptance.

Version-specific files under `references/` are applicable only when their declared
source/target versions match the task. Otherwise treat them as search hints and verify
the target contract from authoritative documentation; never silently transplant a
dated stack profile.

This stage ends when the migration patch and handoff are complete. Return at that
point only for a candidate-only request; continue authorized validation through
`$code-debugging` until the requested task is complete. Missing authorization or a
hard target conflict blocks only the affected action. Route causes outside
compatibility ownership with the existing evidence and authorization scope.
