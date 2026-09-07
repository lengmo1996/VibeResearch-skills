# Result Analysis Protocol

## 1. Gate comparability

Check dataset/split, preprocessing, information access, metric implementation and
direction, aggregation, sampling/pairing unit, configuration, compute, and exclusions.
Mark comparisons comparable, conditional, or incomparable before interpreting deltas.

## 2. Separate evidence levels

- Observation: directly present in an artifact.
- Descriptive finding: repeatable pattern within supplied coverage.
- Associational explanation: compatible with the pattern but not uniquely identified.
- Causal attribution: requires a design that isolates the cause.
- Recommendation: action justified by remaining uncertainty and cost.

Never skip a level. Confidence reflects evidence, not rhetorical certainty.

## 3. Assess claims

Use:

- `supported`: planned evidence directly supports the bounded claim;
- `partially-supported`: some scope or mechanism remains unsupported;
- `not-supported`: evidence does not establish the claim;
- `contradicted`: reliable evidence opposes the claim;
- `inconclusive`: protocol, uncertainty, coverage, or conflict prevents a verdict.

Record alternatives and the strongest wording permitted by the evidence.

### Shared claim-evidence mapping

Keep the five-state analysis verdict in the result report. For the downstream shared
claim-evidence patch, use this deterministic projection:

| Analysis verdict | Shared claim status | Result evidence status |
|---|---|---|
| `supported` | `supported` | `verified` |
| `partially-supported` | `partial` | `verified` |
| `not-supported` | `proposed` | `missing` |
| `contradicted` | `contradicted` | `contradictory` |
| `inconclusive` | `proposed` | `candidate` or `missing` |

Record `analysis_status=<verdict>` and the allowed wording or blocker in the evidence
note. This projection does not erase the more precise analysis verdict and does not
promote a candidate to verified evidence.

The patch validator checks this projection across all three fields. Each result
reference carries exactly one `analysis_status` for the bounded claim assessment;
conflicting run-level observations remain visible in the report and evidence note.
An enum-valid but contradictory status combination is invalid, including an
otherwise `supported` claim paired with `contradictory` result evidence.

## 4. Analyze failures and ablations

Cluster symptoms by run/configuration and keep multiple live causes. Separate data,
optimization, implementation, evaluation, stochastic, and capacity/compute causes.
For ablations, distinguish necessity, sufficiency, interaction, and sensitivity.
Removal effects alone do not establish mechanism.

## 5. Choose next checks

Prefer checks that separate the most consequential live explanations, repair a
protocol blocker, or test a central claim at reasonable cost. State required controls,
artifacts, decision rule, and what each possible result would resolve.

Disclose post-hoc analysis and do not rewrite original thresholds after seeing data.
