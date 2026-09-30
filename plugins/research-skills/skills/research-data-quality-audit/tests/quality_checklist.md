# Quality Checklist

- Authorization, stated use, asset identity, observational unit, and coverage exist.
- Missing-code and sensitive-field semantics are supplied or unresolved.
- Findings use stable `DQ-*` IDs, aggregate evidence, and denominators.
- No raw row or direct identifier is included.
- Bounded scans do not claim exhaustive coverage.
- Remediation and verification remain separate.
- No source data are modified.
- Fitness verdict is scoped to the stated use and linked blockers.

## Moved from SKILL.md

- [ ] Authorization, stated use, observational unit, and coverage are explicit.
- [ ] Missing-code and sensitive-field semantics are supplied or unresolved.
- [ ] Findings include denominators and never expose raw identifiers.
- [ ] Bounded or sampled checks are labeled.
- [ ] No data were changed.
- [ ] Fitness is limited to the stated use and supported coverage.
