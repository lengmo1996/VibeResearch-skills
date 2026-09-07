# paper-to-ppt Skill 设计规格说明书

Version: `1.2.0`

Status: active

Public profile: review and release independently of any private repository history.

## 1. Purpose

`paper-to-ppt` converts verified paper or research content into an academic
presentation and owns the final presentation visual system. It supports paper
talks, lab meetings, project updates, defenses, conference talks, and courses.
It excludes commercial pitches, marketing decks, and product UI design.

The Skill separates two concerns:

1. source-faithful narrative and slide allocation;
2. context-driven visual decisions covering layout, style, color, typography,
   charts, interaction, motion, fixed-canvas adaptation, and accessibility.

## 2. Modes

| Mode | Purpose | Output |
|---|---|---|
| `outline` | Allocate the narrative and slide budget. | story arc and slide outline |
| `visual-system` | Rank visual directions and map layouts before rendering. | visual plan JSON/Markdown |
| `deck` | Build and render the requested deck. | PPTX/PDF or equivalent artifact |
| `speaker-ready` | Add notes, timing, prompts, and delivery guidance. | deck plus speaker notes |
| `template-adaptation` | Apply a supplied template without losing evidence or accessibility. | adapted deck and exceptions |
| `visual-audit` | Audit an existing deck or plan. | deterministic findings and manual checks |

`deck`, `speaker-ready`, and `template-adaptation` include the
`visual-system` stage. `visual-audit` does not authorize edits unless the user
also requests them.

### Mode-scoped resources and completion

Use the initial/conditional resource table in `SKILL.md` as the loading contract.
`outline` starts with the content-plan template and stops after supported claims,
slide/time allocation, source traces, and blockers. It neither loads visual-system
guides/catalogs nor needs a chosen palette, full asset manifest, or rendered deck.
`visual-audit` starts with the QA checklist plus only the rules needed for the stated
checks. It audits supplied artifacts without requiring candidate generation or a new
narrative. Missing evidence is an explicit limitation, not a fabricated design.

Deck modes add visual planning and artifact QA at the corresponding gates. Reuse an
existing validated plan; read a catalog only for a concrete unresolved selection or
let the recommender consume it as a script input. Read this SPEC's detailed interfaces
or the schema only when using/diagnosing them. An initial reference budget does not
limit the safety, evidence, or rendering requirements of the actual selected mode.

## 3. Inputs

Required:

- paper, reading report, or verified research results;
- audience and duration;
- desired output mode.

Optional:

- language, deck type, venue, slide budget, and aspect ratio;
- PPTX template or style reference images;
- verified figures, tables, images, and data;
- `presentation_handoff` from `visual-expression-mining`;
- accessibility, projector, export, branding, and speaker-note constraints.

Mark missing inputs as `not provided / unclear`. Never imply that an unavailable
paper, template, font, figure, or rendering environment was inspected.

## 4. Visual-design brief

The recommender accepts a JSON object:

```json
{
  "deck_type": "paper-talk",
  "audience": "lab researchers",
  "language": "zh",
  "aspect_ratio": "16:9",
  "domain": "computer-science",
  "duration_minutes": 15,
  "candidate_count": 3,
  "template_constraints": [],
  "slides": [
    {
      "id": "s6",
      "role": "method-overview",
      "claim": "The method aligns two modalities in three stages",
      "content_types": ["pipeline", "architecture"],
      "density": "medium",
      "item_count": 6,
      "evidence_type": "",
      "interaction_intent": "progressive-reveal",
      "alt_text": "Three-stage pipeline from two inputs to one prediction.",
      "source_trace": "Paper Figure 2, page 4"
    }
  ]
}
```

`candidate_count` is clamped to two through four. Unknown deck types use a
conservative general research fallback and emit a warning.

## 5. Visual-plan output

The machine-readable contract is
`assets/schemas/visual-plan.schema.json`. The output contains:

- normalized brief;
- ranked candidate systems with rationale;
- selected global palette, typography, spacing, chart, and motion tokens;
- per-slide role, layout, hierarchy, chart, interaction, motion,
  accessibility, and source trace;
- deterministic warnings and validation targets.

The selected system is a planning interface, not proof that PowerPoint,
projector, PDF, font embedding, or accessibility behavior has been verified.

## 6. Decision workflow

Apply only the selected mode's stages; visual-audit starts from existing-artifact QA.

1. Validate sources and presentation constraints.
2. Extract supported claims, evidence, uncertainty, limitations, and source
   traces.
3. Allocate slide roles and one claim per slide.
4. Build the visual-design brief.
5. Rank two to four visual systems using deck type, domain, tone, language,
   template, projection, export, and accessibility constraints.
6. Generate representative previews with identical content across candidates.
7. Record the user-selected direction or an explicitly accepted conservative
   fallback.
