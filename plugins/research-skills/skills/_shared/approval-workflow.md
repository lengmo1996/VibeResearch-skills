# Approval Workflow

Approval is destination- and action-specific. A request to analyze, draft, or propose does not authorize release, external writes, long-term persistence, destructive mutation, permission expansion, commit, or push.

## Classes

1. Read-only inspection and analysis: proceed within the requested scope.
2. Explicitly requested workspace edits: apply minimal reversible changes, preserve user data, and validate.
3. Long-term memory, Profile, approved writing knowledge, or external-system writes: require explicit destination-specific authorization.
4. Evolution candidates: observations may create a dry-run proposal only after a valid threshold; they never authorize active mutation.
5. Release, rollback overwrite, merge/split/delete, alias removal, routing/RAG-boundary changes, new permissions/side effects, commit, or push: require a separate explicit approval scoped to exact behavior and paths.

Record the approval basis, status, date, affected paths, allowed actions, and forbidden actions in the proposal or handoff. Missing, ambiguous, stale, or out-of-scope approval blocks only the affected side effect; continue safe independent work when useful.

Never weaken an approval gate because a test, dependency, credential, or user response is unavailable. Generate a dry-run plan and report the exact blocker.
