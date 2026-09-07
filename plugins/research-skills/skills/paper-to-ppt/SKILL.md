---
name: paper-to-ppt
description: "Use when verified paper or research content must become an academic presentation, speaker-ready deck, template adaptation, visual system, or visual audit. Produces a source-faithful story arc, slide plan, visual plan, deck artifact, notes, or QA report. Do not use for commercial pitches, manuscript prose, deep reading without a presentation request, or visual-style mining alone."
---

# Paper to PPT

## Purpose

Convert verified research evidence into a time-bounded academic talk. Content
fidelity, visual-plan validity, and rendered-artifact quality are separate gates; a
pass at one gate never proves the others.

`paper-to-ppt` owns the final slide narrative and visual system. It may receive source
evidence from `$paper-deep-read`, a pattern handoff from
`$visual-expression-mining`, or verified chart artifacts from
`$visual-research-artifact-generation`.

## Inputs

Required: paper, reading report, or verified research results; audience; presentation
duration. Optional: mode/output format, venue, language, slide budget, aspect ratio,
template, style references, verified figures/data, notes, accessibility, projector,
export constraints, and a presentation handoff.

Mark unavailable sources, templates, fonts, assets, editors, or renderers
`not provided / not checked`. Do not imply they were inspected.

## Modes

| Mode | Primary output | Required gates |
|---|---|---|
| `outline` | story arc and slide-by-slide content plan | narrative |
| `visual-system` | ranked candidates and selected visual plan | narrative, visual plan |
| `deck` | requested deck artifact | all three |
| `speaker-ready` | deck, notes, timing, delivery prompts | all three plus timing rehearsal |
| `template-adaptation` | adapted deck and documented exceptions | all three plus template audit |
| `visual-audit` | findings and manual checks; no edit unless requested | applicable plan/artifact checks |

## Resource loading by mode

After this Skill and the applicable shared safety/evidence contracts, start with only
the following resources. Reuse supplied plans; initial resources are not instructions
to recreate an already validated artifact.

| Mode | Initial resources | Add only when needed |
|---|---|---|
| `outline` | [content plan](assets/templates/deck-content-plan.md) | none of the visual-system guides or catalogs; unresolved visuals remain handoff needs |
| `visual-system` | [decision framework](references/visual-decision-framework.md) and [design brief](assets/templates/visual-design-brief.md) | content plan if narrative is missing; one relevant rule guide at a time |
| `deck` | content plan | at Gate 2, decision framework and design brief; at Gate 3, [visual QA](assets/templates/visual-qa-checklist.md) |
| `speaker-ready` | content plan | existing-deck QA and timing/notes needs; visual-system resources only for missing or changed design decisions |
| `template-adaptation` | visual QA and [layout/style rules](references/layout-and-style-rules.md) | supplied template inspection first; content plan or visual-system resources only for missing/changed decisions |
| `visual-audit` | visual QA | layout/style for geometry/hierarchy; [type/color/chart](references/typography-color-chart-rules.md) for those checks; [interaction/accessibility](references/interaction-motion-responsive-accessibility.md) for relevant output behavior |

`visual-audit` starts from the supplied deck/plan and QA scope; it does not run the
narrative-generation or candidate-selection workflow. Missing source evidence becomes
an unchecked item, not a reason to invent a new story. It does not load the style,
layout, and chart catalogs or run the recommender unless a later redesign is requested.

Catalogs are script inputs, not mandatory model context. For a concrete catalog-ID
decision, inspect only the relevant catalog/entries. Load the visual-plan schema when
authoring or diagnosing that plan, and SPEC interface details only when a script
interface is needed. Artifact modes still perform every applicable content, plan,
render, and visual gate; staged reading never waives a gate or authorizes a write.

## Workflow

### Gate 1: narrative and evidence

1. Bind audience, venue, duration, language, slide budget, output, template, and
   accessibility/export constraints.
2. Extract only supported problem, claim, method, result, limitation, and source
   traces. Use [deck content plan](assets/templates/deck-content-plan.md).
3. Build a talk-specific story rather than copying paper section order. Allocate time
   and slides; give each slide one claim or navigation purpose.
4. Map each claim to evidence and uncertainty. Block missing figures/data instead of
   inventing them.

`outline` stops after this gate when the content plan passes.

### Gate 2: visual plan

