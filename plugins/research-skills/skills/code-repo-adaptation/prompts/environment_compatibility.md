# Environment and Dependency Compatibility

Build a source/target matrix for Python, OS, accelerator, CUDA/driver, compiler/build
tools, core frameworks, extensions, and package constraints. Distinguish:

- hard incompatibility;
- unsupported but plausible combination;
- version declaration mismatch;
- missing evidence.

Do not silently downgrade a hard constraint. Produce a migration patch and verification
request, not a pass verdict.

