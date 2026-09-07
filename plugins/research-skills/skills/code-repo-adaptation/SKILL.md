---
name: code-repo-adaptation
description: "Use when migrating an existing repository across environments, dependencies, framework APIs, dataset layouts, training/inference pipelines, or checkpoint formats. Produces a compatibility patch and verification handoff. Do not use for minimal reproduction, ordinary bug diagnosis, testing, or final verification."
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

1. Record the source repository/revision, target compatibility contract, hard
   constraints, and known unknowns.
2. In `repo-understanding`, map only the surfaces needed for the migration.
3. Read [migration decision protocol](references/migration-decision-protocol.md).
   Assign stable `SURF-*`, `DEC-*`, and `INV-*` IDs. Build a Compatibility Matrix:
   current behavior, target behavior, evidence, incompatibility, planned change,
   risk, invariant, and rollback.
4. Select the narrowest compatibility mode and isolate compatibility axes when
   feasible; do not combine unrelated cleanup or hide a second migration.
5. Before writes, list exact paths and obtain explicit authorization.
6. Apply a minimal reversible patch and document every compatibility deviation,
   affected decision IDs, and hard-constraint exception.
7. Do not run acceptance tests or state that the migration works. Produce a
   `Verification Handoff` for `code-debugging`.

## Allowed work

- Understand directories, entry points, module relationships, and compatibility
  surfaces.
- Modify dependencies and compatibility code.
- Migrate framework APIs and component interfaces.
- Adapt Dataset/DataLoader, existing training/validation/inference entry points, and
  checkpoint loading to the target environment.
- Produce a migration patch, compatibility matrix, changed-path list, risk notes, and
  rollback guidance.

## Prohibited work

- Do not construct a minimal reproduction for a failure.
- Do not diagnose or fix an ordinary bug unrelated to compatibility migration.
- Do not run regression tests or issue a final pass/fail verdict.
- Do not absorb paper-method implementation.
- Do not claim that a candidate compatibility patch is verified.

If investigation shows the root cause is an ordinary defect rather than an
environment, dependency, API, data-layout, pipeline, or checkpoint incompatibility,
hand off evidence to `code-debugging` without applying an unrelated fix.

## Output contract

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

Stop when the migration patch and handoff are complete, authorization is missing, a
hard target constraint conflicts with the requested migration, or the root cause is
outside compatibility ownership.
