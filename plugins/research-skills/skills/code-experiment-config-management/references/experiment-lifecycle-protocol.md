# Experiment Lifecycle Protocol

## Materialized configuration

Resolve defaults, includes, environment-independent substitutions, and explicit
overrides into one materialized configuration before a run. Record override source
and precedence. Canonicalize keys, scalar types, ordering, and path policy before
hashing.

Exclude only declared operational fields such as output path or creation timestamp.
Never exclude a value that can change scientific behavior. Record the hash algorithm
and canonicalization version.

## Run identity

The immutable run ID combines or references:

- materialized config fingerprint;
- code identity (commit or content fingerprint);
- data/split identity;
- seed set and protocol version.

A human-readable name and timestamp are labels, not identity. Collision behavior must
be deterministic: reject, resume after validation, or allocate an explicitly linked
replicate.

## Checkpoint and resume

Record model, optimizer, scheduler, scaler, RNG states, sampler/dataloader state,
step/epoch, data cursor, and config/code/data fingerprints when applicable.

Classify each difference:

- `exact`: all behavior-relevant identities match;
- `compatible`: declared difference is allowed and its consequence is recorded;
- `unsafe`: semantic continuation is not justified; start a new linked run or hand
  format migration to `$code-repo-adaptation`.

Never silently reset optimizer, RNG, or data position while calling the run resumed.

## Registry and lineage

Create an immutable start manifest, append lifecycle events, and finish with a linked
final manifest. Register planned, running, completed, failed, and interrupted states.
Every metric/artifact records run ID, step/epoch, schema, and provenance. Retention may
remove authorized artifacts but must preserve tombstone metadata and lineage.
