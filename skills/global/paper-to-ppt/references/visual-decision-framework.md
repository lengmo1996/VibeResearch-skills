# Choose a visual system for an academic talk

Use this guide when the content plan reaches visual-system selection. The input is
a supported story and a delivery context. The output is a documented set of design
choices, followed by a valid visual plan. It is not a substitute for checking the
paper, experiment record, or final rendered slides.

## Start with the audience's task

Record the deck type, audience knowledge, duration, language, output formats,
canvas ratio, supplied template, and important viewing constraints. Unknown venue
or font availability remains unknown. A planned experiment remains planned in the
title, figure labels, notes, and conclusion.

| Deck type | Question the audience should be able to answer | Evidence to put in view | Useful starting direction |
|---|---|---|---|
| `paper-talk` / 论文报告 | What does this paper establish, and under what conditions? | Problem example, method diagram, supported comparison, limitation | `precise-blue`; `biomedical-teal` for study and cohort detail |
| `lab-meeting` / 组会 | What observation or decision deserves discussion? | Recent output, counterexample, diagnosis, explicit open question | `precise-blue`, using compact evidence and discussion pages |
| `project-update` / 进度汇报 | What changed, what is blocked, and what happens next? | Dated outputs, dependency state, current result, next test | `technical-indigo`, with separate observed and planned states |
| `defense` / 答辩 | How do the contributions support the thesis claim? | Contribution-to-evidence map, controlled comparisons, scope limits | `defense-evidence`, with stable chapter and evidence references |
| `conference` / 会议报告 | What should a mixed audience remember and inspect later? | One readable central result, a short method path, source link | `conference-focus`, with detail available in backup slides |
| `course` / 教学 | Can the learner explain or apply the concept? | Worked example, intermediate state, learner prompt, solution | `teaching-sequence`, with steps that also work in a handout |

These are authoring choices for this catalog. A discipline does not require a
particular color, and a score from the recommender is not a measure of quality.
User instructions and a usable supplied template take priority over the starting
directions.

## Turn the story into visible evidence

For every slide, write the audience question before choosing a layout. Then record
the supported claim or navigation purpose, its source, the evidence that must be
legible, and any uncertainty or missing asset. Prefer a factual title such as
“The error concentrates at object boundaries” only when the shown evidence
supports it. Otherwise use a bounded purpose such as “Boundary-error analysis
to run next.” Neither is an experimental result merely because it is a title.

Match the layout to the operation the audience performs: trace a method, compare
conditions, inspect aligned examples, read an equation, or decide a next action.
A source trace belongs with the visual it identifies. Summary claims should point
back to evidence slides; section and discussion pages should identify their
navigation purpose instead of displaying ornamental evidence.

Keep one primary comparison or explanation in the foreground. If a source figure
requires unreadable labels at presentation size, rebuild a source-faithful subset
from available data, use a labeled enlargement, or move the full figure to backup.
Record omitted panels and preprocessing. Never reconstruct missing measurements.

## Compare candidates with the same content

Reuse a supplied template or approved direction. Otherwise choose a suitable
conservative direction and proceed, recording material assumptions. Compare
alternatives only when requested or when a consequential unresolved choice needs
user input.

When useful, the recommender supplies two to four candidates using deck type,
domain, and tone. Its implementation does not assess the actual audience, viewing
distance, template, or rendered typography; those require author judgment. It also treats catalog
order as a tie-breaker. Record any override of the top candidate and the constraint
that motivated it.

When comparing alternatives, use the same representative content in previews:
a difficult evidence slide, a method or explanation slide, and a navigation or
summary slide are useful choices.
This three-view selection is a local review heuristic, not a required slide count.
Compare evidence size, annotation placement, bilingual line breaks, and reading
order. Merely recoloring identical pages does not demonstrate distinct treatments.

Request preview selection only when the user asks for alternatives or an unresolved
consequential choice prevents completion. Render the representative previews before
requesting a selection; ordinary deck work needs no separate preview waiver.

## Freeze a small set of decisions

Record the selected style ID, canvas, semantic colors, font fallbacks, type sizes,
safe area, source-label position, recurring layout families, and motion/export
policy. Reuse identities across the deck: a method keeps its label and marker;
a condition keeps its legend; a chapter keeps its navigation location. Change the
composition when the audience task changes, while retaining these shared tokens.

The numeric sizes, margins, item capacities, and visual-area shares in the catalogs
are project heuristics. They help produce consistent initial plans and satisfy the
current validator. They do not certify readability or accessibility. Adapt them
upward when text, translation, equations, viewing conditions, or a template need
more room; split content when space is insufficient.

For Chinese or bilingual delivery, decide which language carries the spoken story.
Translate claims and necessary labels consistently, retain source terminology and
units, and avoid doubling every paragraph. Use notes or a separate handout for
full translations if the visible evidence would otherwise shrink.

## Validate at the boundary that actually exists

Run `scripts/recommend_visual_system.py` if its deterministic selection is useful,
then `scripts/validate_visual_plan.py` on the selected plan. Check the JSON schema
when producing or integrating machine-readable output. Supply an actual positive
`duration_minutes` for schema validation: the existing recommender emits `null`
when it is omitted, while the schema declares that field numeric.

A passing plan checks only its declared fields and limited numeric rules. It does
not inspect paper claims, font installation, table labels, PDF tags, captions,
animation, or slide geometry. Render the requested artifact and inspect full slides
and a deck overview. Inspect the requested static PDF separately. Report missing
checks by output format rather than assigning a general “accessible” verdict.

Related guides: [layout and style](layout-and-style-rules.md),
[type, color, and charts](typography-color-chart-rules.md), and
[interaction, adaptation, and accessibility](interaction-motion-responsive-accessibility.md).
