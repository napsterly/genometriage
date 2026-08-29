from __future__ import annotations

from pathlib import Path

import pytest

from genometriage.evidence import EvidenceStore, EvidenceStoreError, build_evidence_snapshot
from genometriage.normalization import normalize_candidate


def test_snapshot_retrieval_exactly_matches_visible_candidate_evidence(benchmark_bundle) -> None:
    store = EvidenceStore.load()
    for case in benchmark_bundle.cases:
        for candidate in case.candidate_variants:
            retrieved = store.retrieve(normalize_candidate(candidate))
            assert [record.evidence_id for record in retrieved] == sorted(
                item.source_id for item in candidate.evidence
            )
            assert all(record.provenance.source_case_id == case.case_id for record in retrieved)


def test_snapshot_is_frozen_and_has_no_live_dependency() -> None:
    store = EvidenceStore.load()
    assert store.manifest.external_live_dependency is False
    assert store.manifest.snapshot_version == "evidence_v1"
    assert store.manifest.record_count == len(store.records)
    assert all(record.provenance.data_origin == "fully_synthetic" for record in store.records)


def test_builder_uses_only_model_visible_cases(tmp_path: Path, monkeypatch) -> None:
    def forbidden_ground_truth(*args, **kwargs):
        raise AssertionError("ground truth must not be loaded")

    monkeypatch.setattr(
        "genometriage.benchmark.loader.load_ground_truth",
        forbidden_ground_truth,
    )
    evidence = tmp_path / "evidence.jsonl"
    manifest = tmp_path / "manifest.json"
    built = build_evidence_snapshot(evidence_path=evidence, manifest_path=manifest)
    assert built.record_count > 0
    assert evidence.is_file()


def test_tampered_snapshot_is_rejected(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    manifest = tmp_path / "manifest.json"
    build_evidence_snapshot(evidence_path=evidence, manifest_path=manifest)
    evidence.write_text(evidence.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(EvidenceStoreError, match="hash"):
        EvidenceStore.load(evidence_path=evidence, manifest_path=manifest)
