from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from genometriage import SAFETY_DISCLAIMER
from genometriage.baseline.runner import load_system_run
from genometriage.benchmark.loader import (
    file_sha256,
    load_benchmark,
    load_cases,
    visible_fixture_contains_answer_fields,
)
from genometriage.evaluation.evaluator import evaluate_run
from genometriage.evidence import EvidenceStore
from genometriage.models.phase2 import EvidenceContent, EvidenceProvenance, EvidenceRecord
from genometriage.models.schema import BenchmarkCase, CaseRunRecord, SystemRun
from genometriage.phase2.prompt import V1_PROMPT_VERSION
from genometriage.phase2.runner import validate_resume_run
from genometriage.phase3.arbitration import arbitrate_candidate
from genometriage.phase3.runner import ConflictArbitrationSystem


ROOT = Path(__file__).parents[1]
CONFLICT_CASES = ROOT / "data" / "cases" / "benchmark_conflict_v1.jsonl"
CONFLICT_TRUTH = (
    ROOT / "data" / "ground_truth" / "benchmark_conflict_v1_ground_truth.jsonl"
)
CONFLICT_FREEZE = ROOT / "data" / "manifests" / "benchmark_conflict_v1_freeze.json"
PUBLIC_CASES = ROOT / "data" / "cases" / "benchmark_public_v1.jsonl"
PUBLIC_TRUTH = ROOT / "data" / "ground_truth" / "benchmark_public_v1_ground_truth.jsonl"
PUBLIC_FREEZE = ROOT / "data" / "manifests" / "benchmark_public_v1_freeze.json"


def _evidence(
    evidence_id: str,
    direction: str,
    strength: str,
    dimension: str = "other",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        source="test evidence",
        original_source_record_id=evidence_id,
        snapshot_version="test_v1",
        snapshot_date="2026-08-29",
        canonical_variant_id="GRCh38:1:1:A:G",
        content=EvidenceContent(
            source_type="synthetic_benchmark_record",
            direction=direction,
            statement=f"{direction} {strength} {dimension}",
            strength=strength,
            dimension=dimension,
        ),
        provenance=EvidenceProvenance(
            data_origin="fully_synthetic",
            source_fixture="test",
            source_fixture_sha256="a" * 64,
            source_case_id="GC-999",
            source_variant_id="GC999-V1",
            extraction_method="test",
            public_resource_compatibility_note="synthetic test only",
        ),
    )


