# Framework API Compatibility

For every PyTorch, Lightning, Diffusers, Transformers, or adjacent API migration,
record the old contract, target contract, affected call sites, state/checkpoint impact,
behavioral risk, and rollback. Preserve model semantics unless the compatibility
contract explicitly requires a change.

Hand the candidate patch and expected invariants to `code-debugging`.

