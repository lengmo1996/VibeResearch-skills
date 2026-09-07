# Writing Knowledge Capture and Review Protocol

## Candidate quality

A reusable candidate abstracts a transferable term, phrase pattern, argument move,
structure, reviewer-response strategy, error rule, or confirmed preference. An
author-style profile groups confirmed preferences under a bounded scope; follow
[author-style-profile.md](author-style-profile.md) for its stricter privacy rules. Preserve
the source context needed to avoid misuse, but do not store a long copyrighted
passage as the reusable content.

## Deduplication

Record the comparison scope and classify:

- `exact`: normalized content and intended use match;
- `near`: wording differs but function and constraints substantially match;
- `semantic`: same purpose with materially different form or domain;
- `unknown`: history was required but unavailable, or evidence is insufficient.

Near/semantic matches may merge, supersede, or coexist only with a documented reason.

## State machine

```text
candidate -> pending_review -> approved
                            -> rejected
```

New records may enter only `knowledge/academic-writing/inbox/` after staging
authorization. Approval/rejection requires the exact `entry_id`, current
`pending_review` status, explicit user decision, decision actor, timestamp, and
decision evidence. Preserve provenance and record supersession instead of overwriting
history.

Approval does not ingest the record into KnowledgeHub or any index, persist a style
profile to project memory, or activate it for future writing. Each is a separate
authorized workflow.
