---
name: literature-synthesis
description: "Use when comparing or organizing multiple academic papers, including related work, taxonomies, consensus, disagreements, evidence maps, or literature-grounded gaps. Produces an evidence-backed multi-paper synthesis. Do not use for one-paper reading or unsupported prose drafting."
---

# Literature Synthesis

## Name and purpose

Use `literature-synthesis` to turn a defined paper set into an evidence-traceable comparison. Read [RAG](../../_shared/rag-retrieval/CAPABILITY.md), [evidence](../../_shared/evidence-policy.md), [failure](../../_shared/failure-policy.md), [outputs](../../_shared/academic-output-contracts.md), and [citations](../../_shared/citation-format.md).

## Use when

Compare papers, build a taxonomy, identify consensus/disagreement, find literature-grounded gaps, position a method, prepare related work, or analyze the user's library.

## Do not use when

Use `paper-deep-read` for one paper, `writing-academic` for final prose, and `literature-kb-build` for indexing. Do not claim a complete or systematic review without a matching protocol and coverage.

## Required and optional inputs

Required: synthesis question/scope and either a supplied paper set or accessible read-only KnowledgeHub. Optional: inclusion/exclusion criteria, time range, collections/tags, target venue, comparison axes, prior ledger, and coverage target.

## Workflow

1. Define scope, question, source boundary, inclusion/exclusion, time range, and the
   lightest sufficient mode. Use only its output sections and reference fragments.
2. When retrieval is required, decompose into at most three retrieval questions and
   retrieve with the shared budget. Deduplicate all used papers by stable IDs,
   DOI, and provenance; do not rerun a supplied accepted retrieval context.
3. Assign stable `PAP-*` and `CLM-*` IDs. Define `AXIS-*` only for axes the selected
   comparison, taxonomy, gap, or positioning actually uses.
4. Deepen only the evidence needed for the selected deliverable; use
   `paper-deep-read` as a supporting Skill when source understanding is insufficient.
5. For comparison and positioning, apply the comparability gate before making a
   paper-by-axis matrix. For taxonomy, derive categories from discriminating axes.
   For gap, test bounded candidate gaps against supporting and contrary evidence.
   These modes do not require each other's final sections.
6. For `evidence-map`, `related-work`, or a downstream writing handoff, materialize
   relevant `CLM-*` rows with the [claim-evidence map](templates/claim_evidence_map.yaml),
   using typed source references and `candidate`, `verified`, `missing`, or
   `contradictory` evidence status. Related-work additionally orders supported
   claims into a narrative plan; final prose belongs to `writing-academic`.
7. In `full`, combine the relevant derivations from ledger-backed rows and
   counter-evidence. Report unsupported derivations as unresolved rather than
   manufacturing a taxonomy, consensus, or gap.
8. Record coverage and unresolved evidence. Only when retrieval ran, report its
   search summary and observed changes from each additional round.

## Modes

- `compare`: compatibility alias for `comparison`.
- `comparison`: method/assumption/data/evaluation/result comparison.
- `taxonomy`: categories and discriminating axes.
- `gap`: evidence-backed missing settings or unresolved conflicts.
- `related-work`: evidence map and narrative plan; final prose may compose with `writing-academic`.
- `evidence-map`: claim/source matrix and coverage map without final prose.
- `positioning`: similarities, differences, novelty risk, closest work.
- `full`: all relevant synthesis outputs.

## Mode-specific reference loading

