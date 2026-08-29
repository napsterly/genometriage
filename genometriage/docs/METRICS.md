# Metrics

The primary metric is Relevant Variant Recall@K. Default K values are 1, 3, and 5; K=5 is primary.

- **Recall@K:** number of labeled relevant variants in the first K ranks divided by all labeled relevant variants. It is null for negative controls and those cases are excluded from the macro mean. Failed positive cases score zero.
- **Precision@K:** number of labeled relevant variants in the first K ranks divided by K. This fixed denominator penalizes over-short, missed, and failed shortlists consistently.
- **MRR:** reciprocal rank of the first relevant candidate. Negative controls are excluded; positive misses and failed runs score zero.
- **False positives@K:** returned candidates in the first K ranks that are not labeled relevant.
- **Unsupported-claim rate:** a deliberately narrow automated proxy. Each ranked reason is unsupported if it cites no source ID, an unknown ID, or an ID belonging to a different candidate. This does not semantically verify the prose.
- **Sent for review:** returned candidates capped at primary K.
- **Runtime:** measured wall time around the provider request and response parsing for each completed case.
- **Estimated cost:** calculated only from actual provider token counts and caller-supplied input/output prices. It is null otherwise.

Macro aggregates include all 12 cases for precision and false positives. Recall and MRR include the 11 positive cases. Raw per-case values remain in the JSON artifact so alternate aggregation can be audited.

