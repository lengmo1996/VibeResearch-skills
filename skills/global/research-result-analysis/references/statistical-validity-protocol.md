# Statistical validity and reproducibility protocol

Load only for `statistical-audit` or `reproducibility-check`.

## Establish data sufficiency

Bind the analysis unit, planned comparison, expected and observed runs, exclusions,
metric direction, pairing/grouping, raw or aggregate inputs, and original decision
rule. Mark unavailable inputs explicitly. Do not reconstruct variance, sample size,
or seed coverage from a plot.

## Audit statistical validity

Check only what supplied inputs permit:

- analysis-unit and independence assumptions;
- paired/unpaired and repeated-measure structure;
- effect estimate, uncertainty interval, denominator, and aggregation;
- distributional/robustness assumptions and outlier policy;
- multiplicity across metrics, datasets, checkpoints, seeds, and hypotheses;
- planned versus post-hoc thresholds, exclusions, and subgroup analyses;
- best-run, best-seed, best-checkpoint, or selective-reporting risk.

Use `pass`, `fail`, `unknown`, or `not-applicable` for each assumption/check. A
missing assumption test is `unknown`, not `pass`.

## Audit reproducibility

Compare the frozen configuration identity, code/data/checkpoint references, planned
seed/run matrix, observed artifacts, failed/missing runs, and agreement across
repeats. Distinguish:

- repeatability in the same environment;
- reproducibility under a separately described environment or implementation;
- robustness across seeds, data slices, or reasonable protocol variation.

Do not claim reproducibility from one successful rerun.

## Assign verdicts

Use:

- `supported`: supplied evidence satisfies the bounded criterion;
- `partial`: important coverage or assumptions remain limited;
- `contradicted`: reliable supplied evidence opposes the criterion;
- `inconclusive`: available evidence conflicts or cannot separate outcomes;
- `not-evaluable`: required inputs are absent.

Record the strongest allowed wording and exact blocker. Preserve the main
claim-analysis vocabulary in the ordinary result report; these verdicts describe the
statistical/reproducibility gate.
