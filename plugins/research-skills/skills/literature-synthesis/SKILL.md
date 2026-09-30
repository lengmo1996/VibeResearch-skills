---
name: literature-synthesis
description: "Compare or organize multiple papers: related work, taxonomy, consensus and disagreement, evidence maps, positioning, literature-grounded gaps (多篇比较、综述梳理、相关工作、研究空白). Returns an evidence-backed multi-paper synthesis."
---

# Literature Synthesis

Turns a defined paper set into a comparison the reader can trace back to sources.
One paper is `$paper-deep-read`; final prose is `$writing-academic`; indexing is
`$literature-kb-build`. A complete or systematic review needs a matching protocol and
coverage (`$literature-systematic-review`); without one, describe the set honestly
instead of calling it complete.

Needed: a synthesis question or scope, and either a supplied paper set or accessible
read-only KnowledgeHub. Inclusion/exclusion criteria, time range, collections or tags,
target venue, comparison axes, a prior ledger, and a coverage target help when given.

## Modes

- `comparison` (alias `compare`): method, assumption, data, evaluation, and result comparison.
- `taxonomy`: categories and the axes that separate them.
- `gap`: evidence-backed missing settings or unresolved conflicts.
- `related-work`: evidence map and narrative plan; final prose may compose with `$writing-academic`.
- `evidence-map`: claim/source matrix and coverage map without final prose.
- `positioning`: similarities, differences, novelty risk, closest work.
- `full`: all relevant synthesis outputs.

Start with [stable identities](references/synthesis-protocol.md#stable-identities)
and only the selected row below. Load templates when building that artifact, not as
a list of sections to fill.

| Mode | Additional initial reference fragments |
|---|---|
| `comparison` (`compare`) | [axis contract](references/synthesis-protocol.md#axis-contract), [comparison](references/synthesis-protocol.md#comparison) |
| `taxonomy` | [axis contract](references/synthesis-protocol.md#axis-contract), [taxonomy](references/synthesis-protocol.md#taxonomy) |
| `gap` | [gap](references/synthesis-protocol.md#gap) |
| `evidence-map` | [evidence map](references/synthesis-protocol.md#evidence-map) |
| `related-work` | [evidence map](references/synthesis-protocol.md#evidence-map), [related work](references/synthesis-protocol.md#related-work) |
| `positioning` | [axis contract](references/synthesis-protocol.md#axis-contract), [positioning](references/synthesis-protocol.md#positioning) |
| `full` | [axis contract](references/synthesis-protocol.md#axis-contract), [derivation rules](references/synthesis-protocol.md#derivation-rules) |

In `full`, deepen only the selected derivations through their fragments. Read the
[saturation log](references/synthesis-protocol.md#saturation-log) only when retrieval
runs. Reuse accepted matrices and evidence maps instead of rebuilding them for a
downstream narrative plan.

## How to synthesize

Fix the scope first: question, source boundary, inclusion/exclusion, time range, and
the lightest mode that answers it. When retrieval is needed, split the question into
at most three retrieval questions within the shared budget, and deduplicate papers by
stable ID, DOI, and provenance. A retrieval context the user already accepted is not
rerun.

Give papers and claims stable `PAP-*` and `CLM-*` IDs, and define `AXIS-*` only for
axes the chosen deliverable actually uses. Deepen only the evidence that deliverable
needs; bring in `$paper-deep-read` as support when a source is not understood well
enough.

Comparison and positioning pass the comparability gate before any paper-by-axis
matrix, because results under different protocols are not comparable. Taxonomy
derives categories from discriminating axes. Gap tests each candidate gap against
supporting and contrary evidence. These modes do not depend on each other's sections.

For `evidence-map`, `related-work`, or a writing handoff, write the relevant `CLM-*`
rows into the [claim-evidence map](templates/claim_evidence_map.yaml) with typed
source references and a status of `candidate`, `verified`, `missing`, or
`contradictory`. Related-work also orders supported claims into a narrative plan.

In `full`, combine derivations from ledger-backed rows and counter-evidence. A
derivation the evidence does not support is reported as unresolved; an empty gap set
is a valid result.

## Evidence and RAG

RAG defaults to `required`. The exception: the user supplies a complete collection
and explicitly forbids retrieval; then use only that collection and state its
boundary. Related work, citation checks, and claims about the user's library come
from sources, not model memory.

Every matrix cell used for a conclusion carries a `CLM-*` marker or is marked
unverified. Zero hits mean the search found nothing, not that a research gap exists.
Titles and abstracts do not reveal full methods, and a small sample does not show
what a whole field does.

If required retrieval fails, stop library-wide comparison and related-work
conclusions. Return the scope, the matrix structure, and findings from supplied
sources, then what is still missing, following the degraded and zero-hit rules.

## Output

All modes include Scope and Coverage limitations. Scope names the question, mode,
paper set, and source boundary. Each mode adds the sections below; sections that
belong only to another mode are omitted.

| Mode | Additional required output sections |
|---|---|
| `comparison` (`compare`) | Comparison matrix; Evidence Ledger |
| `taxonomy` | Taxonomy; Evidence Ledger |
| `gap` | Gaps; Evidence Ledger |
| `evidence-map` | Claim-evidence map |
| `related-work` | Claim-evidence map; Narrative plan; Candidate citations |
| `positioning` | Closest-work comparison; Positioning; Evidence Ledger |
| `full` | Included papers; Comparison matrix; Taxonomy; Consensus; Disagreements; Gaps; Implications; Candidate citations; Evidence Ledger |

The Claim-evidence map is the ledger for `evidence-map` and `related-work`; do not
repeat it as another Evidence Ledger. Maps conform to the shared
[claim-evidence contract](../_shared/contracts/claim-evidence.schema.json). Other
ledgers bind the `PAP-*`/`CLM-*` IDs used to source locators and evidence status; an
accepted ledger may be referenced instead of copied.

A Search summary appears only when retrieval actually ran. Coverage limitations list
excluded or duplicate records, missing cells, and unsupported derivations that matter.

Write the prose parts per [output voice](../_shared/output-voice.md): in a Chinese
answer the section headings and status words are in Chinese, the findings come first,
and IDs stay in the matrix and ledger rather than in running text. See
[output examples](references/output-examples.md).

## Composition

Primary for multi-paper tasks, with at most two supporting Skills from
`$paper-deep-read` and `$writing-academic`. Pass the ledger, matrix, and
claim-evidence map to writing without retrieving again for the same claims.
`writing-academic` owns final prose and may weaken or mark a claim, but it
may not silently promote candidate evidence to verified.

Examples: “结合我的 Zotero 文献比较三种 condition fusion 方法”; “根据我的文献库写
related work 的证据图谱”. Not this Skill: “深读这篇论文” (`$paper-deep-read`);
“把这段 related work 压缩 20% 且不查资料” (`$writing-academic`, RAG `never`).

Load
only references linked by this `SKILL.md`.

Stop when the requested output is complete, required inputs or retrieval are
unavailable, the search budget is spent, or going further would exceed the user's
scope. When KnowledgeHub is unavailable, use the documented fallback and say so; do
not present fallback or partial results as complete. Shared rules:
[RAG](../_shared/rag-retrieval/CAPABILITY.md),
[evidence](../_shared/evidence-policy.md),
[failure](../_shared/failure-policy.md),
[citations](../_shared/citation-format.md),
[platform compatibility](../_shared/platform-compatibility.md).
