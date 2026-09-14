# Code Repo Adaptation Prompt

Treat this as a compatibility migration, not a debugging task.

Use only steps needed for the selected mode. Repository understanding is read-only;
patch records and verification handoffs apply to actual changes or a requested plan.

1. Identify explicit source and target contracts.
2. Map the repository surfaces relevant to that migration.
3. Select one of the environment, dependency, framework, dataset, training pipeline,
   inference, checkpoint, or patch modes.
4. Produce a compatibility matrix and the smallest reversible authorized patch.
5. Record changed paths, deviations, risks, and rollback notes.
6. Produce the unified verification request for `code-debugging`.

This migration stage does not diagnose unrelated bugs or issue acceptance verdicts.
If implementation and validation are already authorized, continue the handoff through
`$code-debugging` in the same task; otherwise return the requested candidate or plan.
