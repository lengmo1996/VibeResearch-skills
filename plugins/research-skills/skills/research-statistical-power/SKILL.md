---
name: research-statistical-power
description: "Calculate, plan, stress-test, or audit sample size, statistical power, minimum detectable effect, design effect, or simulation-based power for a defined study design (样本量、统计功效、需要跑几次). Returns an auditable power plan with sourced assumptions and a ready/conditional/blocked verdict."
---

# Research Statistical Power

## Purpose

Turn a defined study design and estimand into an auditable statistical-power plan.
Own the calculation contract and its assumptions; do not silently choose the
scientific design, dataset protocol, metric, or final claim.

## Required inputs

- primary estimand, statistical test or model family, and evaluation unit;
- quantity to solve for: sample size, achieved power, or minimum detectable effect;
- significance level, target power when applicable, sidedness, and allocation;
- effect-size scale plus a traceable source or an explicit unresolved marker;
- dependence structure, attrition, clustering, repeated measures, multiplicity, and
  other design adjustments that may change effective sample size.

If a required value is unknown, keep it unresolved. A conventional default (alpha
0.05, power 0.8, a “medium” effect) enters only as a labeled, user-approved
assumption, because the sample size it produces is only as good as that value.

## Modes

- `closed-form`: use a justified analytical method for a supported design.
- `simulation`: specify a reproducible data-generating and decision process.
- `sensitivity`: compare plausible assumptions rather than select one silently.
- `audit`: inspect an existing calculation and its provenance.
- `full`: combine method selection, adjustment, sensitivity, and audit checks.

Use the lightest sufficient mode.

## Workflow

1. Freeze the target: estimand, analysis unit, test/model, sidedness, alpha,
   allocation, and the quantity being solved.
2. Build an assumption ledger. Record every effect, variance, event rate,
   correlation, attrition rate, cluster parameter, and multiplicity choice with its
   scale, value or range, source, and status.
3. Select the calculation family. State why a closed-form approximation is valid or
   why simulation is required.
4. Apply design adjustments explicitly. Keep raw sample size, effective sample size,
   design effect, attrition inflation, and rounding policy distinguishable.
5. Run sensitivity scenarios whenever a material assumption is uncertain. Do not
   collapse a range to an unsupported point estimate.
6. Record reproducibility metadata: implementation, version, method, formula or
   algorithm reference, random seed and repetitions for simulation, and rounding.
7. Return a `ready`, `conditional`, or `blocked` verdict with unresolved items and
   the next owner.

Read [references/power-analysis-protocol.md](references/power-analysis-protocol.md)
when selecting the calculation family, handling clustering or simulation, or
auditing an existing plan.

## Output contract

In a chat answer, lead with the number the user asked for and the one or two
assumptions it hinges on, then the sensitivity range, per
[output voice](../_shared/output-voice.md). A saved power plan contains:

- stable `PWR-*` identifier and mode;
- frozen design and calculation target;
- assumption ledger with provenance;
- unadjusted and adjusted quantities;
- sensitivity table;
- implementation and reproducibility metadata;
- explicit limitations and unresolved items;
- verdict: `ready`, `conditional`, or `blocked`;
- handoff notes for experiment design, dataset/metric protocol, or implementation.

Use [templates/power-plan.json](templates/power-plan.json) when a machine-checkable
artifact is useful. Validate it without modifying it:

```powershell
<python-command> <skill-root>/scripts/validate_power_plan.py path/to/power-plan.json
```

## Evidence and calculation policy

- Treat literature values, pilot estimates, historical variance, and domain
  conventions as different evidence classes.
- Preserve units and effect-size scale; do not compare or combine incompatible
  standardized and raw effects.
- Mark values derived from the current data when that creates circularity or
  optimistic bias.
- Report sensitivity or a blocked verdict when effect size, variance, intraclass
  correlation, event rate, or analysis model is materially unresolved.
- A validator can check contract completeness, not the scientific validity of a
  model or the numerical correctness of third-party software.

## Handoffs and boundaries

- Send whole-experiment design, controls, baselines, and ablations to
  `$research-experiment-design`.
- Send splits, preprocessing, leakage controls, metrics, and statistical comparison
  protocols to `$research-dataset-metric-protocols`.
- Send executable configuration binding to `$code-experiment-config-management`.
- Send interpretation of completed observations to `$research-result-analysis`.

This skill is read-only by default. It may calculate or validate supplied artifacts,
but it does not launch experiments, change source code, or invent observations.

## Stop conditions

Stop when the verdict matches the unresolved assumptions and the next owner is named.
Shared rules: [evidence](../_shared/evidence-policy.md),
[approval](../_shared/approval-workflow.md),
[environment](../_shared/environment-compatibility.md),
[file safety](../_shared/file-mutation-safety.md).