Start with [stable identities](references/synthesis-protocol.md#stable-identities)
and only the selected row below. Load templates when constructing that artifact,
not as an instruction to fill every section in a report.

| Mode | Additional initial reference fragments |
|---|---|
| `comparison` (`compare`) | [axis contract](references/synthesis-protocol.md#axis-contract), [comparison](references/synthesis-protocol.md#comparison) |
| `taxonomy` | [axis contract](references/synthesis-protocol.md#axis-contract), [taxonomy](references/synthesis-protocol.md#taxonomy) |
| `gap` | [gap](references/synthesis-protocol.md#gap) |
| `evidence-map` | [evidence map](references/synthesis-protocol.md#evidence-map) |
| `related-work` | [evidence map](references/synthesis-protocol.md#evidence-map), [related work](references/synthesis-protocol.md#related-work) |
| `positioning` | [axis contract](references/synthesis-protocol.md#axis-contract), [positioning](references/synthesis-protocol.md#positioning) |
| `full` | [axis contract](references/synthesis-protocol.md#axis-contract), [derivation rules](references/synthesis-protocol.md#derivation-rules) |

During `full`, deepen only the selected derivations through their fragments above.
Read [saturation log](references/synthesis-protocol.md#saturation-log) only when
retrieval runs. Reuse accepted matrices and evidence maps instead of reconstructing
them for a downstream narrative plan.

## RAG policy

Default `required`. Exception: the user supplies a complete collection and explicitly forbids retrieval; then use only that collection and describe its boundary. Related work, citation verification, and claims about the user's library never rely on model memory.

## Evidence policy

Every matrix cell used for a conclusion needs a `CLM-*` source marker or an explicit
`unverified`. Zero hits are not a research gap. Do not infer full methods from
titles/abstracts, compare results across incompatible protocols, or use small samples
to claim field-wide completeness.

## Output contract

All modes require **Scope** and **Coverage limitations**. Scope names the question,
selected mode, paper set, and source boundary. The table lists the additional
required sections; omit sections belonging only to another mode.

| Mode | Additional required output sections |
|---|---|
| `comparison` (`compare`) | Comparison matrix; Evidence Ledger |
| `taxonomy` | Taxonomy; Evidence Ledger |
| `gap` | Gaps; Evidence Ledger |
| `evidence-map` | Claim-evidence map |
| `related-work` | Claim-evidence map; Narrative plan; Candidate citations |
| `positioning` | Closest-work comparison; Positioning; Evidence Ledger |
| `full` | Included papers; Comparison matrix; Taxonomy; Consensus; Disagreements; Gaps; Implications; Candidate citations; Evidence Ledger |

The Claim-evidence map is the ledger for `evidence-map` and `related-work`, so do not
duplicate it in another Evidence Ledger. Output or reference a map conforming to the
shared [claim-evidence contract](../../_shared/contracts/claim-evidence.schema.json)
for these modes and any downstream writing handoff. Every other ledger binds the
used `PAP-*`/`CLM-*` IDs to source locators and evidence status; a supplied accepted
ledger may be referenced rather than copied.

**Search summary** is conditional on actual retrieval; otherwise Scope states the
supplied-source boundary. Put relevant excluded/duplicate records, missing cells,
and unsupported full-mode derivations in Coverage limitations. An empty candidate
gap set is a valid result; do not invent gaps to populate the Gaps section.

## Failure behavior

If required retrieval fails, stop library-wide comparison and related-work conclusions. Return scope/matrix structure and supplied-source findings only, followed by missing work. Follow degraded and zero-hit rules exactly.

## Composition rules

Primary for multi-paper tasks. Supporting Skills: `paper-deep-read` and/or
`writing-academic`, maximum two. Pass the ledger, matrix, and claim-evidence map to
writing; do not retrieve again for the same claims. `writing-academic` owns final
prose and may weaken or mark a claim, but may not silently promote candidate evidence
to verified.

## Examples

- “结合我的 Zotero 文献比较三种 condition fusion 方法。”
- “根据我的文献库写 related work 的证据图谱。”

## Non-examples

- “深读这篇论文。” → `paper-deep-read`.
- “把这段 related work 压缩 20% 且不查资料。” → `writing-academic`, RAG `never`.

## Validation checklist

- [ ] Scope and inclusion/exclusion are explicit.
- [ ] RAG is required unless the exception is documented.
- [ ] Deduplication and coverage limits are reported.
- [ ] Only selected-mode sections are required; search summaries describe actual retrieval.
- [ ] Matrix claims and other synthesis conclusions link to evidence IDs.
- [ ] Downstream claim rows use stable `CLM-*` IDs and typed evidence references.
- [ ] Candidate and contradictory evidence remain distinguishable from verified support.
- [ ] Paper identities and any comparison axes used have stable IDs and explicit definitions.
- [ ] Incompatible protocols are separated before result comparison.
- [ ] Gaps are not inferred from zero hits.
- [ ] Each reported gap includes counter-evidence and a falsification condition.
- [ ] When retrieval ran, saturation is reported as observed evidence change, not intuition.
- [ ] No completeness claim exceeds the search protocol.

Load
only references linked by this `SKILL.md`.

## Platform compatibility, failure, and stop contract

1. Validate the stated inputs before work. Mark missing material as `not provided / unclear`; do not infer machine access, credentials, prior results, or private data.
2. Check declared external tools once before depending on them. Follow [platform compatibility](../../_shared/platform-compatibility.md) and the existing side-effect/approval rules.
3. If this Skill declares optional KnowledgeHub MCP and it is unavailable, continue only through the documented user-file, link, context, or authoritative-web fallback, state that fallback, and do not retry repeatedly.
4. If the selected mode explicitly requires private-library or citation evidence, stop only the retrieval-dependent claims, identify the missing `knowledge-hub` capability, and keep independent source-bounded work separate.
5. Produce only the output contract defined by this Skill. Do not present a partial, fallback, simulated, or unverified result as complete or as MCP-derived.
6. Stop when the requested output and validation criteria are satisfied, required inputs or authorization are unavailable, the evidence/search budget is exhausted, or proceeding would exceed the user's scope.
