# Resource Preflight Protocol

## Evidence and scope

Every value records source, observation time, evidence class, and scope. Host CPU/RAM
can exceed process affinity, cgroup/container, or scheduler limits. An absent finite
limit is not proof of unlimited capacity.

## Resource families

- CPU: logical/physical inventory, affinity/cpuset, quota, worker and thread ceiling;
- memory: host available, effective hard limit, current usage, pressure threshold;
- disk: free/user-available space, quotas, input/temp/output/checkpoint requirements;
- accelerators: allocation/visibility, permission, driver/runtime, framework and
  operator compatibility, dedicated versus unified memory;
- software: OS/architecture, runtime, packages, compiler/toolchain, licenses;
- operations: network/access, permissions, scheduler, wall time, restart/checkpoint;
- budget: local time, API quota, cloud cost, and user-approved ceiling.

## Matching and verdicts

Match requirements only against compatible units and effective scopes.

- `go`: all hard requirements met; headroom and remaining risks explicit;
- `conditional`: hard requirements are met only under named fallback or unresolved
  soft checks remain;
- `no-go`: one or more hard requirements are observed unmet;
- `not-evaluable`: one or more hard requirements lack sufficient evidence.

Visible accelerators are candidates, not runtime-ready devices. Estimates may guide
fallbacks but cannot alone satisfy a hard requirement unless the user accepts that
assumption.

## Offline report checks

An `observed` match uses observations with `status: success`, a value, source, and
observation time. A `met` or `unmet` requirement must have non-empty evidence references with
the same resource and unit; a hard requirement cannot be satisfied by host-only
visibility. Use the process/container/scheduler/runtime/budget scope that actually
constrains the workload. Numeric minima are checked against the tightest linked
compatible finite numeric value, and the result must agree with the declared match.
Cross-unit conversions must be explicit before validation.

Numbers require finite numeric observations; strings and booleans are not implicitly
converted into numbers. Boolean requirements use exact boolean equality. A textual
version/compatibility condition requires textual observations plus an `evaluation`
object on the match: matching `status`, a non-placeholder `method` and `rationale`,
and non-empty `evidence_ids` drawn from compatible observations. This records the
explicit comparison basis; the checker does not itself prove a free-text version or
operator-compatibility judgment. Objects/lists are not valid resolved minima.

For a user-accepted estimate or declaration, attach
`assumption_acceptance: {"accepted": true, "evidence": "<actual user decision reference>"}`
to the match; do not infer acceptance. Unknown observations never satisfy `met`.
`go` has no unresolved checks. `conditional` cannot hide unknown or unmet hard
requirements: name the fallback for conditional hard matches, or list only remaining
soft checks when all hard matches are met.

The checker validates the supplied report's consistency. It does not run probes,
prove that a source is truthful, verify user consent, or certify runtime compatibility.

## Privacy and probes

Use allowlisted read-only probes and redact machine/job/device identifiers, paths,
environment values, and credentials. Never use benchmarks or allocations as probes.
