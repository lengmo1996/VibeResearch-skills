# Quality Checklist

- `UNC-*` identity is stable.
- Measurand, output unit, and measurement model are explicit.
- Every input retains estimate and unit.
- Every uncertainty statement names its type, distribution, divisor, and source.
- Type A degrees of freedom are present when derived from finite repeated data.
- Sensitivity coefficients and units map components to the measurand.
- Correlation is resolved or explicitly blocks readiness.
- Unit audit distinguishes dimensions from physical meaning.
- Offset and logarithmic scales receive special handling.
- Propagation method matches nonlinearity, bounds, and distribution behavior.
- Simulation metadata is reproducible when Monte Carlo is used.
- Coverage factor/probability and uncertainty type are named.
- Uncertainty and value use defensible aligned rounding.
- Plausibility evidence is cited and not treated as a dimensional proof.
- Verdict agrees with unresolved material inputs.

## Moved from SKILL.md

- [ ] Units remain attached or every stripping boundary names the target unit.
- [ ] Measurement model and all corrections are explicit.
- [ ] Uncertainty statements are normalized with traceable sources.
- [ ] Correlations and degrees of freedom are resolved or visibly blocked.
- [ ] Propagation choice and reproducibility metadata are justified.
- [ ] Reporting precision and coverage meaning are unambiguous.
- [ ] Verdict matches unresolved material assumptions.
