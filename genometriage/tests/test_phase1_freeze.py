from __future__ import annotations

import hashlib
import json
from pathlib import Path

from genometriage.baseline.runner import load_system_run
from genometriage.benchmark.loader import load_benchmark
from genometriage.evaluation.evaluator import evaluate_run


def test_frozen_phase1_artifact_hashes_are_unchanged() -> None:
    root = Path(__file__).parents[1]
    freeze = json.loads((root / "docs" / "PHASE1_FREEZE.json").read_text(encoding="utf-8"))
    for relative_path, expected_hash in freeze["artifacts"].items():
        actual_hash = hashlib.sha256((root / relative_path).read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"frozen artifact changed: {relative_path}"


def test_frozen_v0_replays_with_phase2_review_metrics() -> None:
    root = Path(__file__).parents[1]
    result = evaluate_run(
        load_benchmark(),
        load_system_run(root / "predictions" / "baseline-gemini.json"),
    )
    metrics = result.aggregate
    assert metrics.recall_at_k["3"] == 1.0
    assert metrics.review_burden == 23
    assert metrics.false_positives_per_case == 0.75
    assert metrics.review_burden_at_full_recall == 14
    assert metrics.recall_constraint_met is True
    assert metrics.citation_traceability_error_rate == 0.0
    assert metrics.claim_support_precision is None
    assert metrics.total_tokens == 23275
    assert metrics.shortlist_relevant_count == 14
    assert metrics.shortlist_returned_count == 23
    assert metrics.shortlist_precision == 14 / 23
