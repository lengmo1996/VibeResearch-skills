# Prose-quality audit protocol

Load this reference only for `prose-style` or `artifact-leakage`. The goal is an
explainable revision diagnostic, not AI authorship detection.

## 1. Bind and mask the sample

Record the exact manuscript scope and mask these spans before style analysis:

- code, command output, configuration, and serialized data;
- display equations and equation-only fragments;
- direct quotations and block quotes;
- citation keys, bibliography entries, URLs, and reference lists;
- tables, figure labels, and boilerplate required by a venue template.

Keep the original location map so every reported signal still points to the source.
Do not silently delete masked content or diagnose it as prose. If fewer than three
substantive prose sentences remain, report `insufficient-sample` for `prose-style`.

## 2. Diagnose only bounded signals

Use these compact categories. Do not expand them into a generic catalogue of
everything that might sound artificial.

| ID | Signal | Required observation |
|---|---|---|
| PS-01 | repeated scaffold | the same clause or paragraph frame recurs at distinct locations |
| PS-02 | uniform rhythm | several adjacent sentences have materially similar length and syntax |
| PS-03 | inflated signposting | transition or roadmap language repeatedly exceeds its argumentative function |
| PS-04 | generic evaluation | positive/negative evaluation appears without a bound claim or evidence |
| PS-05 | redundant recap | a conclusion or paragraph restates content without adding a decision or implication |
| PS-06 | lexical monotony | salient non-technical wording repeats where a precise alternative is available |
| PS-07 | dense abstraction | stacked nominalizations or vague nouns obscure actors, operations, or evidence |
| AL-01 | instruction residue | system, prompt, assistant, or generation instructions remain in the manuscript |
| AL-02 | unresolved placeholder | TODO, TK, bracketed insertion notes, dummy values, or template markers remain |
| AL-03 | citation residue | unresolved citation commands, fake keys, or “insert citation” scaffolds remain |
| AL-04 | tool residue | error messages, file paths, debug traces, or tool chatter appear unintentionally |
| AL-05 | drafting scaffold | alternative phrasings, editor notes, or hidden planning labels remain in deliverable prose |

Technical terms, necessary parallelism, venue boilerplate, and concise conventional
phrases are not defects by themselves.

## 3. Calibrate findings

- A prose-style finding requires at least two distinct `PS-*` signals in a bounded
  span or one signal repeated across at least three mapped locations.
- One exact `AL-*` residue may support an artifact finding when its unintended
  presence is directly observable.
- State an alternative explanation for every `PS-*` finding, such as disciplinary
  convention, non-native drafting, template constraint, or intentionally parallel
  exposition.
- Use `high`, `medium`, `low`, or `insufficient-sample` diagnostic confidence.
  Confidence describes the finding, never authorship.
- Prefer location-specific counts and examples over a global score. Do not label text
  “human”, “AI-written”, or “X% AI”.

## 4. Preserve scientific content

The smallest correction may remove residue, vary a repeated scaffold, replace vague
evaluation with a bound claim, or compress redundant signposting. It must preserve:

- claim scope and uncertainty;
- numbers, units, equations, and table relationships;
- citation keys and verified evidence links;
- domain terminology and defined symbols;
- limitations and negative results.

Do not apply the correction in this Skill. Hand accepted findings to
`$writing-academic` with the `AUD-*` IDs, locations, protected content, and
verification method.

## 5. Verify

Re-run the same masking and bounded checks once after a separately authorized
rewrite. Close a finding only when the observed signal is removed and protected
scientific content still passes. Do not loop automatically or optimize against a
detector score.
