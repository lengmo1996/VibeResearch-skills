---
name: code-experiment-config-management
description: "Define or maintain experiment configs, seeds, run IDs, checkpoints and resume rules, logs, sweeps, and archives, or run and monitor an already-frozen plan when authorized (配置管理、随机种子、断点续训、实验记录). Returns a reproducible run contract, run record, or acceptance report."
---

# Code Experiment Config Management

## Purpose

`code-experiment-config-management` owns the lifecycle metadata that makes runs
identifiable, resumable, comparable, and archivable. It does not own model-method code,
repository compatibility, failure diagnosis, or scientific interpretation.

## Inputs

Provide the subset relevant to the selected mode: experiment variables, configuration system, dataset/model identifiers,
training settings, output root, seed policy, logging needs, checkpoint/resume
requirements, and any existing run directory convention. `run-lifecycle` additionally
requires frozen `EXP-*`, `CLM-*`, protocol and metric IDs, acceptance criteria, a
validated manifest, and an explicit user-authorized repository-native command.
Missing values are named as missing (`not provided / unclear` in manifests).

## Modes

- `config-tree`: organize YAML/JSON/argparse/Hydra configuration and override rules.
- `seed-policy`: define global and component seeds, determinism settings, and recorded
  sources of nondeterminism.
- `run-identity`: define stable run names, IDs, tags, commit/config fingerprints, and
  collision behavior.
- `checkpoint-resume`: define checkpoint naming, latest/best selection, saved state,
  resume validation, and partial-resume policy.
- `result-registry`: define metrics/log records and links from runs to artifacts.
- `archive`: define immutable run manifests, directory layout, retention, and export.
- `run-lifecycle`: execute an already-frozen plan, monitor normal run state, collect
  artifact metadata, and evaluate protocol acceptance without scientific
  interpretation.
- `full`: produce the complete run/config/checkpoint/archive contract.

Legacy prompt modes such as `hydra_config_tree`, `experiment_naming`, and
`result_registry` map to the corresponding canonical mode.

## Workflow

Use only steps needed by the selected mode; reuse existing policies and manifests.
Do not design checkpoint, archive, or execution contracts for a seed-only question.

1. Separate scientific variables from infrastructure and bookkeeping parameters.
2. Read only relevant sections of [experiment lifecycle protocol](references/experiment-lifecycle-protocol.md).
   Define the configuration tree, defaults, override precedence, materialized config,
   and schema checks.
3. Define seed/determinism policy and record unavoidable nondeterminism.
4. Define run identity from a canonical config fingerprint, code/data identities, and
   stable fields; never rely only on timestamps or display names.
5. Define checkpoint contents, naming, best/latest policy, compatibility metadata, and
   an `exact / compatible / unsafe` resume decision matrix.
6. Define logs, result records, output directories, manifests, lineage, and
   archive/retention rules. Register failed and interrupted runs as well as successes.
7. For `run-lifecycle`, read
   [run lifecycle](references/run-lifecycle.md), validate
   [run_manifest.json](templates/run_manifest.json) with
   `scripts/validate_run_manifest.py <manifest.json> --execution-ready --workspace-root <authorized-workspace>`,
   verify output-path isolation, and confirm the
   exact repository-native command is explicitly authorized. Execute only that
   command; append state events; collect artifact metadata with
   `scripts/collect_run_artifacts.py`; then evaluate only the frozen protocol
   acceptance criteria.
8. Produce a handoff only when an actual downstream integration needs it. Route a
   concrete failure to `code-debugging` and valid completed artifacts to
   `research-result-analysis`.

## Output contract

In a chat answer, lead with the decision or contract the user asked for, then the risks
that could break reproducibility, per [output voice](../../_shared/output-voice.md).
For a narrow mode, return its named contract plus material risks or missing inputs;
do not emit unrelated sections or empty manifests. The following is a section source
for `full`, not a mandatory checklist for every request:

1. Configuration Tree and Override Rules
2. Seed and Determinism Policy
3. Run Naming and Identity Contract
4. Checkpoint and Resume Contract
5. Logging and Result Registry
6. Directory and Archive Layout
7. Example Manifest
8. Risks, Missing Inputs, and Integration Handoff

For `run-lifecycle`, output the validated start manifest, append-only state events,
artifact inventory, and
[run acceptance report](templates/run_acceptance_report.md). A protocol acceptance
verdict means the required run and artifact contract was satisfied; it is not a
scientific claim verdict.

## Boundaries

- Core paper-method implementation belongs to `paper-reproduction`.
- Environment/framework/data/pipeline/checkpoint-format migration belongs to
  `code-repo-adaptation`.
- Failures, smoke/minimal runs, tests, and patch verification belong to
  `code-debugging`.
- Experimental controls and scientific comparisons belong to
  `research-experiment-design`.
- Completed result interpretation belongs to `research-result-analysis`.

This Skill may specify checkpoint metadata and resume semantics, but migration of a
legacy checkpoint format belongs to `code-repo-adaptation`.

Do not construct or execute an arbitrary shell string. Use an inspected
repository-native entrypoint and explicit argument list. Do not retry a failed run
with changed parameters under the same run ID; hand off the failure or create a new
versioned plan after authorization.

Never overwrite the immutable start manifest to reflect later state. Append lifecycle
events and produce a final manifest that links back to the same run ID.

Stop when the requested lifecycle contract is complete or missing project decisions
would materially change the configuration design.
