# Environment Compatibility

Treat the user's current environment and explicit package versions as hard constraints.

- Inventory OS, interpreter, accelerator/driver, package versions, lock/config files, and relevant commands before adaptation.
- Prefer code/config adaptation and the smallest reversible patch. Do not downgrade or replace core packages merely to match an upstream repository.
- A dependency install, environment recreation, CUDA/toolchain change, or core-version change requires an explicit reason, impact statement, rollback path, and user authorization when it changes the existing environment.
- Validate eager/minimal execution before optimized, compiled, distributed, or full-scale execution.
- Record exact versions, commands, deviations from upstream, expected artifacts, and unresolved incompatibilities.
- Distinguish environment mismatch, API drift, binary incompatibility, data/protocol error, and implementation defect; do not hide one category with an unrelated dependency change.

If the requested result cannot be achieved under the hard constraints, stop the affected action and present compatible alternatives. Never report a reproduction as successful after silently changing its protocol or environment.
