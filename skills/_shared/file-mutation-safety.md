# File Mutation Safety

Preserve user data and existing work by default.

- Inspect target files and repository status before editing. Treat unrelated or pre-existing changes as user-owned.
- Modify only authorized paths with the smallest reviewable patch. Do not overwrite a whole file when a narrow change is sufficient.
- Do not delete, recursively move, rename, replace generated assets, or discard Git changes without explicit authorization for that exact action.
- Resolve and verify absolute targets before recursive operations. Keep every computed target inside the intended workspace or named destination.
- Preserve encodings, line endings when practical, formulas, data, citations, configs, and legacy assets unless their change is in scope.
- Make writes reversible; use dry-run plans for rollback, release, bulk rewrites, and migrations. Actual restoration or removal is a separate action.
- Validate syntax, links, schemas, tests, or rendering in proportion to risk, and report changed paths plus remaining failures.

An authorization to edit the workspace does not imply permission to write external systems, long-term memory, KnowledgeHub, Git history, or remotes.
