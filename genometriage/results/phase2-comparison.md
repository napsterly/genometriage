# GenomeTriage Phase 2 comparison

**For research/expert review. Not a medical diagnosis.**

| Metric | V0 | V0-top3 | V1 | V2 |
|---|---:|---:|---:|---:|
| Recall@1 | 0.863636 | 0.863636 | 0.863636 | 0.863636 |
| Recall@3 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| Recall@5 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| Precision@5 | 0.233333 | 0.233333 | 0.233333 | 0.233333 |
| Shortlist precision | 0.608696 | 0.608696 | 0.875000 | 0.875000 |
| MRR | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| False positives | 9 | 9 | 2 | 2 |
| False positives per case | 0.750000 | 0.750000 | 0.166667 | 0.166667 |
| Review burden | 23 | 23 | 16 | 16 |
| Review burden at full recall | 14 | 14 | 14 | 14 |
| Citation traceability error | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| Claim support precision | n/a | n/a | 1.000000 | 1.000000 |
| Recall@3 constraint met | True | True | True | True |
| Runtime (mean seconds/case) | 2.321434 | 2.321434 | 2.522389 | 5.601468 |
| Tokens (total) | 23275 | 23275 | 42826 | 69517 |
| Cost (total USD) | 0.000000 | 0.000000 | 0.000000 | 0.000000 |

## V0 → V0-top3 → V1 attribution

- Truncation alone removed 0 false positives (0.0% of the total reduction).
- V1 removed an additional 7 false positives (100.0% of the total reduction).
- V0 already returned at most three variants per case, so the top-3 control is prediction-identical to V0.
- Control runtime/tokens are inherited V0 generation accounting; creating the control made no model call.
- After the control, V1 keeps Recall@3 unchanged, returns 7 fewer false positives/review items, and raises shortlist precision by 0.266304.

Causal scope: The top-3 control rules out simple rank-list truncation as the source of the observed reduction. The remaining difference is attributable to the complete V1 pipeline comparison, not uniquely to retrieval: V1 also changes the model, prompt, and selection behavior.

## Complexity verdict

- V1: Preserved Recall@3 while reducing false positives and review burden relative to the V0 top-3 control.
- V2: Matched V1 shortlist quality while adding runtime and tokens; no measured incremental benefit.

All values come from retained machine-readable evaluation artifacts; unavailable values are shown as `n/a`.
