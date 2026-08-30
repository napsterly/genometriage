# Architecture

The repository implements the benchmark-first V0/V1/V2 experiments, the
preregistered deterministic V3 conflict-arbitration experiment, and a Phase 4
judge-facing product layer. It does not implement broad multi-agent orchestration,
memory, autonomous clinical decisions, or quantum functionality.

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

The product/default path ends at V1. V2 is a preserved non-retained experiment,
and V3 remains experimental because it failed the legacy recall constraint. The
offline web app visualizes retained artifacts; it does not create a new research
architecture or rerun a model.

```text
built-in case ──> recorded V1 artifact ──> Judge Mode explanation
custom JSON/VCF ──> deterministic normalization only

evaluator-only ground truth ──> dashboard aggregation only
                             (never loaded by normal product case APIs)
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
- Judge Mode's built-in outputs are labeled `Recorded benchmark execution /
  deterministic replay`. The product repository loads cases, evidence, prediction,
  and aggregate result artifacts but never ground-truth files.
- Custom JSON/VCF input is size- and schema-bounded, deterministically normalized,
  and explicitly stops before ranking. The offline app never fabricates a model
  response for unseen input.
- The standard-library HTTP server binds to `127.0.0.1` by default, serves a fixed
  static allowlist, applies response security headers, and exposes no credential or
  live-provider endpoint.

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

## Phase 4 product boundary and stop condition

Phase 4 packages the retained evidence-grounded V1 workflow into an offline judge
demo, evaluation dashboard, representative trajectories, and submission
documentation. It adds no model calls, evidence sources, benchmark tuning, or new
ranking policy. V2 remains non-retained because it added cost without shortlist
benefit. V3 remains experimental and is not the global default because it failed
the legacy recall constraint.

The project stops here. No Phase 5, quantum functionality, broad agent
orchestration, autonomous diagnosis, treatment recommendation, or clinical
decision path is implemented.
