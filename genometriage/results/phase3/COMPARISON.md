# GenomeTriage Phase 3 comparison

For research/expert review. Not a medical diagnosis.

V3 used the preregistered `conflict_arbitration_v1` policy and made zero additional model calls.

| Metric | benchmark_v1 V1 | benchmark_v1 V3 | conflict V1 | conflict V3 | public V1 | public V3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Recall@1 | 0.863636 | 0.818182 | 0.909091 | 0.909091 | 1.000000 | 1.000000 |
| Recall@3 | 1.000000 | 0.909091 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| Recall@5 | 1.000000 | 0.909091 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| MRR | 1.000000 | 0.909091 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| Shortlist precision | 0.875000 | 0.857143 | 0.764706 | 1.000000 | 0.909091 | 1.000000 |
| False positives | 2 | 2 | 4 | 0 | 1 | 0 |
| False positives/case | 0.166667 | 0.166667 | 0.307692 | 0.000000 | 0.100000 | 0.000000 |
| Review burden | 16 | 14 | 17 | 13 | 11 | 10 |
| Review burden/case | 1.333333 | 1.166667 | 1.307692 | 1.000000 | 1.100000 | 1.000000 |
| Review burden at full recall | 14 | n/a | 13 | 13 | 10 | 10 |
| Citation traceability error | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| Claim support precision | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 0.954545 | 1.000000 |
| Abstention cases | 1 | 2 | 2 | 2 | 0 | 0 |
| Insufficient-evidence candidates | 0 | 2 | 0 | 0 | 0 | 1 |
| Conflicting-evidence candidates | 0 | 5 | 0 | 4 | 0 | 0 |
| Mean runtime seconds | 2.522389 | 2.522663 | 2.694412 | 2.695083 | 2.682310 | 2.683070 |
| Mean deterministic seconds | n/a | 0.000274 | n/a | 0.000671 | n/a | 0.000760 |
| Mean external-model seconds | 2.522389 | 2.522389 | 2.694412 | 2.694412 | 2.682310 | 2.682310 |
| Total model calls | 12 | 12 | 13 | 13 | 10 | 10 |
| Model calls/case | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| Input tokens | 37755 | 37755 | 51602 | 51602 | 66417 | 66417 |
| Output tokens | 5071 | 5071 | 5930 | 5930 | 4392 | 4392 |
| Total tokens | 42826 | 42826 | 57532 | 57532 | 70809 | 70809 |
| Cost USD | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |

## Interpretation

- Regression: V3 reduced burden 16→14 but Recall@3 fell 1.000→0.909; this is a trade-off and fails the recall constraint.
- Held-out conflict: V3 preserved Recall@3=1.000, removed all four false positives, reduced burden 17→13, and improved shortlist precision 0.764706→1.000000.
- Public: V3 preserved Recall@3=1.000, removed the sole false positive, reduced burden 11→10, and improved shortlist precision 0.909091→1.000000.
- V3 therefore earns its small deterministic complexity on evidence with explicit dimensions, but not as a global replacement for V1 because legacy-evidence recall regressed.

## Generalization gap

The held-out and public tracks did not degrade V1/V3 recall. V3 actually performed better there than on `benchmark_v1`; this inverse gap is evidence of schema-transfer sensitivity, not proof of universal generalization. The legacy track defaults evidence dimension to `other`, while the new tracks contain explicit context/provenance dimensions.

## Failure analysis

Structured failures: `results/phase3/failures.jsonl`. Failure cases recorded: 3.

The clearest failure is GT-004: both relevant V1 candidates had support score 2 and were removed by the fixed minimum-support rule, producing an empty shortlist. Two legacy false positives also survive because arbitration cannot recover missing semantic dimensions from records defaulted to `other`.

## Decision and next experiment

revise_not_global_default: V3 earned its small deterministic complexity on dimensioned held-out/public tracks, but failed backward-compatible recall.

Remaining bottleneck: Evidence-strength and dimension calibration does not transfer safely between legacy untyped evidence and newer structured/public evidence.

Quantum recommendation: Do not implement quantum functionality. The observed bottleneck is evidence calibration and schema transfer, not a demonstrated combinatorial optimization limit. If a future shortlist-selection constraint is formalized, benchmark a classical constrained optimizer before considering a separate quantum experiment.
