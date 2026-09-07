---
name: research-uncertainty-units
description: "Use when auditing or planning physical units, dimensional consistency, measurement models, Type A or Type B uncertainty, uncertainty budgets, correlated propagation, Monte Carlo propagation, coverage factors, significant figures, or plausibility of measured quantities. Produces an auditable uncertainty-and-units record with provenance, propagation metadata, reporting rules, and a ready/conditional/blocked verdict. Do not use for statistical power, dataset-quality auditing, general result interpretation, instrument operation, or unsupported conversion from model uncertainty to measurement uncertainty."
---

# Research Uncertainty Units

## Purpose

Preserve units and uncertainty provenance from measured inputs through a stated
measurement model to a reportable result. Separate dimensional validity, numerical
propagation, metrological evidence, and physical plausibility.

## Required inputs

- measurand, measurement model, and output unit;
- each input estimate, unit, standard uncertainty or original uncertainty statement,
  evaluation type, distribution, source, and applicable degrees of freedom;
- known correlations or an explicit statement that correlation is unresolved;
- requested propagation and reporting level.

Unknown values remain unresolved. Never infer a calibration uncertainty, covariance,
coverage factor, or measurement unit from a bare number.

## Modes

- `unit-audit`: units, dimensions, offset/logarithmic scales, and conversions.
- `budget`: Type A/Type B components, divisors, sensitivities, and contributions.
- `propagation`: analytical, covariance-aware, Monte Carlo, or hybrid method plan.
- `reporting`: standard/expanded uncertainty, coverage, notation, and rounding.
- `plausibility`: order-of-magnitude and regime checks with declared references.
- `full`: integrated measurement model, budget, propagation, and report.

Use the lightest sufficient mode.

## Workflow

1. Freeze the measurand and write the measurement model before calculating.
2. Attach a unit and uncertainty statement to every input. Distinguish estimate,
   standard uncertainty, expanded uncertainty, limits, and distribution.
3. Audit dimensional consistency and conversions. Treat offset and logarithmic units
   as special cases; do not apply ordinary additive arithmetic to them.
4. Build the uncertainty budget. Convert stated components to standard uncertainty
   with an explicit divisor, record sensitivity coefficients, and preserve degrees
   of freedom and provenance.
5. Identify correlations. Do not combine correlated contributions as independent.
6. Select a propagation method. Use analytical propagation only when its
   linearization and distribution assumptions are defensible; otherwise specify a
   reproducible Monte Carlo or hybrid check.
7. Check result plausibility against a cited physical scale, dimensionless regime, or
   domain bound when the task asks for it. A dimensional pass is not a plausibility
   pass.
8. Round uncertainty first and the estimate to the same decimal place. State whether
   `±` is standard or expanded, the coverage factor/probability, and the method.
9. Issue `ready`, `conditional`, or `blocked` with unresolved inputs and handoffs.

Read [references/uncertainty-units-protocol.md](references/uncertainty-units-protocol.md)
for distribution conversion, covariance, propagation choice, and reporting rules.

## Output contract

Produce:

- stable `UNC-*` identifier and mode;
- measurand and measurement model;
- input and correlation ledgers with provenance;
- unit/dimensional audit;
- uncertainty budget and propagation method;
- calculation implementation, version, and simulation seed/repetitions when used;
- result, coverage, notation, rounding, and plausibility statement;
- limitations, unresolved items, verdict, and handoff.

Use [templates/uncertainty-budget.json](templates/uncertainty-budget.json) for a
machine-checkable artifact. Validate without changing it:

```powershell
<python-command> <skill-root>/scripts/validate_uncertainty_budget.py path/to/uncertainty-budget.json
```

## Boundaries and handoffs

- `$research-statistical-power`: sample size, target power, or MDE.
- `$research-dataset-metric-protocols`: evaluation units, metrics, statistical tests,
  and comparison protocol.
- `$research-result-analysis`: interpretation of completed experimental evidence.
- `$research-data-quality-audit`: missingness, duplicates, schema, ranges, and
  dataset-level fitness once that dedicated owner is available.
- Code-oriented unit defects may be handed to `$code-debugging` after a reproducible
  finding is established.

This skill does not operate instruments, edit analysis code, install packages, or
claim conformity with a metrology standard. It may perform local calculations only
when inputs and formulas are explicit.

## Completion checklist

- units remain attached or every stripping boundary names the target unit;
- measurement model and all corrections are explicit;
- uncertainty statements are normalized with traceable sources;
- correlations and degrees of freedom are resolved or visibly blocked;
- propagation choice and reproducibility metadata are justified;
- reporting precision and coverage meaning are unambiguous;
- verdict matches unresolved material assumptions.

Follow the shared evidence, approval, environment, and file-mutation policies under
`skills/_shared/`.
