# Literature Synthesis Protocol

## Stable identities

- `PAP-*`: one deduplicated paper identity with DOI, repository/library ID, or a
  normalized title plus provenance.
- `AXIS-*`: one operational comparison dimension.
- `CLM-*`: one source-bounded claim or observation.
- `GAP-*`: one bounded unresolved condition derived from claims and counter-evidence.

Never merge papers solely because titles look similar, and never split versions
without recording their relationship.

Use only IDs needed by the selected deliverable. Every conclusion links to a
`CLM-*` row with `PAP-*` identity, source locator, and evidence status. Reuse accepted
IDs and ledgers; a compact comparison does not need an independent taxonomy report.

## Axis contract

Before filling a matrix, define each axis, allowed values, evidence needed, and
conditions that make entries incomparable. Separate result values by protocol group
when datasets, splits, preprocessing, supervision, metric definitions, or evaluation
settings differ materially.

## Comparison

Build only the requested paper-by-axis matrix. Bind each conclusion-bearing cell to
claims or mark it unverified. Include protocol groups, relevant caveats, and source
locators through the ledger. An incompatible pair may be compared descriptively,
but its scores cannot support a ranked performance conclusion. Do not add taxonomy,
gap, or narrative-plan sections unless separately requested.

## Taxonomy

Define each category by observable `AXIS-*` criteria and cite member-paper evidence.
Permit mixed or unclassified papers when evidence does not support an exclusive
assignment. Record overlaps and counterexamples. The category table plus its ledger
is sufficient; unrelated performance matrices and research gaps are not required.

## Gap

For each `GAP-*`, state its paper-set boundary, supporting claims, counter-evidence,
why the condition remains unresolved, and the source or result that would falsify
it. Distinguish missing evidence from a supported coverage, conflict, assumption,
evaluation, or mechanism gap. Zero hits and empty cells do not establish a gap.
A valid report may find no supported gaps. Reuse any relevant accepted matrix rows;
do not construct a field-wide taxonomy as a prerequisite.

## Evidence map

Use the shared claim-evidence schema and the `claim_evidence_map.yaml` template.
Each relevant `CLM-*` has typed evidence references and an explicit candidate,
verified, missing, or contradictory status. Preserve contradicting sources and
unresolved references. The map is the Evidence Ledger for this mode; supply scope
and coverage limits without repeating it in a second table or adding final prose.

## Related work

Start from an accepted claim-evidence map or construct the missing rows. Order
supported claims into a narrative plan with paragraph roles, claim IDs, transitions,
and candidate citations. Keep unsupported links visibly unresolved. The plan and
map are the deliverable; `writing-academic` owns final prose. Do not require a new
taxonomy or gap report when the narrative does not use those claims.

## Positioning

Require a target method or claim and compare it with the closest evidenced work on
the same operational axes. Report similarities, differences, novelty risk, and
limits of the closest-work coverage. Distinguish an observed difference from
verified novelty and a proposed advantage from a measured result. A closest-work
matrix and calibrated positioning with an Evidence Ledger are sufficient.

## Derivation rules

- Taxonomy: categories require a discriminating `AXIS-*`, not only descriptive labels.
- Consensus: several compatible `CLM-*` entries support the same bounded statement.
- Disagreement: conflicting claims preserve protocol and scope differences.
- Gap: an unresolved coverage, conflict, assumption, evaluation, or mechanism
  condition with supporting claims, counter-evidence, and a falsification condition.
- Positioning: similarity and difference claims cite the same axes used in the matrix.

Zero retrieval hits and an empty matrix cell are missing evidence, not gaps.

## Saturation log

For each retrieval round record:

| Round | Question | New papers | New axis values | Changed claims | Repeated only? |
|---|---|---|---|---|---|

Stop for saturation only when another in-scope round adds no decision-relevant axis
value or changes no synthesis claim. This is bounded saturation, never proof of field
completeness.
