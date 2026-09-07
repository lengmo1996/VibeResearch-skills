# Power Analysis Protocol

## 1. Freeze the target

Distinguish the experimental unit, observation unit, and analysis unit. State the
primary estimand and analysis model before calculating power. Specify whether the
plan solves for total sample size, achieved power, or minimum detectable effect.

## 2. Source assumptions

For every numerical assumption, record:

- parameter and units;
- value or range;
- source type: prior study, meta-analysis, pilot, historical data, domain
  constraint, or user-approved planning scenario;
- locator and applicability limits;
- status: resolved, conditional, or unresolved.

Do not label an assumption as empirical when it is merely conventional. Do not use a
current-study estimate without recording circularity or optimism risk.

## 3. Choose the calculation family

Closed-form calculations are appropriate only when the planned analysis and the
formula's assumptions align. Prefer simulation when the design includes complex
dependence, nonstandard estimators, adaptive decisions, missingness mechanisms,
multiple stages, or a decision rule that cannot be represented faithfully by a
standard approximation.

Record the method, implementation, implementation version, formula or algorithm
reference, and rounding policy. Independent software should not be treated as
equivalent unless parameterization and defaults are reconciled.

## 4. Apply design adjustments

Keep each adjustment visible. For equal cluster size `m` and intraclass correlation
`rho`, a common design-effect approximation is `1 + (m - 1) * rho`; document when
unequal sizes or another model invalidate it.

Separate:

1. analytical sample size before adjustment;
2. clustering or dependence inflation;
3. attrition or nonresponse inflation;
4. allocation and whole-unit rounding;
5. final recruitment or observation target.

Multiplicity should be handled through the planned decision rule or an explicit
alpha/power adjustment, never through an unstated after-the-fact choice.

## 5. Simulation contract

A simulation plan must define the data-generating model, parameter scenarios,
sampling and missingness process, fitted analysis, rejection or success rule,
random-number generator or implementation, seed, repetitions, and Monte Carlo
uncertainty target. Failed fits and numerical errors need a declared policy.

## 6. Sensitivity and audit

Vary assumptions that materially affect the decision, especially effect size,
variance, event rate, attrition, intraclass correlation, and cluster size. Report
scenario-specific outputs rather than a single unsupported value.

An audit verifies target alignment, assumption provenance, parameterization,
adjustments, implementation/version, reproducibility metadata, and verdict. It
should not claim numerical verification unless the calculation was independently
reproduced.

## Artifact readiness

The blocked template remains structurally valid. A `ready` artifact additionally
requires resolved assumption statuses and provenance, an explicit multiplicity
policy, and the requested numerical output: both sample-size fields for
`sample-size`, `achieved_power` for `power`, or a positive solved `effect_size` for
`mde`. Each reported sensitivity scenario needs a numerical `result`. Leave
unfinished calculations `conditional` or `blocked`; clearing the top-level
`unresolved` list does not resolve nested assumptions. These are consistency checks,
not independent verification of a statistical calculation.
