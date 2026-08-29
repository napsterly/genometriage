# Evidence snapshot

`evidence_v1` is a frozen local JSONL snapshot with 53 records. Every record carries
an evidence ID, source label, original fixture record ID, snapshot version/date,
structured direction/statement/strength, exact canonical variant ID, source fixture
hash, case/variant provenance, and deterministic extraction method.

All records are fully synthetic. The benchmark's genes and coordinates are invented,
so linking them to real ClinVar records would create false biological provenance.
Instead, the builder extracts only model-visible synthetic evidence and explicitly
states that the records are not ClinVar records. It never opens the ground-truth
fixture and benchmark execution never uses live web results.

This layout follows public-resource provenance conventions so a later, separately
benchmarked adapter can use real public evidence where loci are real. ClinVar uses
versioned SCV/RCV/VCV accessions and Variation IDs, provides downloadable archives,
and updates live/downloaded data regularly; a benchmark must therefore pin an
archive or local snapshot rather than query mutable live results.

Authoritative references:

- [ClinVar access and update cadence](https://www.ncbi.nlm.nih.gov/clinvar/docs/access/)
- [ClinVar identifiers](https://www.ncbi.nlm.nih.gov/clinvar/docs/identifiers/)
- [ClinVar data use and monthly archives](https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/)
- [GA4GH VCF specifications](https://samtools.github.io/hts-specs/)

Rebuild and validate:

```powershell
.\.venv\Scripts\python.exe -m genometriage.evidence.build
.\.venv\Scripts\python.exe -m pytest tests/test_evidence_store.py tests/test_normalization.py -q
```

The manifest records the evidence hash, source fixture hash, record count, and
`external_live_dependency: false`.
