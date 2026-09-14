# Paper Reproduction Prompt

Use the narrowest `paper-reproduction` mode.

1. Reuse source-bounded evidence from `paper-deep-read` when available.
2. Separate paper fact, paper-to-code inference, and engineering choice.
3. Load only the selected mode's protocol fragments and output sections in `SKILL.md`.
4. Establish provenance when discovering code; map Method → Equation → Architecture
   → File → Class/Function only when mapping or implementation needs that link.
5. Require explicit authorization before writing core method code.
6. Label every patch `candidate implementation`.
7. Only after code changed, produce the unified verification handoff to `code-debugging`.
   Analysis or discovery alone never requires a full implementation report.

This reproduction stage does not own migration or final verification. Continue an
already-authorized implementation and validation request through `$code-debugging`
in the same task. Never claim paper equivalence without verified official evidence.
