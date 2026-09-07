# Manuscript Audit Protocol

Load this reference for multi-mode, scientific-quality, citation, formula,
table-data, reviewer, or full manuscript audits. A local language-only diagnosis can
use the core workflow without loading this file.

## 目录

1. [Build the audit plan](#1-build-the-audit-plan)
2. [Classify evidence state](#2-classify-evidence-state)
3. [Calibrate severity](#3-calibrate-severity)
4. [Run mode-specific checks](#4-run-mode-specific-checks)
5. [Construct findings](#5-construct-findings)
6. [Finish with a residual audit](#6-finish-with-a-residual-audit)
7. [Handoff](#7-handoff)

## 1. Build the audit plan

Record:

- material and sections in scope;
- selected modes and why each is needed;
- auditable objects for each mode;
- evidence source available to each check;
- stopping condition and unavailable checks.

For `full`, start with a risk scan and activate only subchecks supported by the
material. Do not retrieve evidence merely because `full` was requested.

## 2. Classify evidence state

Use one evidence state per finding:

- `observed`: directly visible in the supplied manuscript;
- `corroborated`: confirmed by supplied logs, tables, supplementary material, or a
  verified external source;
- `inference`: reasoned from observed material but not independently confirmed;
- `unresolved`: required material is missing, unreadable, or contradictory.

For citation-evidence, additionally classify source support as `direct`, `partial`,
`contradictory`, `background`, or `unresolved`. A title, keyword overlap, or topical
similarity cannot establish support.

## 3. Calibrate severity

- `S0 Blocking`: invalidates a central result, creates a material integrity problem,
  or makes the manuscript unevaluable.
- `S1 Major`: threatens a central claim, experimental fairness, reproducibility, or
  likely acceptance judgment.
- `S2 Moderate`: materially weakens clarity, traceability, consistency, or supporting
  evidence but does not invalidate the central result.
- `S3 Minor`: local presentation, grammar, formatting, or low-impact consistency
  defect.

Severity measures manuscript impact, not editing effort. Missing evidence is not
automatically S0 or S1; explain the affected claim and decision consequence.

## 4. Run mode-specific checks

- `language`: diagnose grammar, ambiguity, referents, sentence logic, and local
  readability; do not silently rewrite the passage.
- `structure`: follow
  [reverse-outline-protocol.md](reverse-outline-protocol.md) to map paragraph roles
  and argument dependencies before diagnosing defects.
- `logic`: trace problem → gap → hypothesis → method → evidence → claim and identify
  missing or circular links.
- `consistency`: compare claims, terminology, symbols, numbers, units, captions,
  cross-references, and section-level conclusions.
- `terminology`: build a scoped term table and identify collisions, undefined terms,
  or unjustified renaming.
- `formula`: check symbol definition, dimensional consistency, assumptions, equation
  references, and agreement with described computation; do not invent derivations.
- `table-data`: compare supplied cells, captions, units, rankings, deltas, and prose
  claims. Distinguish transcription mismatch from interpretation risk.
- `citation-evidence`: bind each claim to the cited source passage and record support
  class plus unresolved access.
- `reviewer`: assess claimed contribution, soundness, evidence sufficiency,
  experimental fairness, reproducibility, limitations, ethics disclosures when
  relevant, and clarity. Treat venue calibration as an explicit assumption unless
  supported by current official criteria.
- `panel-review`: follow [review-panel-protocol.md](review-panel-protocol.md);
  collect complete reviewer records before synthesis, declare whether contexts were
  isolated, and preserve supported minority or conflicting opinions.

## 5. Construct findings

Give each finding one root cause and one stable ID. Include the exact location,
observed content, evidence state, impact, smallest correction, and a verification
method. Separate:

- defects demonstrated by available evidence;
- improvement suggestions that exceed a strict defect claim;
- questions that require missing material or author clarification.

Merge repeated symptoms only when one correction and verification step can address
them. Otherwise keep separate findings and link the shared dependency.

## 6. Finish with a residual audit

Check that:

- every planned mode was completed or marked unresolved;
- high-severity findings are supported by specific evidence;
- scores, tables, formulas, and narrative claims do not contradict one another;
- duplicated symptoms were merged without hiding distinct impacts;
- suggested corrections preserve scientific content;
- a no-finding result states the actual scope and cannot be read as whole-paper
  certification.

## 7. Handoff

Send only accepted findings to `$writing-academic`, including the finding ID,
protected scientific content, target location, and verification method. Send raw
result interpretation to `$research-result-analysis`, venue packaging to
`$publish-preflight`, and received-review prioritization to
`$writing-review-triage`.

If separately revised material returns for verification, switch to `closure` and
follow [finding-lifecycle.md](finding-lifecycle.md). Do not infer that a suggested
correction was applied, and do not close a finding without observed verification
evidence.
