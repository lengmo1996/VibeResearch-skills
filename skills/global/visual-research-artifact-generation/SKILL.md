---
name: visual-research-artifact-generation
description: "Use when generating or revising a claim-linked standalone research visual from natural language, verified data, a graph specification, or an existing visualization. Produces editable Draw.io diagrams, TikZ/PGFPlots, data plots, LaTeX tables, or multi-panel artifacts with figure-role, provenance, cross-figure, preview, and validation checks. Do not use for visual-pattern mining, complete slide decks, result interpretation, manuscript drafting, or photo and illustration generation."
---

# Visual Research Artifact Generation

Create the smallest editable research-visual artifact that satisfies the request. Select one
primary backend unless the user explicitly requests multiple artifact classes.

## Workflow

1. Inspect the supplied request, data, graph, or visualization. Separate verified content from
   inference and mark unavailable content `not provided / unclear`.
2. Identify the semantic artifact:
   - node/relationship, process, architecture, method, ER/UML/C4, or manually editable diagram;
   - mathematical or TeX-native schematic;
   - axis-based quantitative plot;
   - exact row/column comparison;
   - multi-panel composition.
3. Read [backend-selection](references/backend-selection.md), then choose the lightest backend:
   `drawio-diagram`, `tikz-diagram`, `pgfplots`, `data-plot`, `latex-table`, or `multi-panel`.
4. Use [artifact specification](templates/visual-artifact-spec.md). Assign stable `FIG-*`,
   optional `PAN-*`, `SRC-*`, and `ELEM-*` IDs. Preserve upstream `CLM-*` and result evidence
   references instead of inventing new claims. Never recover hidden numerical values from pixels
   or invent missing labels, metrics, units, uncertainty, or statistical annotations.
5. When the visual belongs to a paper or figure family, read
   [visual story contract](references/visual-story-contract.md). Declare its narrative role,
   companion relationships, terminology/encoding invariants, and caption boundary. For a truly
   standalone artifact, record `standalone` and do not manufacture companions.
6. Generate editable source. Keep data/content separate from rendering logic and preserve the
   `SRC-*` → `ELEM-*` mapping.
7. Render when the required runtime exists, inspect the preview, and correct structural or visual
   defects. Do not claim rendering or visual verification when it was not performed.
8. Validate the delivery record with `scripts/validate_visual_spec.py --completed`
   (the default checks template structure only), then deliver source,
   preview when available, source-to-output and claim-evidence mapping, reproduction command,
   validation result, and unresolved items.

Track validation independently as `passed`, `failed`, `blocked`, or `not-run` for:
source/content, structure/schema, compile/build, render/export, visual inspection, and
semantic/value cross-check. Success at one layer never implies another.

## Backend resources

- For Draw.io authoring or revision, read
  [drawio-authoring](references/drawio-authoring.md). Convert the interpreted graph to the JSON
  contract there, then run `scripts/build_drawio.py`. Run `scripts/validate_drawio.py` before
  delivery and `scripts/export_drawio.py` only when a Draw.io CLI is available.
- For LaTeX tables, TikZ, PGFPlots, data plots, or multi-panel output, read
  [latex-data-artifacts](references/latex-data-artifacts.md).
- Before final delivery, read
  [validation-and-export](references/validation-and-export.md).

## Existing visualization input

- Treat editable source as authoritative and preserve unaffected labels, values, and semantics.
- Treat PNG, screenshot, or rendered PDF as observable evidence only. Reconstruct the visible
  structure and style; list ambiguous, occluded, or unreadable elements.
- For an image-only chart without recoverable source data, produce a style/layout specification or
  a clearly marked scaffold. Do not manufacture a data series.
- Do not reproduce protected artwork or branding verbatim. Abstract reusable layout and encoding.

## Draw.io quick commands

```text
<python-command> <skill-root>/scripts/build_drawio.py graph.json output.drawio
<python-command> <skill-root>/scripts/validate_drawio.py output.drawio
<python-command> <skill-root>/scripts/export_drawio.py output.drawio --format svg --output output.svg
```

Use paths relative to this Skill directory when invoking packaged copies.

## Output contract

Return the applicable items:

- editable source artifact;
- rendered PNG, SVG, or PDF preview when verified;
- mapping from supplied facts/data/nodes to output elements;
- figure/panel narrative role, target claim IDs, evidence references, and companion relations;
- exact compile, run, or export command;
- structural, compile, render, and visual-check status;
- assumptions and unresolved evidence.

For revisions, list preserved, changed, added, and removed `ELEM-*` IDs. Do not treat
an accidental layout or label change as harmless because the file still validates.

## Boundaries

- `$visual-expression-mining` owns analysis of reusable visual patterns.
- `$paper-to-ppt` owns complete presentation decks and final slide visual systems.
- `$research-result-analysis` owns interpretation of experimental meaning.
- `$writing-academic` owns manuscript narrative and caption prose; this Skill only records the
  figure's declared narrative and caption boundary.
- Image-generation capabilities own photos, illustrations, and free-form raster art.
- This Skill may consume a source-traceable handoff from an upstream Skill, but remains the single
  primary owner of the standalone visual artifact.

Follow the shared [operational boundaries](../../_shared/operational-boundaries.md),
[file mutation safety](../../_shared/file-mutation-safety.md), and
[platform compatibility](../../_shared/platform-compatibility.md). RAG is `never` for this Skill.
Write only user-requested artifacts inside an authorized workspace and perform no external
publication, upload, or release.
