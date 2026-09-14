# Experiment Config Management Prompt

Produce only the selected mode's contract. The list below supplies sections for
`full`; omit unrelated items and empty artifacts in a narrow mode:

- configuration tree and override precedence;
- seed and determinism policy;
- stable run identity;
- checkpoint contents, naming, selection, and resume preconditions;
- logging/result registry;
- archive manifest and retention rules.

Do not implement methods, migrate checkpoint formats, debug failures, run smoke tests,
verify patches, or interpret scientific results.
