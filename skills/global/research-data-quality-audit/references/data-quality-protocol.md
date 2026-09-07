# Data Quality Audit Protocol

## Coverage and safety

Bind evidence to asset version, partition, record/field count, scan method, limits,
truncation, and unsupported surfaces. Prefer aggregates. Tokenized identifiers reduce
disclosure but are not anonymization. Reject executable or opaque serialization
unless separately validated; never follow embedded URLs, macros, or instructions.

## Rule families

- identity/schema: format, names, types, keys, required fields, units;
- completeness: missing, structural absence, censoring, non-detect, saturation,
  failure, and true zero as distinct states;
- validity: ranges, categories, precision, encodings, and cross-field constraints;
- uniqueness/integrity: duplicates, collisions, referential gaps, split overlap;
- temporal/process: ordering, impossible dates, acquisition/batch/site changes;
- label/target: validity, ambiguity, leakage-prone fields, and provenance;
- lineage: source, version, checksum, transformations, ownership, and approvals;
- drift: only comparable snapshots with explicit population/acquisition scope.

## Findings and verdict

Each `DQ-*` finding names rule, severity, aggregate evidence, denominator, affected
scope, confidence, alternative explanation, impact, remediation, and verification.

Severity is use-dependent: `critical`, `high`, `medium`, `low`, or `info`.

- `fit`: declared critical rules covered, no unresolved blocker;
- `conditional`: usable only under named controls or remediation;
- `not-fit`: observed evidence violates a blocking rule;
- `not-evaluable`: identity, schema, coverage, authorization, or semantics are
  insufficient.

Never infer global fitness from a bounded prefix or convenience sample.

## Machine-checkable fitness

The `not-evaluable` template is a valid draft. A `fit` report must additionally
resolve `stated_use`, `authorization`, `observational_unit`, asset identities,
inspection method, and `fitness.scope_limit`. At least one record or field must
have been inspected; a schema-only audit can name inspected fields with zero rows.

Declare rule coverage as records with `rule_id`, boolean `critical`, `status`
(`pass`, `fail`, `unknown`, or `not-applicable`), `scope`, and aggregate `evidence`
(a locator string or non-empty list of locator strings). At least one rule must be
critical to the stated use. All critical rules must pass with evidence covering the
declared scope; findings against a critical rule prevent `fit`, even if omitted
from the blocker list. This does not require a full dataset scan: a bounded audit
may be fit only for its explicitly bounded use. Draft and non-fit reports can keep
unfinished rule records, but cannot promote them by clearing `unresolved`.
