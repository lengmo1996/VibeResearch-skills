---
name: paper-reproduction
description: "Use when identifying a paper's core innovation, locating official code, mapping method/equations/architecture to code, or implementing the core method with explicit authorization. Produces a paper-code map and candidate implementation. Do not use for environment migration, experiment-result acceptance, or final verification."
---

# Paper Reproduction

## Purpose

`paper-reproduction` helps understand and complete the core implementation of a
paper's method. Its unit of work is the paper method: contribution, module, loss,
algorithm, architecture change, and their implementation surfaces.

It is not an end-to-end experimental acceptance workflow. A produced patch is a
`candidate implementation` until `code-debugging` verifies its declared invariants.

Read the shared [evidence](../../_shared/evidence-policy.md), [approval
workflow](../../_shared/approval-workflow.md), [file mutation
safety](../../_shared/file-mutation-safety.md), and [operational
boundaries](../../_shared/operational-boundaries.md).

## Inputs

Required: an identifiable paper or source-bounded paper analysis and a requested mode.
Depending on the mode, also provide an official/candidate repository, target
integration repository, constraints, or explicit workspace-write authorization.

Optional: `paper-deep-read` evidence ledger, equations, algorithm blocks, figures,
official project page, repository revision, target interfaces, tensor shapes,
framework constraints, and existing implementation notes.

## Modes

- `innovation-analysis`: extract contribution, novelty, modules, loss terms,
  architecture changes, and algorithm steps.
- `official-code-discovery`: locate author/official repositories and record source,
  identity evidence, revision, and confidence. Do not label third-party code official
  without evidence.
- `code-mapping`: map Method → Equation → Architecture → File → Class/Function and
  identify missing or ambiguous links.
- `implementation`: after explicit authorization, write or integrate the core module,
  loss, or algorithm into the target repository.
- `no-official-code`: produce interfaces, tensor shapes, pseudocode, invariants, and
  inference boundaries first; implement only after explicit authorization.
- `full`: perform innovation analysis, official-code discovery, code mapping, and core
  implementation in order. It still does not perform final verification.

## Workflow

1. Freeze the paper/source scope and reuse the `paper-deep-read` evidence ledger when
   available. Select the output and reference rows below; run only their relevant steps.
2. In `innovation-analysis` or `full`, build the Innovation Map with direct evidence
   and unresolved interpretation. Do not create a code map for an innovation-only request.
3. In `official-code-discovery` or `full`, search for official code;
   record why each source is official, author-maintained, third-party, or uncertain.
   Other modes reuse supplied provenance; unresolved provenance does not silently
   expand a mapping task into an unrestricted repository search.
4. In `code-mapping` or `full`, build the relevant Paper–Code Mapping at module,
   equation, interface, file, and symbol level with stable `MAP-*` IDs. Identify
   observable invariants, without generating a complete implementation specification.
5. For `implementation`, `no-official-code`, or `full`, derive the Core Implementation
   Specification with inputs, outputs, shapes, state, invariants, error cases, and
   integration points. Reuse accepted maps instead of repeating innovation analysis.
6. Before any requested implementation, inspect the target repository and require
   explicit authorization before writes. Keep changes limited to the core method.
7. In modes that specify implementation choices, record paper-fixed behavior, mapping
   inference, and engineering choices with stable `DEC-*` IDs. An unchanged
   paper-fixed specification may explicitly report no new engineering decisions.
8. Only when a patch was produced, mark it `candidate implementation` and emit a
   `verification_request` for `code-debugging` citing relevant mapping/decision IDs.
   Without a patch, report completion or the exact blocker for the requested mode;
   do not manufacture a verification handoff.

## Mode-specific reference loading

Read only these sections of the existing traceability protocol. Do not preload
other modes or the report template for a narrow analysis.

