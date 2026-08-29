# Benchmark v1

The benchmark contains 12 fully synthetic cases. The genes, positions, alleles, evidence statements, contexts, and labels are inventions; `GRCh38-synthetic` means only that the fixture shape resembles normalized GRCh38 records. It does not identify a real locus or person.

Model-visible input is in `data/cases/benchmark_v1.jsonl`. Evaluator-only labels and rationales are in `data/ground_truth/benchmark_v1_ground_truth.jsonl`. The baseline package imports only `load_cases`; label loading happens in the evaluation layer after predictions exist.

## Coverage

| Case | Design intent | Label class |
|---|---|---|
| GT-001 | de novo dominant signal among noise | straightforward |
| GT-002 | homozygous recessive truncation | straightforward |
| GT-003 | splice evidence among eight candidates | moderate |
| GT-004 | two incompletely supported candidates | ambiguous |
| GT-005 | strong functional evidence conflict | conflicting |
| GT-006 | phased compound-heterozygous pair | challenging |
| GT-007 | dramatic consequence with phenotype mismatch | moderate |
| GT-008 | possible low-fraction mosaic requiring confirmation | ambiguous |
| GT-009 | regulatory candidate among coding decoys | challenging |
| GT-010 | no relevant candidate / abstention control | moderate |
| GT-011 | inheritance-model reasoning with truncating decoy | moderate |
| GT-012 | pair, penetrance conflict, conditional assay, strong decoy | challenging |

The hidden label is “should receive expert attention,” not “is pathogenic.” Conflicting and uncertain candidates can therefore be relevant when the safe action is to escalate them for review.

## Integrity rules

- Case and truth IDs must match exactly.
- Every relevant variant must exist in its visible case.
- Every rationale must exactly cover the relevant label set.
- Every rationale source ID must exist in the visible evidence records.
- Visible top-level records cannot contain evaluator-only answer fields.
- Candidate coordinates, variant IDs, and case evidence IDs must be unique.

