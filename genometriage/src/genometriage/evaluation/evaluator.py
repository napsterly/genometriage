"""Pair sealed labels with system outputs and produce validated results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from genometriage.baseline.runner import estimate_cost_usd
from genometriage.benchmark.loader import BenchmarkBundle
from genometriage.models.schema import (
    AggregateMetrics,
    BenchmarkCase,
    BenchmarkGroundTruth,
    CaseEvaluation,
    CaseRunRecord,
    EvaluationResult,
    Prediction,
    SystemRun,
)

from .metrics import (
    false_positive_count_at_k,
    mean,
    precision_at_k,
    reciprocal_rank,
    relevant_variant_recall_at_k,
)


METRIC_DEFINITIONS = {
    "recall_at_k": (
        "Relevant Variant Recall@K = relevant variants in the first K ranks divided "
        "by all relevant variants. Negative controls are null and excluded from the macro mean."
    ),
    "precision_at_k": (
        "Precision@K = relevant variants in the first K ranks divided by K. "
        "Missing ranks, negative controls, and failed runs therefore contribute zero."
    ),
    "mean_reciprocal_rank": (
        "Mean reciprocal rank of the first relevant variant over positive cases; "
        "a miss or failed run scores zero, and negative controls are excluded."
    ),
    "false_positive_count_at_k": (
        "Count of returned variants in the first K ranks that are not evaluator-labeled relevant."
    ),
    "unsupported_claim_rate": (
        "Automated proxy: fraction of ranked-variant reasons in the primary-K shortlist "
        "whose evidence_source_ids are empty, unknown, or not attached to that candidate. "
        "This does not semantically fact-check prose."
    ),
    "sent_for_human_review": (
        "Number of returned variants in the primary-K shortlist."
    ),
    "estimated_cost_usd": (
        "Computed only when provider token usage and both user-supplied per-million-token "
        "prices were available; otherwise null."
    ),
}


def evaluate_run(
    bundle: BenchmarkBundle,
    run: SystemRun,
    *,
    k_values: Sequence[int] = (1, 3, 5),
    primary_k: int = 5,
) -> EvaluationResult:
    if run.run_status != "completed":
        raise ValueError("cannot evaluate an in-progress system run")
    ks = sorted(set(k_values))
    if not ks or any(k < 1 for k in ks):
        raise ValueError("k_values must contain positive integers")
    if primary_k not in ks:
        raise ValueError("primary_k must be included in k_values")

    records = _records_by_case(run.records)
    case_by_id = {case.case_id: case for case in bundle.cases}
    truth_by_id = {truth.case_id: truth for truth in bundle.ground_truth}
    extra_records = set(records) - set(case_by_id)
    if extra_records:
        raise ValueError(f"system run contains unknown case IDs: {sorted(extra_records)}")

    case_results: List[CaseEvaluation] = []
    for case_id in sorted(case_by_id):
        case = case_by_id[case_id]
        truth = truth_by_id[case_id]
        record = records.get(case_id)
        case_results.append(_evaluate_case(case, truth, record, ks, primary_k))

    aggregate = _aggregate(case_results, ks)
    return EvaluationResult(
        benchmark_version=run.benchmark_version,
        system=run.system,
        model=run.model,
        execution_config=run.execution_config,
        primary_k=primary_k,
        k_values=ks,
        generated_at_utc=datetime.now(timezone.utc),
        benchmark_sha256=bundle.sha256,
        prompt_sha256=run.prompt_sha256,
        metric_definitions=METRIC_DEFINITIONS,
        aggregate=aggregate,
        cases=case_results,
    )


def _records_by_case(records: Sequence[CaseRunRecord]) -> Dict[str, CaseRunRecord]:
    result: Dict[str, CaseRunRecord] = {}
    for record in records:
        if record.case_id in result:
            raise ValueError(f"duplicate case in system run: {record.case_id}")
        result[record.case_id] = record
    return result


def _evaluate_case(
    case: BenchmarkCase,
    truth: BenchmarkGroundTruth,
    record: Optional[CaseRunRecord],
    k_values: Sequence[int],
    primary_k: int,
) -> CaseEvaluation:
    prediction = record.prediction if record and record.status == "completed" else None
    ranked_ids = (
        [item.variant_id for item in prediction.ranked_variants] if prediction else []
    )
    recall = {
        str(k): relevant_variant_recall_at_k(
            ranked_ids, truth.relevant_variant_ids, k
        )
        for k in k_values
    }
    precision = {
        str(k): precision_at_k(ranked_ids, truth.relevant_variant_ids, k)
        for k in k_values
    }
    false_positives = {
        str(k): false_positive_count_at_k(
            ranked_ids, truth.relevant_variant_ids, k
        )
        for k in k_values
    }
    unsupported_count, claim_count = _unsupported_claims(case, prediction, primary_k)
    unsupported_rate = unsupported_count / claim_count if claim_count else None
    estimated_cost = prediction.estimated_cost_usd if prediction else None
    if prediction and estimated_cost is None:
        estimated_cost = estimate_cost_usd(
            prediction.usage.input_tokens,
            prediction.usage.output_tokens,
        )
    if record is None:
        error_message = "case missing from system run"
    elif record.status == "error":
        error_message = record.error_message or "system run failed without an error message"
    else:
        error_message = None

    return CaseEvaluation(
        case_id=case.case_id,
        difficulty=truth.difficulty,
        status="evaluated" if prediction else "run_error",
        relevant_count=len(truth.relevant_variant_ids),
        returned_count=len(ranked_ids),
        sent_for_human_review=min(primary_k, len(ranked_ids)),
        recall_at_k=recall,
        precision_at_k=precision,
        false_positives_at_k=false_positives,
        reciprocal_rank=reciprocal_rank(ranked_ids, truth.relevant_variant_ids),
        unsupported_claim_count=unsupported_count,
        evaluated_claim_count=claim_count,
        unsupported_claim_rate=unsupported_rate,
        runtime_seconds=prediction.runtime_seconds if prediction else None,
        estimated_cost_usd=estimated_cost,
        error_message=error_message,
    )


def _unsupported_claims(
    case: BenchmarkCase, prediction: Optional[Prediction], primary_k: int
) -> Tuple[int, int]:
    if prediction is None:
        return 0, 0
    valid_by_variant = {
        variant.variant_id: {item.source_id for item in variant.evidence}
        for variant in case.candidate_variants
    }
    unsupported = 0
    ranked = prediction.ranked_variants[:primary_k]
    for item in ranked:
        supplied = set(item.evidence_source_ids)
        valid = valid_by_variant.get(item.variant_id, set())
        if not supplied or not supplied.issubset(valid):
            unsupported += 1
    return unsupported, len(ranked)


def _aggregate(
    cases: Sequence[CaseEvaluation], k_values: Sequence[int]
) -> AggregateMetrics:
    recall_means: Dict[str, Optional[float]] = {}
    precision_means: Dict[str, Optional[float]] = {}
    false_positive_totals: Dict[str, int] = {}
    for k in k_values:
        key = str(k)
        recall_means[key] = mean(
            value
            for case in cases
            for value in [case.recall_at_k[key]]
            if value is not None
        )
        precision_means[key] = mean(case.precision_at_k[key] for case in cases)
        false_positive_totals[key] = sum(
            case.false_positives_at_k[key] for case in cases
        )

    claim_count = sum(case.evaluated_claim_count for case in cases)
    unsupported_count = sum(case.unsupported_claim_count for case in cases)
    costs = [
        case.estimated_cost_usd
        for case in cases
        if case.estimated_cost_usd is not None
    ]
    review_counts = [case.sent_for_human_review for case in cases]
    runtimes = [
        case.runtime_seconds for case in cases if case.runtime_seconds is not None
    ]
    return AggregateMetrics(
        evaluated_case_count=sum(case.status == "evaluated" for case in cases),
        failed_case_count=sum(case.status == "run_error" for case in cases),
        negative_control_count=sum(case.relevant_count == 0 for case in cases),
        recall_at_k=recall_means,
        precision_at_k=precision_means,
        mean_reciprocal_rank=mean(
            case.reciprocal_rank
            for case in cases
            if case.reciprocal_rank is not None
        ),
        false_positive_count_at_k=false_positive_totals,
        unsupported_claim_rate=(unsupported_count / claim_count if claim_count else None),
        total_variants_sent_for_human_review=sum(review_counts),
        mean_variants_sent_for_human_review=mean(review_counts),
        mean_runtime_seconds=mean(runtimes),
        total_estimated_cost_usd=(round(sum(costs), 8) if costs else None),
        costed_case_count=len(costs),
    )
