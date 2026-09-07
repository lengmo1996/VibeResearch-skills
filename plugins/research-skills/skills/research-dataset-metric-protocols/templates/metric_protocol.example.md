# Evaluation Protocol

## Scope and identities

- Mode: metric
- Task definition: synthetic example of a classification metric contract; no measured results.
- Protocol ID/version: PROT-EXAMPLE-001
- Dataset/split identity: unresolved; this example cannot establish comparability.

## Metric registry

| Metric ID | Target quantity | Direction | Unit/range | Implementation/version | Parameters | Aggregation/weighting | Threshold/missing/tie handling | Reporting precision | Validity conditions |
|---|---|---|---|---|---|---|---|---|---|
| MET-001 | correct predictions divided by labeled predictions | higher | proportion in [0, 1] | supplied fixture definition v1; implementation unresolved | fixed label mapping | sample-weighted mean | report missing predictions; fixed tie rule required | report numerator and denominator | split, label mapping, and missingness rules must be frozen before comparison |

## Unresolved decisions and blocked verdicts

Dataset identity and implementation are unresolved; no comparability verdict is issued.

## Handoff

Bind PROT-EXAMPLE-001 and MET-001 to the supplied dataset and implementation before use.
