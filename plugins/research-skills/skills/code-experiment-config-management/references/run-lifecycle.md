# Run lifecycle

Load only for `run-lifecycle`. Do not load for configuration design, checkpoint
policy, result-registry design, archive-only work, debugging, or result
interpretation.

## Preconditions

Require:

- frozen `EXP-*` and applicable `CLM-*`, protocol, and `MET-*` IDs;
- result-independent acceptance or stop criteria;
- code, data, config, and seed identities;
- a relative isolated output root;
- an inspected repository-native entrypoint and explicit argument list;
- explicit user authorization to execute that exact command.

If the plan, command, or output boundary is missing, return a manifest scaffold and
stop before execution.

## Lifecycle

1. Validate the start manifest with the execution gate:
   `<python-command> <skill-root>/scripts/validate_run_manifest.py <manifest.json> --execution-ready --workspace-root <authorized-workspace>`.
   This requires resolved code/data/config fingerprints, a non-empty component seed
   map, an existing repository-native entrypoint, and contained working/output
   paths. Output roots must be relative, distinct from the workspace root, and free
   of POSIX/Windows roots, drive-relative paths, and traversal. Resolve paths again
   immediately before launch if the filesystem has changed.
2. Check that the run ID is unused or that the action is an explicitly compatible
   resume. Never reuse an ID for changed scientific variables.
3. Execute the exact authorized entrypoint without shell-string expansion. Record the
   start event, code/config/data identities, and process result.
4. Monitor declared health and progress records without changing hyperparameters,
   killing unrelated processes, or treating metric trends as scientific conclusions.
5. On failure, record the terminal state and hand off logs, command tokens, manifest,
   and reproduction steps to `code-debugging`. Do not improvise a fix or silent retry.
6. On completion, collect artifact metadata and verify required files, IDs, metrics,
   and completion markers against the frozen acceptance criteria.
7. Hand valid result artifacts and the original decision rules to
   `research-result-analysis`.

## Acceptance boundary

Protocol acceptance answers whether the planned run completed under the declared
identity and produced required artifacts. It does not answer whether a paper claim is
supported, whether an improvement is meaningful, or why a metric changed.

Without `--execution-ready`, the validator checks draft structure only; the empty
identity fields in `templates/run_manifest.json` are intentional placeholders.
Earlier draft manifests remain editable and cannot authorize execution. The stronger
check does not prove command approval, inspect program behavior, verify fingerprint
contents, or establish unused run identity; those remain the explicit preconditions
above. Artifact collection remains a read-only operation with its own containment
check.
