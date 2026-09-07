# Experiment Design Protocol

After selecting the mode, initially read only its mapped sections: baseline 3,
control 2, ablation 4/5/6, schedule 7. Read section 1 only when the supplied hypothesis
is insufficient, and section 8 only for an unresolved handoff. Full work follows
sections 1–8. The full template is not a minimum output for a narrow mode.

## Contents

- [Hypothesis contract](#1-write-the-hypothesis-contract)
- [Variables and confounds](#2-register-variables-controls-and-confounds)
- [Baseline fairness](#3-build-the-baseline-fairness-envelope)
- [Experiment records](#4-construct-experiment-records)
- [Ablations](#5-design-ablations)
- [Outcome branches](#6-precommit-outcome-branches)
- [Schedule](#7-schedule-by-information-and-dependency)
- [Handoff](#8-define-artifacts-and-handoff)

## 1. Write the hypothesis contract

State:

- target hypothesis and competing explanation or null;
- unit of analysis and target system;
- observable evidence that distinguishes the explanations;
- scientific decision the experiment informs;
- claims the experiment cannot support.

Do not phrase success as the expected conclusion. A reviewer request is a motivation,
not automatically a valid experimental hypothesis.

## 2. Register variables, controls, and confounds

Classify each variable as manipulated, measured, controlled, stratification,
nuisance, or derived. Record protocol invariants and plausible confounds.

Change one causal factor at a time unless the plan explicitly uses a factorial design.
For interactions, include the relevant main effects and state what interaction
contrast answers the hypothesis. Do not describe correlated settings as independent
ablations.

Use positive controls to show the pipeline can detect a known signal and negative
controls to expose leakage, shortcut learning, or implementation artifacts when
relevant.

## 3. Build the baseline fairness envelope

Choose baselines by the explanations they test, not only popularity:

- task or domain standard;
- strongest comparable method under the same information;
- simple lower-complexity reference;
- component-removed or matched-capacity control;
- prior method directly implicated by the claim.

Compare data access, splits, preprocessing, augmentation, initialization, tuning
opportunity, training budget, compute accounting, post-processing, and evaluation.
Document exceptions and restrict the claim when parity is impossible. Historical
reported numbers are not interchangeable with reruns.

## 4. Construct experiment records

Give every run a stable `EXP-###` ID and bind it to:

- one or more upstream `CLM-*` IDs, or an explicit `exploratory` marker;
- one target hypothesis;
- one changed variable or declared interaction;
- fixed controls and protocol reference;
- baseline or comparator;
- decision evidence and artifact;
- resource estimate and prerequisites;
- result-independent acceptance or stop criterion.

The record must remain interpretable if the result is null or adverse.

## 5. Design ablations

Distinguish:

- necessity: remove or disable one component;
- sufficiency: add the component to a controlled base;
- interaction: test whether components depend on each other;
- sensitivity: vary a meaningful range without cherry-picking;
- mechanism: measure an intermediate quantity tied to the explanation.

Capacity- or compute-changing ablations require matched controls or a bounded claim.

## 6. Precommit outcome branches

For each central hypothesis, define:

- `supportive`: evidence consistent with the target explanation;
- `null`: no meaningful distinction under the planned sensitivity;
- `adverse`: evidence favors a competing explanation or harms another criterion;
- `inconclusive`: protocol failure, insufficient precision, or conflicting evidence.

Map every branch to a decision and follow-up. Do not assign invented effect sizes,
thresholds, significance, or success probabilities. Delegate exact metric and
statistical definitions to `$research-dataset-metric-protocols` when primary.

## 7. Schedule by information and dependency

Run cheap validity pilots before expensive sweeps. Order protocol validation,
baseline establishment, main comparison, ablations, robustness, and optional
extensions by dependency. Separate must-run, conditional, and optional work.

Use stop/go gates to prevent spending the remaining budget on an invalid pipeline or
an already-disproved premise. A gate stops work; it does not rewrite the hypothesis
after seeing results.

## 8. Define artifacts and handoff

Require stable experiment IDs in configs, logs, tables, checkpoints, and analysis
outputs. Record code/config revision, environment, dataset/split identity, seeds,
resource use, metrics, failures, and exclusions.

Handoff the frozen matrix and protocol to configuration/implementation Skills. Handoff
completed artifacts plus original decision rules to `$research-result-analysis`.
Protocol changes after results begin must be versioned and disclosed rather than
silently replacing the original plan.
