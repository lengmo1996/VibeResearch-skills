---
name: research-uncertainty-units
description: "Audit or plan physical units, measurement models, and measurement-uncertainty budgets or propagation (单位换算、测量不确定度、误差传递). Returns traceable calculations, reporting precision, and a ready/conditional/blocked verdict."
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

Unknown values remain unresolved. A bare number does not reveal its calibration
uncertainty, covariance, coverage factor, or unit, so none of these is inferred from
one.

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

In a chat answer, lead with the result and its uncertainty as it should be reported, then the component that dominates the budget and any blocking input, per [output voice](../../_shared/output-voice.md). A saved analysis contains:

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

## Stop conditions

Stop when the verdict matches the unresolved material assumptions and the next owner is named. Shared rules:
[evidence](../../_shared/evidence-policy.md),
[approval](../../_shared/approval-workflow.md),
[environment](../../_shared/environment-compatibility.md),
[file safety](../../_shared/file-mutation-safety.md).
