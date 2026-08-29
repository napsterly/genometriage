from __future__ import annotations

from pathlib import Path

import pytest

from genometriage.baseline.runner import load_system_run
from genometriage.benchmark.loader import file_sha256
from genometriage.controls.v0_top3 import (
    CONTROL_SYSTEM,
    build_v0_top3_control,
)
from genometriage.benchmark.loader import load_benchmark
from genometriage.evaluation.evaluator import evaluate_run


def test_v0_top3_control_is_deterministic_and_does_not_mutate_source() -> None:
    root = Path(__file__).parents[1]
    source_path = root / "predictions" / "baseline-gemini.json"
    source = load_system_run(source_path)
    source_before = source.json(sort_keys=True)
    first = build_v0_top3_control(
        source, source_sha256=file_sha256(source_path)
    )
    second = build_v0_top3_control(
        source, source_sha256=file_sha256(source_path)
    )
    assert first == second
    assert source.json(sort_keys=True) == source_before
    assert first.system == CONTROL_SYSTEM
    assert first.execution_config["no_model_calls"] is True
    assert all(
        len(record.prediction.ranked_variants) <= 3
        for record in first.records
        if record.prediction is not None
    )


def test_retained_v0_is_already_top3_so_control_rankings_are_identical() -> None:
    root = Path(__file__).parents[1]
    source_path = root / "predictions" / "baseline-gemini.json"
    source = load_system_run(source_path)
    control = build_v0_top3_control(
        source, source_sha256=file_sha256(source_path)
    )
    source_ids = [
        [item.variant_id for item in record.prediction.ranked_variants]
        for record in source.records
        if record.prediction is not None
    ]
    control_ids = [
        [item.variant_id for item in record.prediction.ranked_variants]
        for record in control.records
        if record.prediction is not None
    ]
    assert control_ids == source_ids
    assert sum(map(len, control_ids)) == 23


def test_v0_top3_control_rejects_nonfrozen_source_hash() -> None:
    root = Path(__file__).parents[1]
    source = load_system_run(root / "predictions" / "baseline-gemini.json")
    with pytest.raises(ValueError, match="frozen V0"):
        build_v0_top3_control(source, source_sha256="0" * 64)


def test_v0_top3_control_replays_identically_on_requested_metrics() -> None:
    root = Path(__file__).parents[1]
    source_path = root / "predictions" / "baseline-gemini.json"
    source = load_system_run(source_path)
    control = build_v0_top3_control(
        source, source_sha256=file_sha256(source_path)
    )
    baseline_result = evaluate_run(load_benchmark(), source)
    control_result = evaluate_run(load_benchmark(), control)
    baseline = baseline_result.aggregate
    measured = control_result.aggregate
    assert measured.recall_at_k == baseline.recall_at_k
    assert measured.mean_reciprocal_rank == baseline.mean_reciprocal_rank
    assert measured.false_positive_count_at_k == baseline.false_positive_count_at_k
    assert measured.false_positives_per_case == baseline.false_positives_per_case
    assert measured.review_burden == baseline.review_burden == 23
    assert measured.review_burden_at_full_recall == baseline.review_burden_at_full_recall == 14
    assert measured.shortlist_precision == baseline.shortlist_precision == 14 / 23
