"""Create, validate, and query the immutable Phase 2 evidence snapshot."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List, Sequence

from pydantic import ValidationError

from genometriage.benchmark.loader import DEFAULT_CASES_PATH, file_sha256, load_cases
from genometriage.models.phase2 import (
    CanonicalVariant,
    EvidenceContent,
    EvidenceProvenance,
    EvidenceRecord,
    EvidenceSnapshotManifest,
)
from genometriage.normalization import normalize_candidate


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVIDENCE_PATH = PROJECT_ROOT / "data" / "evidence" / "evidence_v1.jsonl"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "evidence" / "evidence_v1_manifest.json"
SNAPSHOT_DATE = "2026-08-29"
SOURCE_FIXTURE_LABEL = "data/cases/benchmark_v1.jsonl"
PROVENANCE_NOTE = (
    "The coordinates, genes, case context, and evidence are fully synthetic. "
    "The record carries versioned accession-like IDs and frozen provenance fields "
    "for compatibility with later public-resource adapters; it is not a ClinVar record."
)


class EvidenceStoreError(ValueError):
    """The evidence snapshot is malformed, inconsistent, or has changed."""


def _record_json(record: EvidenceRecord) -> str:
    return json.dumps(record.dict(), sort_keys=True, separators=(",", ":"))


def build_evidence_snapshot(
    *,
    cases_path: Path = DEFAULT_CASES_PATH,
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> EvidenceSnapshotManifest:
    """Extract evidence from visible cases only; evaluator labels are never loaded."""

    cases_path = Path(cases_path)
    source_hash = file_sha256(cases_path)
    records: List[EvidenceRecord] = []
    for case in load_cases(cases_path):
        for candidate in case.candidate_variants:
            canonical = normalize_candidate(candidate)
            for item in candidate.evidence:
                records.append(
                    EvidenceRecord(
                        evidence_id=item.source_id,
                        source="GenomeTriage synthetic benchmark evidence",
                        original_source_record_id=item.source_id,
                        snapshot_version="evidence_v1",
                        snapshot_date=SNAPSHOT_DATE,
                        canonical_variant_id=canonical.canonical_id,
                        content=EvidenceContent.parse_obj(
                            item.dict(exclude={"source_id"})
                        ),
                        provenance=EvidenceProvenance(
                            data_origin="fully_synthetic",
                            source_fixture=SOURCE_FIXTURE_LABEL,
                            source_fixture_sha256=source_hash,
                            source_case_id=case.case_id,
                            source_variant_id=candidate.variant_id,
                            extraction_method="deterministic_fixture_extraction_v1",
                            public_resource_compatibility_note=PROVENANCE_NOTE,
                        ),
                    )
                )
    records.sort(key=lambda record: record.evidence_id)
    evidence_ids = [record.evidence_id for record in records]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise EvidenceStoreError("evidence IDs must be globally unique")

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        "".join(f"{_record_json(record)}\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )
    manifest = EvidenceSnapshotManifest(
        snapshot_version="evidence_v1",
        snapshot_date=SNAPSHOT_DATE,
        record_count=len(records),
        evidence_file="data/evidence/evidence_v1.jsonl",
        evidence_file_sha256=file_sha256(evidence_path),
        source_fixture=SOURCE_FIXTURE_LABEL,
        source_fixture_sha256=source_hash,
        provenance_model="deterministic_fixture_extraction_v1",
        external_live_dependency=False,
        notes=[
            "All records are synthetic and contain no patient-identifiable genomic data.",
            "Ground-truth files are not read when building this snapshot.",
            "Live web or API access is not used during benchmark retrieval.",
        ],
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        manifest.json(indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


class EvidenceStore:
    """An in-memory index over a hash-validated frozen evidence snapshot."""

    def __init__(
        self,
        records: Sequence[EvidenceRecord],
        manifest: EvidenceSnapshotManifest,
    ) -> None:
        self.records = tuple(records)
        self.manifest = manifest
        by_id: Dict[str, EvidenceRecord] = {}
        by_canonical: DefaultDict[str, List[EvidenceRecord]] = defaultdict(list)
        for record in records:
            if record.evidence_id in by_id:
                raise EvidenceStoreError(f"duplicate evidence ID: {record.evidence_id}")
            by_id[record.evidence_id] = record
            by_canonical[record.canonical_variant_id].append(record)
        self._by_id = by_id
        self._by_canonical = dict(by_canonical)

    @classmethod
    def load(
        cls,
        *,
        evidence_path: Path = DEFAULT_EVIDENCE_PATH,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
        verify_source_fixture: bool = True,
        cases_path: Path = DEFAULT_CASES_PATH,
    ) -> "EvidenceStore":
        evidence_path = Path(evidence_path)
        manifest_path = Path(manifest_path)
        try:
            manifest = EvidenceSnapshotManifest.parse_raw(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise EvidenceStoreError(f"invalid evidence manifest: {manifest_path}: {exc}") from exc
        if not evidence_path.is_file():
            raise EvidenceStoreError(f"evidence snapshot not found: {evidence_path}")
        if file_sha256(evidence_path) != manifest.evidence_file_sha256:
            raise EvidenceStoreError("evidence snapshot hash does not match its manifest")
        if verify_source_fixture and file_sha256(Path(cases_path)) != manifest.source_fixture_sha256:
            raise EvidenceStoreError("model-visible case fixture hash does not match evidence provenance")

        records: List[EvidenceRecord] = []
        for line_number, line in enumerate(evidence_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(EvidenceRecord.parse_raw(line))
            except (ValidationError, ValueError) as exc:
                raise EvidenceStoreError(
                    f"{evidence_path}:{line_number}: invalid evidence record: {exc}"
                ) from exc
        if len(records) != manifest.record_count:
            raise EvidenceStoreError("evidence record count does not match its manifest")
        return cls(records, manifest)

    def retrieve(self, variant: CanonicalVariant) -> List[EvidenceRecord]:
        """Return only exact normalized-allele matches in stable evidence-ID order."""

        records = self._by_canonical.get(variant.canonical_id, [])
        matching = [
            record
            for record in records
            if record.provenance.source_variant_id == variant.variant_id
        ]
        return sorted(matching, key=lambda record: record.evidence_id)

    def get(self, evidence_id: str) -> EvidenceRecord:
        try:
            return self._by_id[evidence_id]
        except KeyError as exc:
            raise EvidenceStoreError(f"unknown evidence ID: {evidence_id}") from exc
