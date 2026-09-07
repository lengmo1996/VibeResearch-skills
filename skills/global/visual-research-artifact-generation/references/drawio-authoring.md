# Draw.io Authoring

## Authoring sequence

1. Convert the request or observable source into explicit nodes, edges, groups, labels, and
   uncertainties.
2. Give every semantic element a stable ID. Preserve IDs when revising existing source.
3. Select `horizontal`, `vertical`, `grid`, or `manual` layout.
4. Put grouped children under a container node. Child coordinates are relative to the container.
5. Choose a bundled style preset and override only when the request requires it.
6. Build, validate, optionally export, and inspect the rendered result.

## JSON fields

Top-level fields:

- `title`: diagram title and stable diagram-ID seed.
- `layout`: `horizontal`, `vertical`, `grid`, or `manual`.
- `theme`: key from `assets/drawio-style-presets.json`.
- `directed`: whether default edges use an arrow.
- `page`: optional positive `width` and `height`.
- `nodes`: non-empty list of node objects.
- `edges`: list of edge objects.

Node fields:

- `id`, `label`, `kind`, `parent`, `container`;
- optional `x`, `y`, `width`, `height`;
- optional complete Draw.io `style` override.

Supported bundled kinds are `default`, `process`, `data`, `decision`, `note`, and `group`.

Edge fields:

- `id`, `source`, `target`, `label`, `kind`;
- optional `directed` and complete `style` override.

Supported bundled edge kinds are `default`, `dashed`, and `dependency`.

## Layout guidance

- Horizontal: left-to-right pipelines and method overviews.
- Vertical: top-down procedures, hierarchies, and decision flows.
- Grid: unordered inventories or relationship sets without a meaningful direction.
- Manual: source reconstruction or venue-specific composition with supplied coordinates.

Keep labels concise, avoid crossing edges, align comparable nodes, and use containers only for
real semantic grouping. Do not turn decorative panels into false graph structure.

## Commands

```text
<python-command> <skill-root>/scripts/build_drawio.py graph.json output.drawio
<python-command> <skill-root>/scripts/validate_drawio.py output.drawio --json
<python-command> <skill-root>/scripts/export_drawio.py output.drawio --format svg --output output.svg
```

Use `--force` only when overwriting the exact user-authorized output path.
