# Compose slides around the evidence operation

The layout catalog describes arrangements, not ready-made slide artwork. Select
an arrangement after identifying what the audience must inspect. Keep the content
faithful when adapting a figure or supplied presentation template.

## Give each region a job

A content page normally needs a title, an evidence region, a nearby explanation,
and a short source label. These are semantic regions; they do not require four
visible boxes. A useful reading path reaches the evidence before a long discussion
of it. Place the takeaway where its connection to the figure or table is clear.

The catalog's `grid` is a textual composition instruction. `visual_ratio` estimates
the fraction of usable content area allocated to the main evidence region after
title and footer space. `max_items` counts independently explained blocks or
panels, not shapes, words, plotted samples, or individual equation symbols. These
values are authoring heuristics. A low item count can still be unreadable if an
individual figure contains too much detail.

Keep a safe border around the content and an intentional gap between adjacent
blocks. Apply the global spacing tokens first, then inspect actual label and
connector extents. A catalog margin is not proof that a printer, projector, or
exporter will preserve the content.

## Match layout to a concrete reading task

| Audience operation | Layout family | Composition and evidence check |
|---|---|---|
| Orient to the talk | `title-context`, `section-route` | Identify subject and route; distinguish paper authors from the presenter |
| Understand the task | `question-evidence`, `task-pair` | Put an observed example beside the bounded question or input/output definition |
| Follow a mechanism | `method-pipeline`, `module-detail` | Label inputs, transformations, outputs, and dependencies; do not draw an arrow that implies unsupported causation |
| Interpret an equation | `equation-explanation` | Show the equation, define the symbols used here, and connect it to its role in the method |
| Compare measurements | `benchmark-evidence`, `ablation-contrast` | Align categories and scales; keep baseline, metric direction, and measured condition visible |
| Inspect visual outputs | `paired-observations`, `failure-analysis` | Preserve sample identity, crop, alignment, scale, and selection notes across panels |
| Compare prior work | `related-work-matrix` | Use explicit comparison dimensions and a source for each row; unknown entries remain unknown |
| Assess status or plan | `decision-update`, `milestone-plan` | Separate dated observations from future actions; name the dependency or decision being requested |
| Understand boundaries | `scope-boundary` | Connect each limitation to evidence or an untested condition and state its consequence |
| Learn or rehearse | `teaching-example` | Keep the prompt, known quantities, intermediate state, and answer identifiable in static form |
| Consolidate or discuss | `takeaway-sources`, `discussion-index` | Revisit supported conclusions and use stable references to evidence or backup pages |

Automatic role matching is only a starting point. If the selected layout hides
the key comparison, choose a better catalog entry or document a custom layout.
Custom visual-plan entries must still satisfy the current plan contract.

## Keep comparison geometry honest

In paired image panels, use the same field of view and physical or pixel scale
when comparison requires them. If registration or acquisition differs, label the
difference. Match crop boxes between a full frame and its enlargement. Reuse the
same range for comparable heat maps or explain a changed normalization beside
each panel. A displayed image intensity is not automatically a physical quantity.

Align table column headings, units, decimal precision, and metric direction.
Emphasize a verified comparison result with a label or marker in addition to color.
Do not remove unfavorable rows simply to produce a cleaner pattern. A deliberately
selected subset needs an explicit scope label and access to the full result.

Method diagrams should distinguish data flow, supervision, optional paths, and
evaluation-only operations through labels and connector conventions. Reuse the
same module names when enlarging a subsystem on another slide. If an equation
does not fit beside its explanation, separate derivation from interpretation
instead of shrinking both.

## Preserve consistency without repeating the same page

Use the style's typography, semantic palette, and source region throughout the
deck. Keep recurring method names, line styles, axis directions, citation keys,
and status words stable. Reserve the strongest emphasis for the current point.
The six catalog presets differ in annotation and evidence treatment as well as
color; use their rationale to select a family, not as a claim about disciplinary
taste.

For a supplied template, inspect the canvas, masters, actual layouts, placeholders,
type choices, source area, and recurrent navigation. Use those structures where
they preserve legibility. Record changes needed for long bilingual titles, charts,
equations, or meaningful reading order. Do not infer that a template is accessible
from its visual appearance.

## Adapt by recomposing

For a 4:3 version of a 16:9 talk, decide which regions stack or move to a second
page; retain the evidence needed for the claim. Do not stretch images or squeeze
all text horizontally. For bilingual pages, allocate a primary and secondary
language deliberately, and check the longest actual labels rather than a short
placeholder. Full-sentence duplication often needs a second page or notes.

Review a deck overview for repeated structure and abrupt token changes, then
inspect full pages for clipping, obscured source labels, connector crossings,
image scaling, inconsistent comparison ranges, and overloaded evidence. An
item-capacity warning asks for human inspection; it is not a diagnosis by itself.
