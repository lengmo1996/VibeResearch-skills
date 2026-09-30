---
name: tool-resource-preflight
description: "Check before running a workload whether CPU, memory, disk, GPU, runtime, dependencies, permissions, scheduler limits, wall time, or budget are enough (跑之前检查显存、磁盘、环境够不够). Returns a redacted inventory, bottlenecks, fallbacks, and a go/conditional/no-go/not-evaluable verdict."
---

# Tool Resource Preflight

## Purpose

Decide whether a defined workload can start safely in the effective execution
environment. Keep host visibility, current-process access, container/cgroup limits,
scheduler allocation, runtime compatibility, and user budget as separate facts.

## Inputs and modes

Required: workload, hard and preferred requirements, intended environment, and
acceptable fallbacks. Optional: existing resource snapshot, runtime/dependency lock,
scheduler allocation, wall-time/cost budget, data/checkpoint sizes, and concurrency.

Modes: `inventory`, `requirements`, `match`, `fallback`, `audit`, and `full`.

## Workflow

1. Freeze the workload and requirements with units and hard/soft classification.
2. Reuse a current snapshot when valid; otherwise plan the narrowest read-only probes.
   Do not persist a machine fingerprint unless explicitly requested.
3. Record observations as `observed`, `declared`, `estimated`, or `unknown`, with
   scope: host, process, container, scheduler, runtime, or budget.
4. Compute effective availability from the tightest applicable observed constraint.
   Unknown is never converted to zero or unlimited.
5. Match each requirement to evidence. GPU visibility is only a candidate until
   permission, driver/runtime, framework, and workload compatibility are checked in
   the exact environment.
6. Identify bottlenecks, headroom, concurrency/oversubscription risk, temporary and
   output storage, checkpoint/restart needs, and wall-time/cost exposure.
7. Propose bounded fallbacks: smaller batch, fewer workers, CPU path, reduced data,
   chunking, streaming, checkpointing, alternate runtime, or scheduled environment.
8. Return `go`, `conditional`, `no-go`, or `not-evaluable`. Do not install, allocate,
   launch, benchmark, or mutate the environment.

Read [references/resource-preflight-protocol.md](references/resource-preflight-protocol.md)
for effective-resource semantics, accelerator gates, privacy, and verdict rules.

## Probe safety

- Fixed, read-only commands with bounded output and short timeouts only.
- No stress test, write probe, large allocation, device reset, power/clock change, or
  full environment dump.
- Redact hostname, job/node IDs, device UUID/PCI address, absolute paths, raw
  visibility variables, credentials, and scheduler secrets.
- A failed probe preserves other observations and becomes an explicit warning.

## Output and validation

In a chat answer, lead with go / conditional / no-go and the bottleneck that decides it, then the fallback, per [output voice](../../_shared/output-voice.md). A saved preflight contains workload requirements, inventory/provenance, effective constraints,
requirement-evidence matrix, bottlenecks, fallbacks, risks, unresolved checks, and
verdict.

Use [templates/resource-preflight.json](templates/resource-preflight.json), then run:

```powershell
<python-command> <skill-root>/scripts/validate_resource_preflight.py path/to/resource-preflight.json
```

The validator is offline and does not probe resources.

## Handoffs

- `$code-experiment-config-management`: bind an approved resource plan into a frozen
  run configuration.
- `$code-repo-adaptation`: environment, dependency, framework, or platform migration.
- `$code-debugging`: concrete runtime/resource failure after execution begins.

## Stop conditions

Stop when every requirement has evidence or an explicit gap and the verdict follows from them. Shared rules:
[approval](../../_shared/approval-workflow.md),
[environment](../../_shared/environment-compatibility.md),
[operational boundaries](../../_shared/operational-boundaries.md),
[file safety](../../_shared/file-mutation-safety.md).
