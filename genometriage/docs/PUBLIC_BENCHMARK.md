# Public benchmark provenance

**For research/expert review. Not a medical diagnosis.** ClinVar assertions are
submitted and aggregated public evidence; they are not autonomous clinical
decisions and require qualified expert interpretation.

## Frozen source

`benchmark_public_v1` is a separate real-public-data track. It does not map the
synthetic benchmark loci to ClinVar.

- Source: NCBI ClinVar through E-utilities `esearch` and JSON `esummary`.
- Retrieval time: `2026-08-29T13:58:31+00:00`.
- Snapshot identity: `clinvar_eutils_public_v1`.
- Versioning: every selected record retains its exact versioned VCV accession.
- Local source pool: 30 fixed gene/category queries (three categories for each of
  10 genes), capped at 60 identifiers per query before deterministic filtering.
- Evaluation dependency: none. The source pool, selected records, cases, labels,
  and evidence are all retained locally.
- Transformation: `scripts/build_public_benchmark.py`; no model is involved.

The relevant NCBI pages are the ClinVar
[access and attribution guidance](https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/),
[review-status definitions](https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/),
and [download documentation](https://www.ncbi.nlm.nih.gov/clinvar/docs/downloads/).
The snapshot manifest preserves these URLs. Users should consult the current NCBI
guidance for downstream reuse and retain ClinVar attribution and disclaimers.

No private records, raw patient genomes, or patient-identifiable information are
included. The retained data are public aggregate records.

## Benchmark construction

The benchmark contains 10 cases and 30 real GRCh38 SNVs: three candidates per
case across `APC`, `BRCA1`, `BRCA2`, `CFTR`, `LDLR`, `MLH1`, `MSH2`, `MYH7`,
`PAH`, and `TP53`. Each case contains one independently selected relevant record,
one benign/likely-benign decoy, and one ambiguous-evidence decoy. The evidence
snapshot contains 90 provenance-rich records.

Candidate filtering requires a current GRCh38 SNV, one represented gene, and
ClinVar traits. For each fixed gene, the evaluator label was constructed before
model evaluation:

1. Select records classified Pathogenic, Likely pathogenic, or their combined
   category with at least `criteria provided` aggregate review.
2. Prefer the highest available review tier in the fixed query pool.
3. Break ties deterministically by the lowest numeric Variation ID.
4. Use that selected record's ClinVar trait set as the model-visible target context.
5. Select benign and ambiguous decoys deterministically, preferring trait overlap,
   then review rank, then Variation ID.

The 10 relevant labels include five single-submitter records with criteria, four
multiple-submitter/no-conflict records, and one expert-panel record. This mix is an
important limitation: the benchmark's labels are a reproducible ClinVar-metadata
proxy for expert attention, not an independently adjudicated clinical truth set.
The fixed recent query pool did not provide high-review SNVs for every selected
gene, so the preregistered minimum was one-star/criteria-provided review.

## Separation and leakage controls

Model-visible cases live in `data/cases/benchmark_public_v1.jsonl`; evaluator-only
labels live in `data/ground_truth/benchmark_public_v1_ground_truth.jsonl`.
System runners load only cases and the frozen evidence store. Tests reconstruct
both artifacts from the retained source pool, reject malformed or duplicate
variants, check that answer fields are absent from model input, and verify all
freeze hashes.

The benchmark, labels, source snapshot, evidence snapshot, and transformation
script were frozen before final V1/V3 prediction. Freeze tag:
`benchmark-public-v1-freeze` at commit `b6a3fde`.

## SHA-256 freeze

| Artifact | SHA-256 |
|---|---|
| Model-visible cases | `fb5cdeaa164919948a301a409ed4ffcfc88052bfa7d1edd0b6a63d1a3223c74b` |
| Evaluator labels | `792f2fd0565a8178557869e5193a84d9b7f76ab93450cb44d77460d83af8c6fb` |
| Raw query pool | `68fb52036c9c57a2b47875ba621cf4e136733b4b5617ce82075f4acdcf5817a1` |
| Selected records | `9274d6865b3cd3887aa9f47c972412736d4977bcfce2bf6ade65ab8691e91e92` |
| Source manifest | `1b435bf8ddeac68f508bef9a4779c8726616414bf4d30566e80b43cdf24bb25c` |
| Evidence JSONL | `9e08a12746f9d60425217f6b0b9822129ca3cbdfe3d9f377f37b654fdbcd5f73` |
| Evidence manifest | `ec44d259475cda4fdc64c2a4bacf2c6e7f5e5efcbaf4748ea052c6db748e4a4c` |
| Transformation script | `6f0a61b96af7e0c000bb8114efc35ab1242a8f27f38ba8a85607996600dc4739` |

The machine-readable source and freeze manifests are authoritative.

## Reproduction

Read-only validation:

```powershell
.\.venv\Scripts\python.exe scripts\build_public_benchmark.py validate
.\.venv\Scripts\python.exe scripts\validate_phase3_freezes.py
```

Offline reconstruction from the retained query pool is deterministic, but it
rewrites the derived frozen files and should be run only in a clean disposable
checkout:

```powershell
.\.venv\Scripts\python.exe scripts\build_public_benchmark.py rebuild
.\.venv\Scripts\python.exe scripts\build_public_benchmark.py validate
```

`fetch` performs a new live retrieval and therefore creates a new candidate
snapshot; it is not a reproduction of `benchmark_public_v1` and must not replace
the frozen artifacts under the same version.
