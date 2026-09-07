# Issue Severity Scale

Use severity for impact and urgency; report confidence separately as `high`, `medium`, or `low`.

| Severity | Meaning | Typical action |
|---|---|---|
| `Blocker` | Invalidates the core result, makes execution/submission unsafe or impossible, or creates a material integrity/security/privacy failure. | Stop the affected workflow; resolve before release/submission. |
| `Major` | Materially weakens correctness, reproducibility, evidence, comparability, or reviewer confidence, but a bounded repair is possible. | Must fix or explicitly justify before the target milestone. |
| `Minor` | Local defect with limited impact on the main conclusion or workflow. | Fix when practical; track if deferred. |
| `Nit` | Cosmetic, stylistic, or optional improvement with no material correctness impact. | Optional cleanup. |

Do not inflate severity to prioritize preferences. For each issue, identify location, evidence, impact, recommended action, and confidence. If impact cannot be established, mark it `unverified` rather than assigning a strong severity.