| Mode | Initial reference sections |
|---|---|
| `innovation-analysis` | [innovation evidence](references/paper-code-traceability.md#innovation-evidence) |
| `official-code-discovery` | [repository provenance](references/paper-code-traceability.md#repository-provenance) |
| `code-mapping` | [mapping rule](references/paper-code-traceability.md#mapping-rule) |
| `implementation` | [implementation specification](references/paper-code-traceability.md#implementation-specification), [engineering decisions](references/paper-code-traceability.md#engineering-decisions) |
| `no-official-code` | [no official code](references/paper-code-traceability.md#no-official-code), [implementation specification](references/paper-code-traceability.md#implementation-specification), [engineering decisions](references/paper-code-traceability.md#engineering-decisions) |
| `full` | [innovation evidence](references/paper-code-traceability.md#innovation-evidence), [repository provenance](references/paper-code-traceability.md#repository-provenance), [mapping rule](references/paper-code-traceability.md#mapping-rule), [implementation specification](references/paper-code-traceability.md#implementation-specification), [engineering decisions](references/paper-code-traceability.md#engineering-decisions) |

When an actual patch is ready, additionally read
[patch trace](references/paper-code-traceability.md#patch-trace) and the
[verification handoff template](templates/paper_reproduction_report.md#verification-handoff).
When full-mode discovery cannot establish official code, read the
[no-official-code boundary](references/paper-code-traceability.md#no-official-code).
An implementation lacking a necessary existing map may inspect the mapping rule for
that unresolved link; this is a bounded dependency, not a new full-mode run.

## No-official-code contract

When no official implementation can be established:

- distinguish paper fact, design inference, and engineering choice;
- document unknowns that could change behavior;
- define pseudocode, tensor contracts, expected invariants, and comparison points;
- never claim semantic or numerical equivalence to the paper;
- call any authorized code a `candidate implementation`.

## Mode-specific output

Every mode includes **Scope** (paper/repository material actually inspected). Add
only the selected row's outputs. Innovation and repository-provenance rows include
their own unresolved interpretations or identity evidence; they do not require a
separate paper-to-code section.

| Mode | Required additional output sections |
|---|---|
| `innovation-analysis` | Innovation Map |
| `official-code-discovery` | Repository Provenance |
| `code-mapping` | Paper–Code Mapping; Expected Invariants; Unresolved Paper-to-Code Inferences |
| `implementation` | Core Implementation Specification; Engineering Decision Ledger; Expected Invariants; Unresolved Paper-to-Code Inferences; Implementation Status |
| `no-official-code` | Core Implementation Specification; Engineering Decision Ledger; Expected Invariants; Unresolved Paper-to-Code Inferences |
| `full` | Innovation Map; Repository Provenance; Paper–Code Mapping; Core Implementation Specification; Engineering Decision Ledger; Expected Invariants; Unresolved Paper-to-Code Inferences; Implementation Status |

**Implementation Status** distinguishes a produced patch, an unchanged implementation,
or an attempt blocked by missing evidence/authorization. Include this status also
when `no-official-code` includes requested implementation. **Implementation Patch** and
**Verification Handoff** are conditional outputs: include both only when code changed,
including authorized changes made under `no-official-code`. A mode selection is not
write authorization. The handoff schema lives only in the linked report template;
do not copy or redefine it in prompts or references.

## Compatibility routing for one release

Legacy modes do not execute inside this Skill:

- `environment-audit` → `code-repo-adaptation:environment-compatibility`
- `smoke` → `code-debugging:minimal-reproduction`
- `gap-analysis` → `code-debugging:regression`
- `verification` → `code-debugging:patch-verification`
- `data-protocol` → `research-dataset-metric-protocols`
- `runbook` → `code-repo-adaptation` for compatibility work, otherwise
  `code-experiment-config-management` for run/config/checkpoint lifecycle

Compatibility aliases `environment`, `data`, `execute`, and `verify` follow the same
forwarding rules.

## Hard boundaries

- Do not migrate environments, dependencies, frameworks, datasets, training pipelines,
  or checkpoints; hand those to `code-repo-adaptation`.
- Do not create a minimal reproduction, run regression tests, or issue a final pass
  verdict; hand those to `code-debugging`.
- Do not own seed, run naming, checkpoint/resume policy, or experiment archives; hand
  those to `code-experiment-config-management`.
- Do not claim official metric reproduction or paper equivalence from a runnable
  candidate.

Stop when the selected analysis/discovery/map/specification is complete. Missing write
authorization blocks only requested implementation; it does not block read-only
analysis. For a produced candidate, stop at its verification handoff. Never claim
the blocked remainder of a `full` request was completed.