def _load_script():
    path = ROOT / "scripts" / "build_public_benchmark.py"
    spec = importlib.util.spec_from_file_location("build_public_benchmark_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_conflict_benchmark_is_separate_and_has_no_label_leakage() -> None:
    bundle = load_benchmark(CONFLICT_CASES, CONFLICT_TRUTH)
    assert len(bundle.cases) == 13
    assert all(case.case_id.startswith("GC-") for case in bundle.cases)
    assert not visible_fixture_contains_answer_fields(CONFLICT_CASES)
    assert CONFLICT_CASES.read_bytes() != (
        ROOT / "data" / "cases" / "benchmark_v1.jsonl"
    ).read_bytes()


def test_conflict_and_public_freeze_hashes_validate() -> None:
    conflict = json.loads(CONFLICT_FREEZE.read_text(encoding="utf-8"))
    for relative, expected in conflict["artifacts"].items():
        assert file_sha256(ROOT / relative) == expected
    public = json.loads(PUBLIC_FREEZE.read_text(encoding="utf-8"))
    for relative, expected in public["artifacts"].items():
        assert file_sha256(ROOT / relative) == expected


def test_arbitration_spec_hash_is_frozen() -> None:
    freeze = json.loads(
        (ROOT / "docs" / "CONFLICT_ARBITRATION_SPEC_FREEZE.json").read_text(
            encoding="utf-8"
        )
    )
    assert file_sha256(ROOT / freeze["spec_path"]) == freeze["spec_sha256"]
    assert freeze["preregistration"]["post_hoc_changes_permitted"] is False


@pytest.mark.parametrize(
    ("records", "state", "rule"),
    [
        ([], "insufficient_evidence", "1_insufficient_no_directional_evidence"),
        (
            [_evidence("E1", "against", "moderate")],
            "deprioritize",
            "2_counterevidence_only",
        ),
        (
            [
                _evidence("E1", "supports", "strong", "molecular"),
                _evidence("E2", "against", "strong", "inheritance"),
            ],
            "deprioritize",
            "3_contextual_strong_counter",
        ),
        (
            [
                _evidence("E1", "supports", "strong"),
                _evidence("E2", "uncertain", "weak"),
            ],
            "conflicting_evidence",
            "6_material_conflict_or_uncertainty",
        ),
        (
            [_evidence("E1", "supports", "strong")],
            "retain",
            "7_unopposed_support",
        ),
    ],
)
def test_arbitration_states_are_deterministic(records, state, rule) -> None:
    first = arbitrate_candidate("GC999-V1", 1, records)
    second = arbitrate_candidate("GC999-V1", 1, list(reversed(records)))
    assert first == second
    assert first.state == state
    assert first.fired_rule == rule


def test_public_records_have_pinned_provenance_and_source_separation() -> None:
    bundle = load_benchmark(PUBLIC_CASES, PUBLIC_TRUTH)
    assert len(bundle.cases) == 10
    assert not visible_fixture_contains_answer_fields(PUBLIC_CASES)
    assert all(case.data_origin == "appropriately_public" for case in bundle.cases)
    assert all(case.case_id.startswith("GP-") for case in bundle.cases)
    store = EvidenceStore.load(
        evidence_path=ROOT / "data" / "evidence" / "evidence_public_v1.jsonl",
        manifest_path=ROOT / "data" / "evidence" / "evidence_public_v1_manifest.json",
        cases_path=PUBLIC_CASES,
    )
    assert store.manifest.external_live_dependency is False
    assert all(record.content.source_type == "clinvar_public_record" for record in store.records)
    assert all(record.provenance.source_release for record in store.records)
    assert all(record.provenance.source_record_sha256 for record in store.records)
    assert all(record.original_source_record_id.startswith("CLINVAR:VCV") for record in store.records)


def test_public_snapshot_reconstructs_cases_and_labels_offline() -> None:
    module = _load_script()
    pool = json.loads(module.RAW_POOL.read_text(encoding="utf-8"))
    selected = module._select_records(pool)
    cases, truths = module._build_cases_and_truth(selected)
    expected_cases = [case.dict() for case in load_cases(PUBLIC_CASES)]
    expected_truths = [truth.dict() for truth in load_benchmark(PUBLIC_CASES, PUBLIC_TRUTH).ground_truth]
    assert [BenchmarkCase.parse_obj(case).dict() for case in cases] == expected_cases
    assert [module.json.loads(module.json.dumps(truth)) for truth in truths] == expected_truths


def test_malformed_public_record_and_duplicate_public_variant_are_rejected() -> None:
    module = _load_script()
    selected = json.loads(module.SELECTED_RECORDS.read_text(encoding="utf-8"))["records"]
    malformed = copy.deepcopy(selected[0]["clinvar_record"])
    malformed["variation_set"][0]["canonical_spdi"] = "not-spdi"
    assert module._variant_fields(malformed, selected[0]["gene"]) is None

    case = load_cases(PUBLIC_CASES)[0].dict()
    duplicate = copy.deepcopy(case["candidate_variants"][0])
    duplicate["variant_id"] = "DUPLICATE-COORDINATE"
    case["candidate_variants"].append(duplicate)
    with pytest.raises(ValueError, match="coordinates must be unique"):
        BenchmarkCase.parse_obj(case)


def test_v3_regression_artifact_preserves_safety_and_reports_new_metrics() -> None:
    run = load_system_run(ROOT / "predictions" / "conflict-arbitrated-v3.json")
    result = evaluate_run(load_benchmark(), run)
    assert all(
        record.prediction.safety_disclaimer == SAFETY_DISCLAIMER
        for record in run.records
        if record.prediction
    )
    assert result.aggregate.total_model_calls == 12
    assert result.aggregate.insufficient_evidence_count == 2
    assert result.aggregate.abstention_count == 2
    assert result.aggregate.mean_deterministic_runtime_seconds is not None


def test_phase3_human_and_machine_reports_retain_safety_label() -> None:
    markdown = (ROOT / "results" / "phase3" / "COMPARISON.md").read_text(
        encoding="utf-8"
    )
    comparison = json.loads(
        (ROOT / "results" / "phase3" / "comparison.json").read_text(
            encoding="utf-8"
        )
    )
    assert SAFETY_DISCLAIMER in markdown
    assert comparison["safety_disclaimer"] == SAFETY_DISCLAIMER


def test_phase3_source_model_switch_and_resume_mismatch_are_rejected() -> None:
    v1 = load_system_run(ROOT / "predictions" / "evidence-grounded-v1.json")
    store = EvidenceStore.load()
    switched = v1.copy(update={"model": "different-model"})
    system = ConflictArbitrationSystem(store, switched)
    assert system.model == "different-model"
    checkpoint = SystemRun(
        system="conflict-arbitrated-v3",
        benchmark_version="benchmark_v1",
        prompt_version=system.prompt_version,
        model="unexpected-model",
        created_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        benchmark_sha256=v1.benchmark_sha256,
        prompt_sha256=system.prompt_hash,
        execution_config=system.execution_config,
        records=[],
    )
    with pytest.raises(ValueError, match="model"):
        system.validate_resume_run(
            checkpoint, cases_path=ROOT / "data" / "cases" / "benchmark_v1.jsonl"
        )

    with pytest.raises(ValueError, match="model"):
        validate_resume_run(
            v1.copy(update={"model": "unexpected-model"}),
            system="evidence-grounded-v1",
            prompt_version=V1_PROMPT_VERSION,
            model=v1.model,
            prompt_hash=v1.prompt_sha256,
            execution_config=v1.execution_config,
            cases_path=ROOT / "data" / "cases" / "benchmark_v1.jsonl",
        )
