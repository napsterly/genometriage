# Architecture

The repository implements the benchmark-first V0/V1/V2 experiments and the
preregistered deterministic V3 conflict-arbitration experiment. It does not
implement broad multi-agent orchestration, memory, autonomous clinical decisions,
or quantum functionality.

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
                            ├── V2 independent verification
                            │        │
                            │ deterministic safe finalization
                            │        │
                            │ expert-review output
                            │
                            └── V3 deterministic conflict arbitration
                                     │
                               audit states + filtered shortlist
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
- V3 receives a completed V1 run and the same frozen evidence records. Its frozen
  rules operate on structured direction, strength, and semantic dimension. It can
  retain or remove a V1 candidate but cannot add, promote, or reorder one.
- V3 records `retain`, `deprioritize`, `insufficient_evidence`, or
  `conflicting_evidence` plus scores, cited evidence IDs, and the exact fired rule.
  Conflict remains visible to expert review rather than being silently converted
  into certainty.
- Ground truth is a software separation boundary rather than a defense against a
  malicious process with repository access. Evaluation loads it only after a raw
  `SystemRun` exists.

Runs checkpoint atomically after each case. Resume validation binds benchmark,
prompt, exact model, evidence snapshot, execution configuration, and source V1 run
for V2/V3. Evaluation rejects in-progress checkpoints. V3 performs only local
deterministic work; retained model-call, token, cost, and external-runtime values
are inherited from its V1 source so complete-pipeline comparisons count them once.

## Benchmark tracks

- `benchmark_v1`: frozen synthetic regression track only.
- `benchmark_conflict_v1`: 13 held-out synthetic conflict-heavy cases, frozen
  before the arbitration specification.
- `benchmark_public_v1`: 10 cases built from a pinned local ClinVar E-utilities
  subset. It uses real public GRCh38 loci and never reuses synthetic loci.

Every track stores model-visible cases and evaluator-only labels in separate files.
Conflict/public freeze manifests bind inputs, labels, source/evidence artifacts,
and transformation scripts by SHA-256. Evaluation has no live web dependency.

## Deterministic normalization scope

The normalizer supports benchmark-required VCF 4.x records with at least the first
eight tab-separated columns, literal A/C/G/T/N alleles, and multiallelic splitting.
It removes `chr`, uppercases alleles, and trims shared prefix/suffix sequence while
preserving an anchor. Symbolic alleles, breakends, and missing alleles are rejected.
Reference-backed repeat left-alignment is deliberately out of scope and is never
approximated by an LLM.

## Stop condition

The repository stops at V3. V2 remains as a measured but non-retained experimental
stage because it added cost without shortlist benefit. V3 remains experimental and
is not the global default because it failed the legacy recall constraint. No
Phase 4, quantum, or broad agent architecture is implemented.
