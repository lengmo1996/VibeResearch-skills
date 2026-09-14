# Mode Analysis Protocol

## Shared sequence

For every mode:

1. transcribe the observable source element without correction;
2. retain the exact artifact location; assign stable `CLM-*` IDs when a full report
   or actual handoff needs a structured ledger;
3. classify the statement as `paper states`, `supported interpretation`, or
   `unconfirmed inference`;
4. test whether missing context changes the conclusion;
5. preserve contradictions, linking existing claim IDs when available.

## Mode-specific extraction

| Mode | Observe first | Required checks |
|---|---|---|
| `overview` | problem, stated contributions, method summary, results | complete-paper coverage and claim/evidence fit |
| `method` | modules, interfaces, data flow | observed interface versus inferred function |
| `equations` | symbols, operators, dimensions, stated assumptions | symbol reuse, dimensional consistency, derivation boundary |
| `figure` | labels, arrows, legend, caption, visible grouping | crop, resolution, encoding convention, inferred arrow risk |
| `table` | headers, metric direction, values, footnotes | split, protocol, baseline comparability, missing variance |
| `experiments` | datasets, settings, baselines, metrics, ablations | control fairness, leakage, variance, claim support |
| `limitations` | author statements and evidenced failure patterns | stated versus inferred, scope, external validity |
| `full` | all applicable elements | source completeness before claiming full coverage |

## Revision rule

New evidence may raise or lower confidence, but never erase the prior claim silently.
Keep the claim ID, record the revision source, and state whether the earlier
interpretation was narrowed, contradicted, or superseded.
