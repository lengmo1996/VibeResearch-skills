# Author style profile protocol

Load this reference only for `style-preference` when the user explicitly asks to
capture reusable traits from their own writing.

## Eligibility

Require all of the following:

- the user identifies the sample as author-owned;
- the user authorizes analysis for a reviewable profile candidate;
- the language and academic genre are known;
- enough comparable prose exists to support repeated observations.

Do not build a profile from retrieved third-party papers, mixed-author text with
unclear ownership, confidential reviewer text, chat history, or an automatically
loaded file. Retrieval may compare existing approved profiles for deduplication, but
retrieved text never establishes a new user preference.

## Abstract traits, not prose

Record only traits that affect future academic editing:

- sentence rhythm and typical variation;
- technical vocabulary and formality;
- paragraph openings and transitions;
- punctuation and parenthetical use;
- first-person, active-voice, and cautious-claim preferences;
- terminology to preserve or avoid.

Each trait needs a stable ID, dimension, short preference statement, at least one
source locator, and confidence from `0` to `1`. Do not store raw sample text, long
excerpts, full prompts, chat, or reconstructed passages. Source references should be
IDs, titles, and locators sufficient for audit without embedding the source.

## Scope and confidence

Bind language, genre, domain, and applicable manuscript sections. Mark a trait
low-confidence when it appears only once, differs across samples, or comes from a
non-comparable section. A profile does not generalize beyond its declared scope and
does not override evidence, terminology, venue, or scientific-integrity rules.

## Review lifecycle

New profiles use `status: pending_review`. Approval/rejection requires the exact
`WSP-*` ID, prior status, actor, timestamp, and decision evidence. Preserve profile
identity and provenance across transitions. Approval does not persist the profile to
project memory, ingest it into KnowledgeHub, or automatically activate it.

`$writing-academic` may consume an approved profile only when the user explicitly
selects it for the current writing task.
