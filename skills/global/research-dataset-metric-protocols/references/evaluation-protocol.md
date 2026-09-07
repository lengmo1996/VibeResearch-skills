# Evaluation Protocol Reference

After selecting the mode, initially read only its mapped sections: split 1/2,
preprocessing 3, metric 4, leakage 5, statistics 1/6, comparability 7. Read section 8
only when the handoff/reporting decision needs it. Full work follows sections 1–8.
Load another section only for a named missing decision; the full template is not a
minimum output for a narrow mode.

## Contents

- [Identity and units](#1-freeze-identity-and-units)
- [Splits](#2-define-and-freeze-splits)
- [Preprocessing](#3-order-and-fit-preprocessing)
- [Metrics](#4-register-metrics-exactly)
- [Leakage](#5-audit-leakage-paths)
- [Statistics](#6-plan-estimation-and-statistics)
- [Comparability](#7-issue-comparability-verdicts)
- [Reporting](#8-freeze-reporting-and-handoff)

## 1. Freeze identity and units

Record dataset name, source, version/date, manifest or checksum when available,
inclusion/exclusion rules, license/access constraints, split version, and protocol
version. Names alone do not establish identity.

Separate:

- prediction unit: one model output;
- evaluation unit: one contribution to the metric;
- grouping unit: entities that must remain in one partition;
- uncertainty unit: independent sampling or resampling unit.

State the target population and whether sampling is iid, grouped, temporal,
site-specific, spatial, paired, or repeated.

## 2. Define and freeze splits

Specify train/validation/test and any external or calibration partitions. Define
membership, randomization seed/procedure, stratification, group/time/site constraints,
rare-class handling, exclusions, and freeze artifact.

Do not split lower-level samples before their shared subject, scene, sequence, patient,
document, location, or origin group. The final test set must not guide model,
hyperparameter, preprocessing, threshold, or prompt selection.

## 3. Order and fit preprocessing

List transforms in execution order. For each transform, state whether it is stateless
or learns statistics, which partition it may inspect, parameters/version, output
identity, and whether it changes labels or sampling.

Fit learned normalization, vocabulary, imputation, feature selection, augmentation
policy selection, and threshold/calibration state only on allowed training or
validation material. Cache identity must include the input split and transform
version.

## 4. Register metrics exactly

For every metric, record:

- target quantity and task relevance;
- direction and meaningful range/unit;
- formula or authoritative implementation/version;
- parameters, thresholds, calibration, and class/label handling;
- per-sample/group aggregation, macro/micro/weighted choice, and weighting;
- missing predictions, undefined denominators, ties, exclusions, and precision;
- uncertainty and reporting companion metrics.

Identical names can conceal different implementations or aggregation. Proxy,
perceptual, task, calibration, fairness, cost, and safety metrics answer different
questions and should not be substituted silently.

## 5. Audit leakage paths

Check:

- exact and near duplicates across partitions;
- shared subjects, scenes, sequences, sites, sources, or time windows;
- target/label-derived features and future information;
- global preprocessing statistics, vocabularies, imputation, or feature selection;
- augmentation or synthetic samples derived from held-out material;
- pretrained data overlap or external benchmark contamination when material;
- hyperparameter, threshold, prompt, ensemble, or checkpoint selection on test data;
- repeated test-set use and manual inspection feeding back into development.

For each path, define a detection check, prevention, residual risk, and affected claim.

## 6. Plan estimation and statistics

Define the estimand before selecting a test. Record independent/pairing unit,
repeated-measure structure, resampling unit, interval method, test/model assumptions,
effect size, multiple-comparison family, missingness/exclusions, and minimum
reporting.

Do not invent power, sample size, significance thresholds, or distributional
assumptions. If inputs are insufficient, specify the decision needed. Statistical
significance does not repair biased sampling, leakage, or protocol mismatch.

## 7. Issue comparability verdicts

Compare dataset identity, partitions, population, preprocessing, information access,
metric implementation, aggregation, sampling unit, uncertainty, tuning budget, and
reporting.

- `comparable`: no material mismatch for the stated claim;
- `conditional`: comparison is allowed only with explicit caveats or restricted claim;
- `non-comparable`: a material mismatch prevents the proposed ranking or conclusion.

Never numerically convert or merge results unless the transformation is defined and
valid for the underlying sufficient statistics.

## 8. Freeze reporting and handoff

Bind tables and result artifacts to dataset, split, preprocessing, metric, statistics,
and code/config identifiers. Report estimates with uncertainty, sample/group counts,
exclusions, failed runs, protocol deviations, and applicable caveats.

Version protocol changes after evaluation begins. Handoff the frozen contract to
experiment/configuration Skills and the original estimand, direction, pairing, and
allowed comparisons to `$research-result-analysis`.
