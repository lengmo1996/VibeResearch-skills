# Validation and Export

## Shared checks

Use `validate_visual_spec.py --completed` for a delivery record. Its default mode
checks an editable template only. Completed-record validation checks unique IDs,
reference closure, explicit statuses, and recorded evidence for successful steps;
it does not execute a renderer or independently prove source truth. A standalone
visual without upstream claims declares `Target claim IDs: none` and leaves the
claim-coverage table empty. Record blocked rendering honestly with its reason.

- Confirm every visible value, label, unit, and relationship has a supplied source or a clearly
  marked inference.
- Check the requested dimensions, target venue, color policy, typography, and accessibility.
- Render the final source when the runtime exists and inspect the actual result.
- Distinguish `source validated`, `compiled/rendered`, and `visually inspected`.
- Confirm each target `CLM-*` maps to supplied `SRC-*` evidence and visible
  `FIG/PAN/ELEM-*` records.
- For declared companions, check terminology and encoding invariants independently
  from single-artifact render success.

## Draw.io

1. Run `validate_drawio.py`.
2. Confirm unique IDs, valid parents, valid edge endpoints, positive geometry, and editable cells.
3. If Draw.io CLI is available, export SVG or PNG with `export_drawio.py`.
4. Inspect clipping, overlaps, edge crossings, label legibility, and grouping.
5. Preserve the `.drawio` source even when export is unavailable.

## LaTeX, TikZ, and PGFPlots

- Compile in the target document context when available.
- Check missing packages, overfull boxes, font consistency, labels, references, and column fit.
- Inspect the rendered PDF rather than treating compilation alone as visual validation.

## Data plots

- Re-run the plotting source from the delivered data.
- Cross-check plotted values against the input.
- Inspect axes, ranges, legends, uncertainty, color accessibility, and vector export.

## Delivery record

Report:

- source artifacts;
- preview artifacts and formats;
- exact reproduction commands;
- structural/compile/render/visual status;
- assumptions, warnings, and unresolved items.
- claim-evidence trace and cross-figure consistency status.
