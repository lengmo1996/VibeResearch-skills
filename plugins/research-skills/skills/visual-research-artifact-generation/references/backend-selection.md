# Backend Selection

Choose by semantic structure and required editability, not by tool familiarity.

| Request signal | Default backend | Reason |
|---|---|---|
| process, pipeline, architecture, relationship network, ER/UML/C4 | Draw.io | direct node/edge editing |
| user must drag, regroup, or relabel diagram elements | Draw.io | editor-native objects |
| compact TeX-native schematic or formula-linked annotation | TikZ | native manuscript integration |
| publication plot whose typography must match TeX | PGFPlots | TeX-aligned axes and labels |
| complex statistical, exploratory, or high-density plot | data plot | stronger data transformation ecosystem |
| exact comparisons in rows and columns | LaTeX table | precise tabular semantics |
| coordinated heterogeneous panels | multi-panel | explicit composition contract |

## Tie breakers

1. Honor an explicit output format when it can represent the artifact faithfully.
2. Prefer Draw.io over TikZ when manual node editing is the dominant need.
3. Prefer TikZ over Draw.io for small TeX-native schematics with formula-level alignment.
4. Prefer PGFPlots for stable publication plots and a data runtime for complex processing.
5. Do not generate every backend as a precaution. Generate multiple sources only when requested or
   when heterogeneous panels require them.

## Adjacent tasks

- Pattern analysis without final generation belongs to `$visual-expression-mining`.
- Full slide decks belong to `$paper-to-ppt`.
- Scientific interpretation belongs to `$research-result-analysis`.
- Photos, illustrations, and free-form raster art belong to image-generation capabilities.
