# Statistical Validity and Reproducibility Report

## Scope and data sufficiency

- Modes: statistical-audit, reproducibility-check
- Claim/experiment IDs: CLM-001 / EXP-001
- Protocol/metric IDs: PROT-001 / MET-001
- Analysis unit: one independently sampled evaluation unit
- Planned or post-hoc: planned
- Runs expected/observed/missing/failed: 3 / 3 / 0 / 0
- Seed coverage: seeds 1, 2, and 3
- Raw inputs available: aggregate metrics and per-run summaries
- Original decision rule: supplied frozen criterion

## Assumption checks

| Check ID | Claim/metric IDs | Assumption or risk | Evidence | Status | Impact |
|---|---|---|---|---|---|
| STAT-001 | CLM-001 / MET-001 | analysis-unit independence | protocol artifact | unknown | limits inferential wording |

## Effect and uncertainty

| Finding ID | Comparison | Effect estimate | Uncertainty | Denominator | Aggregation | Limitation |
|---|---|---|---|---|---|---|
| FIND-001 | method vs baseline | supplied estimate | supplied interval or unavailable | supplied count | supplied rule | state limitation |

## Multiplicity and selection

- Hypotheses/metrics/datasets inspected: list supplied coverage
- Correction or hierarchical rule: supplied rule or not provided
- Best-run/seed/checkpoint selection: none observed or describe evidence
- Exclusions and subgroup analyses: list planned and post-hoc exclusions
- Selective-reporting risk: unknown until complete run registry is supplied

## Reproducibility coverage

| Run group | Config/code/data identity | Seeds planned/observed | Independent repeats | Missing/failed/excluded | Artifact refs | Status |
|---|---|---|---|---|---|---|
| RUN-GRP-001 | supplied frozen identities | 3 / 3 | not provided | 0 / 0 / 0 | RUN-001..003 | partial |

## Verdicts

| Claim ID | Statistical verdict | Reproducibility verdict | Strongest allowed wording | Exact blocker |
|---|---|---|---|---|
| CLM-001 | partial | partial | bounded descriptive support only | independent repeat unavailable |

## Risks and next checks

| Priority | Risk or unknown | Discriminating check | Required input | Decision rule |
|---|---|---|---|---|
| P1 | independent reproducibility unknown | repeat frozen protocol independently | complete run artifacts | supplied criterion |
