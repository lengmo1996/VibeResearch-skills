# LaTeX and Data Artifacts

## LaTeX tables

- Verify row/column meaning, metric direction, units, precision, missing values, and aggregation
  before marking best or second-best results.
- Prefer `booktabs`; avoid vertical rules and dense grids.
- Keep data definitions separate from formatting logic.
- Use `tabularx`, controlled abbreviation, grouped headers, or table splitting before indiscriminate
  scaling.
- Supply caption, label, required packages, width target, and compile command.

## Data plots

- Preserve the original data or a source-linked data file.
- Label axes, units, legend semantics, uncertainty, and statistical annotations explicitly.
- Avoid 3D effects, misleading truncation, decoration without meaning, and color-only encoding.
- Prefer vector output for publication.
- Use a general plotting runtime when preprocessing, statistical layers, or high-density
  visualization exceed PGFPlots' practical clarity.

## PGFPlots

- Use for publication plots that benefit from manuscript-consistent typography.
- Separate table data from `axis` presentation settings.
- State the required packages and compatibility level.
- Compile and inspect the resulting PDF before claiming success.

## TikZ diagrams

- Use for compact TeX-native schematics, not as a default substitute for editable node diagrams.
- Keep node styles semantic and reusable.
- Avoid unexplained absolute coordinates when relative placement expresses the structure.
- Use Draw.io when manual dragging and future visual editing dominate.

## Multi-panel artifacts

- Define each panel's claim, source, backend, label, and shared visual encodings.
- Keep panel data and source files independently editable.
- Verify consistent typography, color meaning, spacing, and caption references after composition.
