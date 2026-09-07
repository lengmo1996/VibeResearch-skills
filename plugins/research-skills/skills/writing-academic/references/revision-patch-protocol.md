# Revision patch protocol

Load only for `revision-patch`. Use this workflow for manuscript text, not source-code
patching.

## Bind the target

Resolve one UTF-8 target inside the authorized workspace root. Require unique
line-oriented markers:

```text
<!-- REV:REV-001:START -->
text owned by REV-001
<!-- REV:REV-001:END -->
```

Hash the entire target and each exact block interior before editing. Store
replacement text in a contained file and bind its reviewed UTF-8 bytes with
`replacement_sha256`. Preserve line endings when calculating all hashes. Do not place replacement prose or secrets
inside command arguments.

## Validate before writing

Require:

- manifest schema `1.1.0` (legacy `1.0.0` is accepted only with the same mandatory replacement hash);
- one contained, regular target and contained replacement files;
- unique `REV-*` patch IDs and marker pairs;
- exactly one occurrence of each marker in the correct order;
- exact target, block, and reviewed replacement SHA-256 matches;
- at least one accepted `AUD-*` or explicit user change reference per patch;
- a protected-span result when scientific content is at risk.

The default command performs validation and preview only. A valid preview does not
authorize application.

Older manifests without `replacement_sha256` must be rebuilt after reviewing the
replacement file. The validator never fills an expected hash from current content,
because that would silently accept a changed replacement.

## Apply fail closed

Use `--apply` only after exact target authorization. Recheck every precondition in
the same invocation, build the complete output in memory, verify that only declared
block interiors changed, write a temporary sibling file, and atomically replace the
target.

On any mismatch, write nothing. Never fuzzy-match, silently refresh hashes, remove
markers, or modify an undeclared region. Return the conflicting patch IDs and require
a newly reviewed manifest.

## Verify the result

Report source/output hashes, per-patch original and replacement hashes, unchanged
segment status, and apply status. Run protected-span verification separately because
block/hash integrity does not prove scientific equivalence.
