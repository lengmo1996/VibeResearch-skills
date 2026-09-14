# Experiment Configuration and Run Contract

Use only the sections required by the selected mode. `full` combines the contracts;
narrow requests omit unrelated sections and do not create empty manifests.

## Configuration tree and override rules

## Seed and determinism policy

## Run naming and identity

- Canonicalization rules:
- Fingerprint inputs / exclusions:
- Collision behavior:

## Checkpoint and resume contract

### Saved state

- Model / optimizer / scheduler / scaler:
- RNG and sampler/dataloader state:
- Step/epoch and data cursor:
- Config/code/data fingerprints:

### Resume compatibility

| Field | Exact match required | Compatible change | Unsafe change | Action |
|---|---|---|---|---|

## Logging and result registry

## Directory and archive layout

## Example manifest

```yaml
run:
  id:
  name:
  code_identity:
  data_identity:
  config_fingerprint:
  seed_set: {}
  parent_run_id:
  started_at:
  status: planned | running | completed | failed | interrupted
artifacts:
  checkpoints: []
  logs: []
  results: []
resume:
  source:
  source_run_id:
  compatibility_verdict: exact | compatible | unsafe
  differences: []
lineage_events: []
```

## Risks, missing inputs, and integration handoff
