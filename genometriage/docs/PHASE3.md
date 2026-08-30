# Phase 3: generalization and conflict arbitration

**For research/expert review. Not a medical diagnosis.**

Phase 3 asks whether the complete V1 evidence-grounded pipeline generalizes to
unseen conflict-heavy synthetic cases and pinned real public genomic evidence, and
whether a preregistered deterministic arbitration stage can safely reduce review
burden. It does not implement broad multi-agent orchestration or quantum methods.

## Experimental order and freezes

1. Phase 2 was committed and tagged `phase2-evidence-grounding` at
   `d61c8fda411a3369444a6e2a95e853d3ad328d3c`.
2. `benchmark_conflict_v1` was created before the arbitration policy, committed at
   `e5b91d0a0b2ee4745866322c886b4085b29129d8`, and tagged
   `benchmark-conflict-v1-freeze`.
3. `conflict_arbitration_v1` was specified and hashed before V3 evaluation, then
   tagged `conflict-arbitration-v1-freeze` at `cd5ab07`.
4. `benchmark_public_v1` and all labels/source/evidence artifacts were frozen
   before final predictions, tagged `benchmark-public-v1-freeze` at `b6a3fde`.

No arbitration rule was changed after evaluation. A changed policy must receive a
new version such as V3.1.

## Held-out conflict benchmark

`benchmark_conflict_v1` has 13 fully synthetic cases, 52 candidates, 11 positive
cases, two negative controls, and 82 evidence records. It stresses combinations of
molecular support with phenotype or inheritance mismatch, partial phenotype fit,
conflicting evidence, incomplete penetrance, regulatory/noncoding evidence,
stronger counterevidence, inheritance decoys, multiple plausible candidates, and
insufficient evidence. Its loci and scenarios are not renamed copies of the two
legacy V1 false positives.

The model-visible case hash is
`2dce889f428c2662ba5a26dbae227212f87be7023eec87bfb0f2c4efa4809aae`;
the local evidence hash is
`ba2554f5b52b84a0683f7fc467c0c13263ff5fc9b8b754fa6045d7e2867dd887`.
Ground truth remains in a separate evaluator-only file.

## Preregistered V3 policy

The frozen policy is `docs/CONFLICT_ARBITRATION_SPEC.md`, SHA-256
`73e1479cbfaac7bc671dbe147e396695397669b49259ca68e1a14158d3080a98`.
It assigns weak/moderate/strong weights 1/2/3 and evaluates rules in fixed order:

1. no directional evidence → `insufficient_evidence`;
2. counterevidence only → `deprioritize`;
3. strong phenotype/inheritance/context counterevidence at least as strong as
   support → `deprioritize`;
4. counterevidence exceeds support by at least two → `deprioritize`;
5. support below three → `insufficient_evidence`;
6. remaining material counterevidence or uncertainty → `conflicting_evidence`;
7. otherwise → `retain`.

`retain` and `conflicting_evidence` stay in their existing V1 order;
`deprioritize` and `insufficient_evidence` are removed. V3 cannot introduce or
promote a candidate, preserves a per-candidate audit trail, and makes zero extra
model calls.

## Result

| Track | System | Recall@3 | Shortlist precision | False positives | Review burden | Full-recall burden |
|---|---|---:|---:|---:|---:|---:|
| Frozen `benchmark_v1` regression | V1 | 1.000000 | 0.875000 | 2 | 16 | 14 |
| Frozen `benchmark_v1` regression | V3 | 0.909091 | 0.857143 | 2 | 14 | unavailable |
| Held-out conflict | V1 | 1.000000 | 0.764706 | 4 | 17 | 13 |
| Held-out conflict | V3 | 1.000000 | 1.000000 | 0 | 13 | 13 |
| Public | V1 | 1.000000 | 0.909091 | 1 | 11 | 10 |
| Public | V3 | 1.000000 | 1.000000 | 0 | 10 | 10 |

On the held-out conflict track V3 removes all four false positives without losing
recall. On the public track it removes the one false positive without losing
recall. However, it removes both relevant candidates in legacy case `GT-004`, so
the regression Recall@3 constraint fails. Lower legacy burden is therefore not an
improvement.

The inverse generalization gap—better V3 results on new tracks than on the legacy
track—indicates schema-transfer sensitivity. New evidence has explicit dimensions;
legacy evidence defaults to `other`. It is not evidence of universal clinical
generalization.

## Complexity decision and failure mode

Decision: **revise; do not make V3 the global default**. Its deterministic runtime
overhead is below one millisecond per case in these retained runs and it adds no
tokens or model calls, so it earns its small complexity on explicitly dimensioned
evidence. It does not earn unconditional deployment because backward-compatible
recall regressed.

The clearest remaining bottleneck is evidence-strength and semantic-dimension
calibration across evidence schemas. The frozen minimum-support threshold removes
relevant legacy evidence that sums to two, while missing dimensions prevent V3
from resolving two legacy false positives. Structured trajectories are retained in
`results/phase3/failures.jsonl`.

Quantum functionality is not recommended. The measured bottleneck is evidence
calibration/schema transfer, not a demonstrated combinatorial optimization limit.
If a future shortlist constraint is formally specified, compare a classical
constrained optimizer first in a separately preregistered experiment.