5. When this mode reaches visual-system work, read
   [visual decision framework](references/visual-decision-framework.md), then
   load only the additional reference needed:
   [layout/style](references/layout-and-style-rules.md) for composition;
   [type/color/chart](references/typography-color-chart-rules.md) for quantitative
   evidence; [interaction/accessibility](references/interaction-motion-responsive-accessibility.md)
   for motion, links, export, adaptation, or accessibility.
6. Build the visual-design brief. Use `scripts/recommend_visual_system.py` when
   deterministic candidates help, and keep candidate preview content identical.
7. Ask for a direction before a full deck unless the user waived preview or requested
   uninterrupted execution. Under a waiver, choose the top conservative candidate
   and record the assumption.
8. Validate the selected plan with `scripts/validate_visual_plan.py`. A valid plan is
   not proof of PPTX, PDF, font, projector, or accessibility behavior.

### Gate 3: artifact and rendering

9. Build only the requested artifact with the available presentation editor. Preserve
   source traces, editable structure where requested, and static fallbacks for motion.
10. Render and inspect full slides plus thumbnails. Inspect PDF, notes, links, font
    embedding, animation, or projector behavior only when those deliverables exist.
11. Repair visible defects within scope, rerender, and report manual checks that tools
    cannot perform.

## Slide contract

Each slide records: stable slide ID, claim/purpose, audience question, evidence/source,
layout role, visual/takeaway, density, timing, speaker notes, accessibility treatment,
and unresolved asset. Titles should express a claim when appropriate.
For `outline`, require the supported claim/purpose, source trace, order, time budget,
and blockers. Later visual-system, detailed notes, and accessibility decisions may
remain explicitly pending; do not manufacture them merely to fill a full-deck row.

Charts preserve metric, units, baseline, run/sample context, uncertainty when
supported, and source trace. Color cannot be the only encoding. Meaningful visuals
need alt text or equivalent notes and logical reading order.

## Preview and template rules

Preview candidates must differ in layout logic, hierarchy, typography, evidence
treatment, or interaction—not only color. Style references constrain visual language
but do not authorize copying protected content.

A supplied template is first audited for masters/layouts, fonts, tokens, aspect ratio,
placeholders, and accessibility. Record every deviation. If unavailable, use an
explicitly labeled neutral fallback.

## Automation and resources

The canonical visual-plan schema is
[visual-plan.schema.json](assets/schemas/visual-plan.schema.json). Layout, style, and
chart catalogs are under `assets/catalogs/`. Recommendation and validation scripts
use the Python standard library and only plan/validate; they do not create or render a
deck. Detailed interfaces remain in [SPEC.md](SPEC.md).

## Output and handoff

Return only mode-relevant artifacts plus:

- source/evidence boundary and unresolved assets;
- content plan and visual-system decision;
- validation commands/results and artifact views inspected;
- visual asset manifest with reuse/source notes;
- manual checks and limitations.

For `outline`, return the story/slide plan, source boundary, timing, and blocked asset
needs; no selected visual system, asset manifest, render proof, or deck file is due.
For `visual-audit`, return scoped findings, inspected views, source limitations, and
manual checks; no new content plan or candidate visual system is due. These are
completed narrow-mode outputs, not incomplete deck deliveries.

If a source-faithful chart must be rebuilt, hand verified data, claim, units,
uncertainty, and visual constraints to `$visual-research-artifact-generation`.

## Failure behavior

If source evidence is missing, return a bounded outline and blocked claims. If visual
validation fails, do not build the full deck from that plan. If rendering is
unavailable, return the validated plan and mark artifact checks not run. Never invent
paper results or report unperformed accessibility/export checks as passed.

## Validation checklist

- [ ] Required source, audience, duration, mode, and output are explicit.
- [ ] One supported claim/navigation purpose and source trace exist per slide.
- [ ] Slide/time budget supports the story arc and intended discussion.
- [ ] Visual candidates are meaningfully different and selection/waiver is recorded.
- [ ] Visual-plan validation passes before deck construction.
- [ ] Rendered full-slide and thumbnail views were inspected for deck modes.
- [ ] Charts, visuals, citations, notes, and accessibility preserve evidence and meaning.
- [ ] Artifact-specific checks are reported only when actually performed.

## Shared contracts and stop conditions

Follow [approval](../_shared/approval-workflow.md),
[file safety](../_shared/file-mutation-safety.md),
[operational boundaries](../_shared/operational-boundaries.md), and
[evidence](../_shared/evidence-policy.md). RAG is `never`. Stop when the requested
mode's plan, audit, or rendered artifact and applicable gates are complete, or when required
source, template, tool, authorization, or a validation gate is unavailable.
