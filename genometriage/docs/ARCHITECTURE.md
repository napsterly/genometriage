# Architecture

Phase 2 implements only the evidence-grounding and claim-verification experiment.
It does not implement broad multi-agent orchestration, memory, autonomous clinical
decisions, or quantum functionality.

```text
model-visible case
      │
      ├── V0 ─────────────────────────────> one-call ranking
      │
      └── deterministic normalization
                 │
        exact local evidence retrieval
                 │
                 └── V1 prioritization ───> shortlist + typed claims
                                                  │
                                      V2 independent verification
                                                  │
                                      deterministic safe finalization
                                                  │
                                      expert-review output

sealed ground truth ─────────────────────────────> evaluator only
```

## Boundaries

- Parsing, chromosome/allele normalization, exact retrieval, hash validation,
  claim-ID assignment, shortlist filtering, metrics, and report assembly are code.
- V1 receives context, normalized candidate metadata, and only exact evidence records
  retrieved for each candidate. It never receives ground truth.
- V2 receives V1 claims and their cited frozen evidence. It verifies every claim
  exactly once and cannot add or reorder variants.
- A V2 claim marked contradicted or insufficient is retained only as an explicitly
  typed non-established claim; deterministic final reasons use supported retaining
  claims only.
- Ground truth is a software separation boundary rather than a defense against a
  malicious process with repository access. Evaluation loads it only after a raw
  `SystemRun` exists.

Runs checkpoint atomically after each case. Resume validation binds benchmark,
prompt, exact model, evidence snapshot, execution configuration, and source V1 run
for V2. Evaluation rejects in-progress checkpoints.

## Deterministic normalization scope

The normalizer supports benchmark-required VCF 4.x records with at least the first
eight tab-separated columns, literal A/C/G/T/N alleles, and multiallelic splitting.
It removes `chr`, uppercases alleles, and trims shared prefix/suffix sequence while
preserving an anchor. Symbolic alleles, breakends, and missing alleles are rejected.
Reference-backed repeat left-alignment is deliberately out of scope and is never
approximated by an LLM.

## Stop condition

The repository stops at V2. Interfaces for later annotation, public-resource
adapters, conflict handling, and reports remain narrow extension points; they are
not speculative implementations.
