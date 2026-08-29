from genometriage.evaluation.metrics import (
    false_positive_count_at_k,
    precision_at_k,
    reciprocal_rank,
    relevant_variant_recall_at_k,
)
from genometriage.baseline.runner import estimate_cost_usd
from genometriage.evaluation.evaluator import evaluate_run
from genometriage.models.schema import CaseRunRecord, RankedVariant

from conftest import make_prediction


def test_recall_precision_and_false_positives() -> None:
    ranked = ["A", "X", "B", "Y"]
    relevant = {"A", "B"}
    assert relevant_variant_recall_at_k(ranked, relevant, 1) == 0.5
    assert relevant_variant_recall_at_k(ranked, relevant, 3) == 1.0
    assert precision_at_k(ranked, relevant, 3) == 2 / 3
    assert false_positive_count_at_k(ranked, relevant, 3) == 1


def test_reciprocal_rank_and_miss() -> None:
    assert reciprocal_rank(["X", "B"], {"A", "B"}) == 0.5
    assert reciprocal_rank(["X"], {"A"}) == 0.0


def test_negative_control_recall_and_mrr_are_undefined() -> None:
    assert relevant_variant_recall_at_k([], set(), 5) is None
    assert reciprocal_rank([], set()) is None
    assert precision_at_k([], set(), 5) == 0.0


def test_unsupported_claim_proxy_is_candidate_specific(
    benchmark_bundle, complete_empty_run
) -> None:
    run = complete_empty_run.copy(deep=True)
    prediction = make_prediction(
        "GT-001",
        [
            RankedVariant(
                variant_id="GT001-V1",
                rank=1,
                reason="Supported by the attached synthetic assay.",
                confidence=0.9,
                evidence_source_ids=["GT001-E1"],
            ),
            RankedVariant(
                variant_id="GT001-V2",
                rank=2,
                reason="Cites an ID that does not belong to this candidate.",
                confidence=0.2,
                evidence_source_ids=["GT001-E1"],
            ),
        ],
    )
    run.records[0] = CaseRunRecord(
        case_id="GT-001", status="completed", prediction=prediction
    )
    result = evaluate_run(benchmark_bundle, run)
    evaluated = result.cases[0]
    assert evaluated.unsupported_claim_count == 1
    assert evaluated.evaluated_claim_count == 2
    assert evaluated.unsupported_claim_rate == 0.5
    assert evaluated.sent_for_human_review == 2


def test_cost_is_only_computed_from_explicit_prices(monkeypatch) -> None:
    monkeypatch.delenv("GENOMETRIAGE_INPUT_COST_PER_MILLION", raising=False)
    monkeypatch.delenv("GENOMETRIAGE_OUTPUT_COST_PER_MILLION", raising=False)
    assert estimate_cost_usd(1000, 500) is None
    monkeypatch.setenv("GENOMETRIAGE_INPUT_COST_PER_MILLION", "2")
    monkeypatch.setenv("GENOMETRIAGE_OUTPUT_COST_PER_MILLION", "8")
    assert estimate_cost_usd(1000, 500) == 0.006
