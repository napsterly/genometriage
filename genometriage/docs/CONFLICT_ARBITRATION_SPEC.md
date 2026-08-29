# GenomeTriage Conflict Arbitration Specification

Status: preregistered and frozen before V3 evaluation  
Policy version: `conflict_arbitration_v1`  
System version: `conflict-arbitrated-v3`  
Date: 2026-08-29  

## Purpose and scope

This policy is a transparent research-evaluation rule for candidate-level evidence conflict. It is not an ACMG/AMP classification implementation, diagnosis, treatment recommendation, or substitute for qualified review.

V3 consumes the ranked candidates produced by the frozen V1 evidence-grounded pipeline. It may retain or remove a V1 candidate, but it may not introduce a candidate that V1 did not return and may not change V1 ordering among retained candidates. It reads only the candidate's deterministically retrieved, frozen evidence records. Ground truth is never available to the policy.

Every report must display:

`For research/expert review. Not a medical diagnosis.`

## Structured inputs

Each unique evidence record has:

- an evidence identifier and provenance;
- a direction: `supports`, `against`, or `uncertain`;
- a strength: `weak`, `moderate`, or `strong`;
- a dimension: `molecular`, `functional`, `regulatory`, `phenotype_context`, `inheritance`, `population`, `provenance`, or `other`.

Records are deduplicated by evidence identifier. A duplicate identifier with non-identical content is an input error. Missing direction, strength, identifier, provenance, or dimension is a malformed input error; legacy Phase 2 records receive the schema default dimension `other` without changing their frozen bytes.

V3 does not infer new genomic facts, reclassify evidence strength, inspect ground truth, or search the web. Evidence text is retained for expert display but is not semantically reinterpreted by the deterministic policy.

## Scoring

Strength weights are fixed:

| Strength | Weight |
| --- | ---: |
| weak | 1 |
| moderate | 2 |
| strong | 3 |

For one candidate:

- `support_score` is the sum of weights for `supports` records.
- `counter_score` is the sum of weights for `against` records.
- `uncertainty_score` is the sum of weights for `uncertain` records.
- A `contextual_strong_counter` exists when at least one `strong` `against` record has dimension `phenotype_context`, `inheritance`, `population`, or `provenance`.

Scores are bookkeeping aids, not clinical pathogenicity scores.

## State decision, in exact precedence order

The first matching rule is final:

1. **Insufficient evidence:** if `support_score == 0` and `counter_score == 0`, assign `insufficient_evidence`.
2. **Counterevidence only:** if `support_score == 0` and `counter_score > 0`, assign `deprioritize`.
3. **Contextual strong counter:** if `contextual_strong_counter` is true and `counter_score >= support_score`, assign `deprioritize`.
4. **Aggregate counter dominance:** if `counter_score >= support_score + 2`, assign `deprioritize`.
5. **Below support threshold:** if `support_score < 3`, assign `insufficient_evidence`.
6. **Material conflict or uncertainty:** if `counter_score > 0` or `uncertainty_score > 0`, assign `conflicting_evidence`.
7. **Unopposed support:** otherwise assign `retain`.

The fixed support threshold of 3 means either one strong record or multiple weaker records with a combined weight of at least 3 is needed to survive arbitration.

## Shortlist and reporting behavior

- `retain` and `conflicting_evidence` candidates remain in the final shortlist.
- `deprioritize` and `insufficient_evidence` candidates are removed from the final shortlist but remain in the arbitration audit trail.
- Retained candidates keep their relative V1 ranks and are renumbered contiguously.
- `conflicting_evidence` is never presented as settled fact; the report lists the supporting, counter, and uncertainty evidence IDs.
- `insufficient_evidence` is an explicit abstention. It is not converted to benign, irrelevant, or non-causal language.
- A material V1 claim survives as established only to the extent that its cited frozen evidence remains traceable. Arbitration does not semantically validate claim text and must not be reported as doing so.
- If every V1 candidate is removed, V3 returns an empty shortlist with an explicit abstention/escalation note rather than inventing a replacement.

## Determinism and audit record

For each V1 candidate, V3 records:

- candidate and source V1 rank;
- final state;
- support, counter, and uncertainty scores;
- all evidence IDs grouped by direction;
- contextual strong-counter evidence IDs;
- the numbered rule that fired;
- whether the candidate was retained for review.

Given identical V1 predictions, evidence snapshot, and policy version, output must be byte-stable apart from explicitly recorded timing/timestamp fields. V3 makes zero additional model calls; its model-call and token totals are inherited from its V1 source run, while arbitration runtime is recorded separately.

## Preregistered evaluation and success criteria

V1 and V3 will be compared separately on:

1. frozen `benchmark_v1` as a regression check;
2. sealed `benchmark_conflict_v1` as the primary held-out conflict test;
3. sealed `benchmark_public_v1` as the real-public-data generalization test.

V3 earns its complexity only if held-out results preserve strong relevant-variant recall while justified removals improve or preserve shortlist precision. A lower review burden accompanied by materially lower recall is a trade-off, not an improvement. Empty or unavailable metrics remain unavailable rather than being fabricated.

## Change control

This document and its SHA-256 freeze manifest are committed before V3 implementation or evaluation. No rule, threshold, dimension, or precedence change may be made after results are observed under this version. Any revision requires a new policy/system version (for example V3.1), a new freeze hash, and explicit reporting that V3.0 failed or exposed a new hypothesis.
