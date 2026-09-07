# Monitoring Protocol

## Coverage ledger

| Source | Intended scope | Window/cursor | Query or category | Retrieved range | Status | Gap |
|---|---|---|---|---|---|---|

Status is `complete`, `partial`, `failed`, or `not-applicable`. A successful request
does not prove complete coverage when pagination, caps, category shards, or date
boundaries remain unresolved.

## Identity and version

Prefer DOI, arXiv base ID/version, official repository identity, dataset release ID,
or another stable source identifier. Fall back to normalized title plus authors and
record the lower confidence.

Classify:

- `new`: identity absent from prior bounded state;
- `known-updated`: same identity with verified new version or material metadata change;
- `already-known`: same identity/version already covered;
- `uncertain-duplicate`: evidence cannot safely merge or split the records.

## Change card

Each retained candidate records identity, version/date, source evidence, matched
scope, change type, why it may matter, confidence, and one next reading action.
Abstract claims are author claims until verified. Code/dataset availability must use
an inspected source, not a paper promise.

## Stop and saturation

Stop when all declared sources/windows are complete and the candidate budget is
filled, or when remaining sources are unavailable. Report partial coverage instead
of extending the time window or silently substituting a different source.
