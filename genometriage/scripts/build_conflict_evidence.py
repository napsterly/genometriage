"""Build the offline evidence snapshot for sealed benchmark_conflict_v1."""

from __future__ import annotations

from pathlib import Path

from genometriage.evidence import build_case_evidence_snapshot


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "cases" / "benchmark_conflict_v1.jsonl"
EVIDENCE = ROOT / "data" / "evidence" / "evidence_conflict_v1.jsonl"
MANIFEST = ROOT / "data" / "evidence" / "evidence_conflict_v1_manifest.json"


def main() -> int:
    manifest = build_case_evidence_snapshot(
        cases_path=CASES,
        evidence_path=EVIDENCE,
        manifest_path=MANIFEST,
        snapshot_version="evidence_conflict_v1",
        snapshot_date="2026-08-29",
        source_fixture_label="data/cases/benchmark_conflict_v1.jsonl",
        source_name="GenomeTriage synthetic conflict benchmark evidence",
        extraction_method="deterministic_conflict_fixture_extraction_v1",
        provenance_model="deterministic_conflict_fixture_extraction_v1",
        compatibility_note=(
            "All loci, genes, case contexts, and evidence are fully synthetic; no record "
            "is represented as ClinVar or patient-derived evidence."
        ),
        notes=[
            "All records are synthetic and contain no identifiable genomic data.",
            "Ground-truth files are not read during evidence extraction.",
            "Benchmark retrieval is exact, local, frozen, and independent of live services.",
        ],
    )
    print(
        f"Built {manifest.snapshot_version}: {manifest.record_count} records; "
        f"sha256={manifest.evidence_file_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
