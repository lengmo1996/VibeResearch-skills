# Citation Metadata Protocol

## Identifier normalization

Retain the exact input. Normalize DOI resolver URLs and `doi:` prefixes to a bare DOI;
validate rather than guess missing characters. Keep PMID numeric, distinguish PMCID,
and preserve arXiv version suffixes separately from the work-level identifier.

## Source ledger

For every lookup record source name, query form, retrieval time, locator, response
state, and returned fields. Prefer registration/discipline repositories for identity,
but do not assume one source is complete or current for every field.

## Field comparison

Compare normalized whitespace and Unicode carefully while preserving display forms.
Author order, collective authors, online/print dates, journal abbreviations, article
numbers, pagination, and title punctuation can differ legitimately. A match rule must
not erase a substantive difference.

## Offline consistency checks

Each source's `fields` is an object keyed by returned field name. A provenance entry
marked `verified` or `single-source` must reference a `resolved` source that returned
that field, with non-placeholder source name, query, timestamp, and record locator.
Record-level `verified` requires non-empty canonical values, verified provenance for
every canonical field, and no missing/conflict/single-source field state or unresolved
retrieval failure. Keep bounded single-source results `partial` until the declared
validation depth is satisfied. `not-applicable` fields may remain outside the
canonical record.

These checks establish internal consistency, not truth or independent source
agreement. Every resolved canonical field must match at least one of its linked,
resolved source values under these conservative rules: Unicode NFC, trimmed text;
collapsed whitespace and case folding for title/venue/journal/booktitle/publisher/
series/status and author names; DOI resolver or `doi:` prefix removal and case folding;
four-digit string/integer year equivalence. Author lists preserve order and membership.
Other strings remain case-sensitive, including URL paths; punctuation, substrings,
abbreviations, and approximate title/name matches are never treated as equality.

The agent still investigates conflicting variants and records source-specific
differences. One matching source does not establish cross-source agreement. The
validator does not equate a metadata match with scientific citation support or invent
a second source.

## Duplicates and versions

Exact stable identifiers support exact grouping. Similar title/author/year produces
only a candidate. Relate preprint, conference, journal extension, correction,
retraction, erratum, dataset, and software records explicitly rather than collapsing
them.

## Failure states

Use `resolved`, `zero-hit`, `rate-limited`, `timeout`, `access-denied`,
`malformed-response`, or `not-queried`. Preserve unresolved fields. Do not invent a
DOI because a modern article is expected to have one.
