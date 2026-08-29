# Metrics

The central safety constraint is `Recall@3 >= frozen V0 Recall@3`, where the frozen
threshold is 1.0. Lower review burden is never called an improvement when this
constraint fails. K values 1, 3, and 5 remain available for historical comparison;
primary shortlist accounting uses K=5.

- **Relevant Variant Recall@K:** relevant variants in the first K ranks divided by
  all evaluator-labeled relevant variants. Negative controls are null and excluded
  from the macro mean; failed positive cases score zero.
- **Precision@K:** relevant variants in the first K ranks divided by fixed K. A
  shorter shortlist therefore does not increase historical Precision@5 by itself.
- **Shortlist precision:** total evaluator-labeled relevant returned variants divided
  by total returned variants across all cases. This micro-average uses the actual
  shortlist denominator and is reported separately from unchanged Precision@K.
- **MRR:** reciprocal rank of the first relevant candidate. Negative controls are
  excluded; misses score zero.
- **False positives@K:** returned candidates in the first K ranks that are not
  evaluator-labeled relevant.
- **Review burden:** total candidates returned in the primary-K expert shortlist.
- **False positives per case:** primary-K false positives divided by all 12 cases.
- **Review burden at full recall:** the sum of each case's smallest ranked prefix
  containing all relevant variants. It is null if any relevant variant is missing;
  a negative control contributes zero.
- **Recall constraint:** whether Recall@3 is at least 1.0.
- **Citation traceability error rate:** the historical evidence-ID proxy, renamed
  clearly. A ranked reason is an error if citations are absent, unknown, or belong
  to another candidate. The old `unsupported_claim_rate` field remains an identical
  alias so V0 parses unchanged.
- **Claim Support Precision:** among typed claims the system labels supported, the
  proportion whose cited structured evidence directions support the declared claim
  interpretation. This semantically checks support/against/uncertainty direction;
  it is separate from identifier validity and null when no supported typed claims
  exist.
- **Runtime:** mean per-case wall time. V2 includes its inherited V1 runtime plus
  verifier runtime so system-level cost is comparable.
- **Tokens:** retained provider input/output/total usage. V2 includes V1 plus V2.
- **Estimated cost:** calculated only from retained token usage and explicitly
  supplied rates. Missing rates produce null; confirmed free-tier zero rates produce
  zero.

Macro recall and MRR cover the 11 positive cases. Precision and false-positive
aggregates include all 12 cases. Every per-case value is retained in result JSON.
