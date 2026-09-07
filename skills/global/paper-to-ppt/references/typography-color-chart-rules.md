# Readable text and inspectable quantitative evidence

Use the catalog tokens as a consistent starting point, then judge the actual
rendered text and evidence. This guide distinguishes program compatibility rules,
local authoring heuristics, and externally sourced accessibility facts.

## Typography that survives the actual content

The font lists in `academic-style-presets.json` are ordered candidates for each
language, not proof that fonts are installed or redistributable. Resolve available
fonts in the rendering environment and record substitutions. Check Chinese
characters, Latin text, punctuation, subscripts, minus signs, Greek letters, and
mathematical symbols with the real slide content. Do not assume that a font that
renders the title also covers an equation or a bilingual bibliography.

Use one visible hierarchy for claims, explanations, chart labels, and sources.
The new catalog begins with title sizes of 32–38 pt, body sizes of 22–24 pt,
captions of 16–18 pt, and source labels of 11–12 pt. These ranges are local design
heuristics, not accessibility standards or promises about projection. Source
labels identify a trace; information needed to understand a result belongs at a
readable content size. Increase type or reduce content when the actual view needs
it. Never use a smaller language translation as a way to hide a contradictory
qualification.

The current validator requires titles of at least 28 pt, body text of at least
18 pt, and safe margins of at least 0.35 in; it warns about source text below
9 pt. Those are repository compatibility checks. They do not verify that a chart
imported as an image has readable labels. Keep line breaks, language pairing,
abbreviation expansions, and mathematical symbol conventions stable across pages.

## Color as a redundant signal

Assign color by meaning: shared background and text; a primary comparison; a
secondary condition; a caveat or current focus. Keep the same method or condition
identities throughout the talk. Use direct labels, markers, line patterns, or
written status alongside color, especially for errors, significance, and
completed/planned work. This follows the principle in
[W3C's explanation of WCAG 2.2 criterion 1.4.1](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
that information must not rely on color alone.

WCAG 2.2 criterion 1.4.3 specifies a text contrast ratio of at least 4.5:1, with a
3:1 exception for its defined large text and other stated exceptions. We adopt
4.5:1 for deck text as a conservative planning target. This adaptation does not
establish WCAG conformance for a PPTX or PDF. Check the actual foreground and
background pair, including labels on colored fills and images; do not round a
failing ratio up to a pass. See the
[official W3C contrast explanation](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

The script checks only the selected `text`/`background` pair. It does not validate
every palette pair, line, plot mark, or rendered transparency. Do not use an accent
as small text without checking that use. Inspect a grayscale view for lost
distinctions and a rendered view for fine lines and faded labels.

## Select a chart from the evidence question

| Evidence question | Suitable initial view | Context that must remain available |
|---|---|---|
| Which method differs on a metric? | Labeled points or bars, with supported uncertainty | Metric, units, direction, baseline identities, evaluation population |
| What changes along an ordered variable? | Line plot or points at observed positions | Both axes, actual sampling positions, gaps and transformations |
| What is the distribution? | Individual points, histogram, or explained summary plot | Sample count, independent unit, grouping, bin or summary definition |
| Are two measurements associated? | Scatter plot | Units, pairing, grouping, sample count; association alone does not show causation |
| What does a component contribute? | Matched ablation table or paired difference view | Shared protocol, component state, baseline, uncertainty if available |
| What varies across space or matrix cells? | Labeled heat map or small multiples | Coordinate/cell meaning, scale, normalization, missing-value treatment |
| What happens in representative examples? | Aligned panels with a selection note | Sample identity, comparable crops, output scale, failure cases |
| What is the status of a planned action? | Dated milestone or dependency view | Observed completion, planned date, dependency, verification evidence |

The machine catalog additionally covers uncertainty summaries and compositions.
Its `required` tokens form a minimum input-presence check, while its `avoid` and
`accessibility` entries guide human review. A token in `chart_fields` asserts that
information is supplied; the script cannot establish that the value is true,
displayed, or statistically appropriate. Supply `source_trace` independently.

The `comparison` rule retains four required field tokens for caller compatibility:
`metric-name`, `units`, `baseline-identity`, and `direct-takeaway`. Sample and run
context, protocol comparability, and uncertainty are still required human review
topics when the claim depends on them. A dimensionless metric can be labeled
“dimensionless”; a normalized display intensity should be described as such.

## Show the limits of the numbers

State whether a mark is a single run, a sample summary, or an aggregate across
datasets or seeds. Identify the independent unit and available sample/run count.
For error bars or bands, name what they represent, the level if applicable, and
the computation or source. Distinguish standard deviation, standard error,
confidence intervals, and ranges. Do not manufacture error bars for a lone value;
write “uncertainty not reported” where that limitation matters.

Keep units, scale factors, normalization, metric direction, and axis transformations
visible. If using bars to compare magnitude, start the magnitude axis at zero or
choose another clearly labeled view; explicitly mark any truncated axis. Do not
connect unordered categories as if they were a trajectory. Share scales across
comparable panels unless a documented analytic reason requires otherwise.

Separate measured values from interpolations, targets, simulations, and forecasts
using labels and line conventions. Include adverse or mixed evidence that limits
the title. A visually separated pair of estimates alone is not a significance
test. If significance is claimed, provide the actual test, comparison scope, and
supporting result from the verified analysis.

Finish each chart check by reading its title against the data source, the visible
marks, and the caveat. If those disagree, repair the claim or the evidence view
before polishing the style.
