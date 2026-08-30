# Improvement changelog

| Stage | What we tried & why | Evidence | Decision / Learning |
|---|---|---|---|
| Baseline | Single general-purpose model evaluates each case | Frozen `results/baseline-gemini.json`; Phase 2 replay: Recall@3 1.000, 9 false positives, review burden 23, full-recall burden 14, shortlist precision 0.608696 | Establish the frozen starting point; tag `phase1-gemini-baseline` and hash-guard all six artifacts |
| V0-top3 control | Deterministically truncate retained V0 rankings to at most three candidates, with no model call, to test whether shortlist capping alone explains V1's false-positive reduction | `results/v0-top3-control.json`: all V0 cases already returned at most three candidates; predictions and all requested metrics are identical to V0; 9 false positives, review burden 23, shortlist precision 0.608696 | Truncation alone explains 0 of the 7 V0→V1 false-positive reductions (0%). The control does not equalize total review burden because V0 already obeyed the cap. |
| V1 | Deterministic normalization and exact frozen-evidence retrieval before one prioritization call, to reduce unsupported/noisy review candidates | `results/evidence-grounded-v1.json`: Recall@3 1.000, 2 false positives, review burden 16, full-recall burden 14, shortlist precision 0.875000, claim support precision 1.000 | Earned its complexity relative to V0-top3: same Recall@3, 7 fewer false positives/review items, and +0.266304 shortlist precision. This advantage belongs to the complete V1 pipeline comparison; the control does not isolate retrieval from its changed model, prompt, and selection behavior. |
| V2 | Independent verification of every V1 material claim, followed by deterministic safe report assembly, to remove weak claims without reprioritizing | `results/verified-v2.json`: Recall@3 1.000, 2 false positives, review burden 16, claim support precision 1.000; mean runtime 5.601s and 69,517 total system tokens | Did not earn incremental complexity: it matched V1 shortlist quality while adding runtime/tokens. Preserve the artifact, but do not retain V2 as the active shortlist stage. |
| V3 conflict arbitration | Hypothesis: candidate-level arbitration over evidence direction, strength, and semantic dimension can remove contextually weak/conflicted V1 candidates without suppressing relevant variants. Implementation: frozen deterministic `conflict_arbitration_v1`, no added model calls, no candidate promotion/reordering. | Regression `benchmark_v1`: Recall@3 1.000→0.909, FP 2→2, burden 16→14; `GT-004` loses both relevant candidates. Held-out conflict: Recall@3 1.000→1.000, FP 4→0, burden 17→13, shortlist precision 0.764706→1.000000. See `results/phase3/COMPARISON.md` and `results/phase3/failures.jsonl`. | **Revise, not global default.** It earns minimal deterministic complexity on explicitly dimensioned conflict evidence, but fails backward-compatible recall. The frozen policy is not tuned post hoc; a revised policy must be V3.1 and separately preregistered. |
| Public benchmark | Test V1/V3 generalization on a separately frozen real-public ClinVar subset rather than invented loci. Ten cases/30 candidates were selected and labeled deterministically before model prediction; exact VCV versions and provenance are retained. | Public V1→V3: Recall@3 1.000→1.000, FP 1→0, burden 11→10, shortlist precision 0.909091→1.000000, claim support precision 0.954545→1.000000. Label mix: five single-submitter, four multiple-submitter/no-conflict, one expert-panel relevant record. | Useful evidence of performance on this fixed public proxy benchmark, not proof of clinical validity or universal generalization. Keep the track and broaden independent curation/review tiers before stronger claims. |

## Phase 2 failure trajectory

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

## Phase 3 failure trajectory

V3 introduced no new false positives on any track. Three structured failures remain:

- `benchmark_v1 / GT-004`: V3 removed both relevant candidates because each had
  support score 2, below the preregistered threshold 3. The empty shortlist causes
  Recall@3 to fall and makes full-recall burden unavailable.
- `benchmark_v1 / GT-007`: irrelevant `GT007-V2` survives as conflicted evidence.
- `benchmark_v1 / GT-012`: irrelevant `GT012-V3` survives as conflicted evidence.

The latter two expose schema-transfer limits: legacy records default semantic
dimension to `other`, so deterministic arbitration cannot recover missing context.
Exact scores, rules, ranks, and evidence IDs are in
`results/phase3/failures.jsonl`.

The current stopping decision is to revise evidence-strength/dimension calibration.
No Phase 4 or quantum iteration is claimed or implemented.
