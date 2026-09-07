# Patch Verification Prompt

Consume a `verification_request`.

For each changed path, reproduction step, expected invariant, expected output, known
risk, and unresolved item, record whether it was exercised and the observed evidence.
A successful command is insufficient. Return only:

- `verified` when all required behavior and regressions pass;
- `failed` when a declared expectation fails;
- `blocked` when required inputs, environment, or assertions are unavailable.

