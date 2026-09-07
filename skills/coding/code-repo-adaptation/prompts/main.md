# Code Repo Adaptation Prompt

Treat this as a compatibility migration, not a debugging task.

1. Identify explicit source and target contracts.
2. Map the repository surfaces relevant to that migration.
3. Select one of the environment, dependency, framework, dataset, training pipeline,
   inference, checkpoint, or patch modes.
4. Produce a compatibility matrix and the smallest reversible authorized patch.
5. Record changed paths, deviations, risks, and rollback notes.
6. Produce the unified verification request for `code-debugging`.

Do not create a minimal reproduction, diagnose unrelated bugs, execute acceptance
tests, or claim the migration passed.
