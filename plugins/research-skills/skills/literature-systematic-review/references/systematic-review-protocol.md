# Systematic review protocol

Load for every mode. Read only the section needed by the selected mode.

## Protocol fields

Freeze before result-dependent decisions:

- review question and rationale;
- population/problem, intervention/exposure, comparator, outcomes, study designs,
  and context as applicable;
- source systems, date range, languages, grey-literature policy, and query strings;
- deduplication identifiers and conflict handling;
- title/abstract and full-text criteria;
- screener count, isolation, reconciliation, and amendment policy;
- outcome definitions, extraction fields, bias framework, certainty framework, and
  synthesis plan.

Record every amendment with date, reason, affected decisions, and whether it was made
before or after observing results.

## Search accounting

One `SEARCH-*` batch binds one source, exact query hash, execution time, count,
pagination/cap state, completion status, and evidence reference. A source with
multiple queries has multiple batches. Failed or truncated batches remain visible.

## Screening

Use controlled decisions: `include`, `exclude`, `unclear`, or `not-assessed`.
Full-text exclusions require one primary controlled reason; optional notes may add
detail. Preserve both decisions when reviewers disagree until reconciliation.

A full-text assessment requires a recorded title/abstract `include`. A title/abstract
`exclude` legitimately leaves full text `not-assessed`. An included title/abstract
whose full text is still `not-assessed` is pending work and prevents `complete`;
preserve it in a `partial` ledger instead of omitting the candidate.

## Appraisal

Choose a framework appropriate to the design. Each domain judgment is `low`,
`some-concerns`, `high`, or `unclear` with a source locator and rationale. Certainty
is outcome-specific and records every downgrade/upgrade reason.

## Synthesis gate

Qualitative synthesis still requires protocol-compatible grouping. Meta-analysis
requires compatible effect definition, direction, analysis unit, population,
comparator, and sufficient uncertainty inputs. Statistical heterogeneity cannot
repair conceptual incompatibility.

When `flow.included_quantitative` is nonzero, explicitly list the selected, unique
`STUDY-*` IDs in `meta_analysis_gate.quantitative_study_ids`. The list length must
match that count; every selected study must be included after full-text assessment
and have `effect_data_status: available`. Incompatible or incomplete studies may
remain in the qualitative synthesis but cannot appear in this quantitative subset.
The IDs bind the declared subset; they do not independently establish numerical or
conceptual compatibility, which still requires the source-backed gate above.

Existing ledgers with zero quantitative studies may omit this list; use `[]` in new
ledgers. Existing positive-count ledgers must identify their actual selected studies
before validation; the checker never guesses or silently backfills that selection.