8. Map each slide to a layout, evidence form, interaction, motion, and
   accessibility treatment.
9. Build the artifact, render it, and validate both visual plan and output.

## 7. Layout and evidence rules

Assign semantic slide roles such as title, motivation, task definition, method
overview, equation, main results, ablation, qualitative results, failure cases,
limitations, takeaway, and Q&A.

- Use `assets/catalogs/slide-layouts.json` for deterministic layout candidates.
- Use `assets/catalogs/chart-rules.json` for evidence-to-chart mappings.
- Keep tables and grids only when the audience must inspect structured
  comparisons.
- Preserve metric name, units, baseline, run/sample context, uncertainty when
  supported, and source trace.
- Do not derive a stronger claim than the visible evidence supports.

## 8. Visual-system rules

- Use one global semantic palette and one typography/spacing system.
- Keep normal text/background contrast at least 4.5:1.
- Default to at least 28 pt primary title, 18 pt body, 14 pt caption, and 10 pt
  source trace.
- Default to at least 0.35 in safe margins.
- Provide Chinese, English, and bilingual font fallbacks.
- Never use color as the sole carrier of identity, significance, or error.
- Prefer projector-safe light systems when viewing conditions are unknown.
- Treat supplied template rules as constraints, not evidence.

## 9. Interaction, motion, and adaptation

- Use interaction for labeled navigation, discussion prompts, or deliberate
  progressive disclosure.
- Preserve a linear path and a static fallback.
- Use motion only for reading order, state comparison, or process explanation.
- Provide a reduced-motion path and avoid flashing or repeated decorative
  movement.
- Treat responsive behavior as reflow and readability across 16:9/4:3,
  PowerPoint, PDF, thumbnails, and projection—not as CSS breakpoints.
- Reflow a 4:3 variant; do not horizontally compress a 16:9 slide.

## 10. Accessibility

- Provide alt text or speaker-note descriptions for meaningful visuals.
- Preserve logical object reading order.
- Pair color with labels, shapes, line styles, patterns, or values.
- Caption audio/video and provide static summaries.
- Explain dense equations, abbreviations, diagrams, and interactions in notes.
- Report manual checks when the available editor/renderer cannot verify a
  requirement.

## 11. Preview and artifact gates

Preview before the full deck unless the user explicitly waives the gate. A
preview set must use the same representative content and differ in meaningful
system decisions, not only color.

Before artifact delivery (`outline` and audit-only outputs use their own applicable gates):

1. run `recommend_visual_system.py` when deterministic selection is useful;
2. run `validate_visual_plan.py` for the visual plan;
3. render the deck;
4. inspect full-slide and thumbnail views;
5. export PDF when requested and inspect fonts, symbols, clipping, links,
   transparency, and source trace;
6. report any animation, accessibility, or projector behavior that still needs
   manual validation.

## 12. Tool and dependency contract

The recommendation and validation scripts use only the Python standard library.
They do not require web frameworks, Chart.js, GSAP, online fonts, icon CDNs,
external APIs, or KnowledgeHub.

Actual deck creation may use the available presentation editor, renderer, PDF
exporter, and image viewer. Check tool availability once before depending on it.

## 13. Cross-Skill contract

- `$paper-deep-read` may provide verified content, equations, and source traces.
- `$visual-expression-mining` may provide an optional `presentation_handoff`
  containing visual roles, layout candidates, source/reuse notes, and
  projection risks. It does not choose final deck styling.
- `$visual-research-artifact-generation` may create verified editable
  charts/tables from supplied data. It does not own slide narrative or system
  design.
- `paper-to-ppt` owns final narrative allocation, visual-system selection,
  slide composition, rendering, and delivery.

Use exactly one primary Skill and at most two supporting Skills.

## 14. Failure behavior

- If the source is unavailable, stop source-dependent deck claims and report the
  missing input.
- If the template is unavailable, use an explicitly labeled neutral fallback.
- If a chart lacks required fields or source trace, keep it as a blocked
  placeholder rather than fabricating data.
- If a visual violates capacity, contrast, alt-text, motion, or export rules,
  return validation findings and repair only when edits are authorized.
- If rendering is unavailable, provide the verified slide/visual plan and mark
  artifact-level checks as not run.

## 15. Acceptance criteria

- Existing modes and triggers remain compatible.
- Every slide has one supported claim or navigation purpose.
- Every system decision has a context, template, evidence, or accessibility
  rationale.
- Candidate directions number two through four and are meaningfully distinct.
- Visual plan validation is deterministic.
- PPTX/PDF/thumbnail/projector claims are made only after the corresponding
  artifact check.
- No commercial pitch, product UI, web-stack, or unlicensed upstream material
  enters the active Skill.
