# Method structure guide

Load this guide only for a method `outline` or structural `draft`.

## Establish the reader path

Use this order unless the method itself requires another dependency order:

1. **Problem setup:** inputs, outputs, task definition, assumptions, and notation.
2. **Overview:** the end-to-end information flow and the reason for each major stage.
3. **Components:** one subsection per independently understandable operation.
4. **Objective or algorithm:** losses, optimization, inference, or procedural logic.
5. **Implementation boundary:** details needed for reproducibility, separated from
   conceptual claims.

Introduce a symbol before using it. Keep the prose, equations, and figure labels
aligned.

## Plan each component

For every component, record:

- **Role:** the limitation or dependency it addresses.
- **Input and output:** tensors, records, variables, or states with shape or domain
  where verified.
- **Operation:** the transformation, objective, or decision rule.
- **Rationale:** why this operation belongs in the method, without inventing a
  mechanism.
- **Interface:** what the next component consumes.
- **Evidence hook:** the ablation, analysis, or comparison expected to test its role.

This role–operation–interface pattern prevents a method section from becoming either
a code walk-through or an unsupported motivation essay.

## Draft checks

- Overview names all major components in the same order used later.
- Each subsection has a distinct responsibility and explicit interfaces.
- Equations define symbols, domains, reductions, and optimization direction.
- Training and inference behavior are distinguished when they differ.
- Reproducibility details are present only when supplied or verified.
- Claimed mechanisms are labeled as hypotheses unless supported by analysis.
