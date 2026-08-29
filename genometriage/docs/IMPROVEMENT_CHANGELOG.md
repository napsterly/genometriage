# Improvement changelog

| Stage | What we tried & why | Evidence | Decision / Learning |
|---|---|---|---|
| Baseline | Single general-purpose model evaluates each case | Frozen `results/baseline-gemini.json`; Phase 2 replay: Recall@3 1.000, 9 false positives, review burden 23, full-recall burden 14, shortlist precision 0.608696 | Establish the frozen starting point; tag `phase1-gemini-baseline` and hash-guard all six artifacts |
| V0-top3 control | Deterministically truncate retained V0 rankings to at most three candidates, with no model call, to test whether shortlist capping alone explains V1's false-positive reduction | `results/v0-top3-control.json`: all V0 cases already returned at most three candidates; predictions and all requested metrics are identical to V0; 9 false positives, review burden 23, shortlist precision 0.608696 | Truncation alone explains 0 of the 7 V0→V1 false-positive reductions (0%). The control does not equalize total review burden because V0 already obeyed the cap. |
| V1 | Deterministic normalization and exact frozen-evidence retrieval before one prioritization call, to reduce unsupported/noisy review candidates | `results/evidence-grounded-v1.json`: Recall@3 1.000, 2 false positives, review burden 16, full-recall burden 14, shortlist precision 0.875000, claim support precision 1.000 | Earned its complexity relative to V0-top3: same Recall@3, 7 fewer false positives/review items, and +0.266304 shortlist precision. This advantage belongs to the complete V1 pipeline comparison; the control does not isolate retrieval from its changed model, prompt, and selection behavior. |
| V2 | Independent verification of every V1 material claim, followed by deterministic safe report assembly, to remove weak claims without reprioritizing | `results/verified-v2.json`: Recall@3 1.000, 2 false positives, review burden 16, claim support precision 1.000; mean runtime 5.601s and 69,517 total system tokens | Did not earn incremental complexity on this benchmark: it matched V1 quality while adding runtime and tokens |

## Failure trajectory

No V1/V2 transition removed a true positive, introduced a new false positive,
contradicted evaluator-supported evidence, or failed from missing evidence. Two
residual false positives remained in both V1 and V2:

- `GT-007 / GT007-V2`: ranks 2 → 2 → 2 (V0/V1/V2).
- `GT-012 / GT012-V3`: ranks 3 → 3 → 3.

Both combined a supported truncation claim with strong phenotype-mismatch
counterevidence. Verification correctly supported both factual claims, but a
verification-only stage cannot by itself arbitrate candidate-level conflict. The
exact machine-readable trajectories are in
`results/phase2-failure-analysis.json`.

No later iteration is claimed or invented here.
