# Uncertainty and Units Protocol

## Measurement model

Name the measurand and express the output as a function of input quantities,
including correction terms whose best estimate is zero. Record the model's scope and
assumptions. A missing correction also removes its uncertainty from the budget.

## Unit audit

Check dimensions before numerical substitution. Preserve units through intermediate
steps and name the unit when extracting a magnitude. Handle temperature differences
separately from absolute temperatures. Convert logarithmic quantities to an
appropriate linear representation before arithmetic. Same dimensions do not imply
the same physical meaning.

## Normalize uncertainty statements

Each component needs its estimate, units, evaluation type, stated uncertainty,
distribution, conversion divisor, standard uncertainty, source, and degrees of
freedom when applicable.

Common planning conversions include:

- an explicitly standard normal uncertainty: divisor 1;
- an expanded uncertainty: divide by its stated coverage factor;
- symmetric rectangular limits: divide the half-width by the square root of 3;
- symmetric triangular limits: divide the half-width by the square root of 6.

Do not apply a divisor without confirming how the source states the value.

## Sensitivity and correlation

Record the sensitivity coefficient for every component and compare contributions on
the common measurand scale. Shared calibration, instrumentation, environmental
effects, fitted parameters, or reused data may induce correlation. Preserve a
covariance/correlation source; independence is an assumption, not an absence of
information.

In a machine-checkable record, declare `correlation_policy.status` as `independent`,
`specified`, or `unresolved`, with a traceable `source`. `independent` has no listed
pairs; `specified` carries the applicable pairs in `correlations`. This records the
assumption explicitly and does not establish its scientific validity. Earlier
drafts without this object remain structurally valid, but cannot be `ready`.

## Propagation choice

Analytical propagation requires a defensible local linearization and compatible input
distributions. Use covariance terms for correlated inputs. Specify Monte Carlo when
nonlinearity, bounds, asymmetry, discontinuities, or complex decision rules make the
analytical approximation doubtful. A simulation record includes model, input
distributions, correlation construction, implementation/version, seed, repetitions,
convergence or Monte Carlo precision, and interval method.

## Coverage and reporting

Distinguish standard uncertainty, combined standard uncertainty, expanded
uncertainty, confidence/credible intervals, and prediction intervals. Do not call one
by another name. Choose a coverage factor from a stated method and applicable degrees
of freedom rather than assuming `k = 2`.

Round uncertainty before the estimate, align decimal places, retain units, and state
the uncertainty type, coverage factor or probability, and propagation method.

## Plausibility

When requested, compare against a cited scale, conservation constraint, dimensionless
group, or validated domain range. Record the characteristic length/time and model
regime. A heuristic band is a warning signal, not proof that a measurement is wrong.

## Artifact readiness

A `ready` budget requires resolved input statuses and a non-failing unit audit.
Each passing unit row names its expression and expected/observed dimensions; a
`not-applicable` row needs a reason. Analytical or hybrid propagation requires a
resolved non-failing linearization check. Drafts with missing or failed evidence
remain `conditional` or `blocked`; clearing `unresolved` cannot override nested
failures. These checks do not verify an equation, calibration record, or model.
