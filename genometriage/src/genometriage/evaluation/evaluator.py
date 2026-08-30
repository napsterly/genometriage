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
    review_burden_at_full_recall,
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
        "Historical name for citation_traceability_error_rate. Preserved unchanged "
        "for V0 comparability."
    ),
    "citation_traceability_error_rate": (
        "Fraction of ranked-variant reasons in the primary-K shortlist whose evidence "
        "IDs are empty, unknown, or attached to another candidate. This checks citation "
        "traceability only and does not semantically fact-check prose."
    ),
    "claim_support_precision": (
        "Of typed material claims labeled supported by the system, the fraction whose "
        "cited benchmark evidence directions support the claim interpretation. Null when "
        "the system emits no typed supported claims."
    ),
    "review_burden": (
        "Number of variants in the primary-K shortlist sent for expert review."
    ),
    "false_positives_per_case": (
        "Primary-K false positives divided by all benchmark cases, including the "
        "negative control."
    ),
    "review_burden_at_full_recall": (
        "Smallest summed per-case shortlist prefixes containing every known relevant "
        "variant. Null if any relevant variant is absent."
    ),
    "recall_constraint_met": (
        "Whether Recall@3 is at least the frozen V0 Recall@3 threshold."
    ),
    "shortlist_precision": (
        "Micro-averaged precision over the actual shortlist: total evaluator-labeled "
        "relevant returned variants divided by total returned variants. Unlike "
        "Precision@K, this has no fixed-K denominator."
    ),
    "sent_for_human_review": (
        "Number of returned variants in the primary-K shortlist."
    ),
    "estimated_cost_usd": (
        "Computed only when provider token usage and both user-supplied per-million-token "
        "prices were available; otherwise null."
    ),
    "abstention_count": (
        "Number of evaluated cases with an empty shortlist and explicit uncertainty "
        "escalation. This is case-level and distinct from candidate-level insufficiency."
    ),
    "insufficient_evidence_count": (
        "Number of audited candidates assigned the explicit insufficient_evidence state."
    ),
    "conflicting_evidence_count": (
        "Number of audited candidates retained with the explicit conflicting_evidence state."
    ),
    "model_call_count": (
        "External model calls represented by the prediction artifact. V3 inherits V1 calls "
        "and makes zero additional calls."
    ),
    "deterministic_runtime_seconds": (
        "Measured local deterministic processing time where separately instrumented."
    ),
    "external_model_runtime_seconds": (
        "Measured external provider wall-clock time where separately instrumented; provider "
        "latency is not interpreted as algorithmic processing time."
    ),
}


def evaluate_run(
    bundle: BenchmarkBundle,
    run: SystemRun,
    *,
    k_values: Sequence[int] = (1, 3, 5),
    primary_k: int = 5,
    recall_constraint_at_3: float = 1.0,
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

    aggregate = _aggregate(
        case_results,
        ks,
        primary_k=primary_k,
        recall_constraint_at_3=recall_constraint_at_3,
    )
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
    semantic_supported, system_supported = _claim_support(case, prediction, primary_k)
    claim_support_precision = (
        semantic_supported / system_supported if system_supported else None
    )
    burden_at_full_recall = review_burden_at_full_recall(
        ranked_ids, truth.relevant_variant_ids
    )
    shortlist_relevant_count = len(
        set(ranked_ids) & set(truth.relevant_variant_ids)
    )
    shortlist_returned_count = len(ranked_ids)
    arbitration = prediction.arbitration_records if prediction else []
    insufficient_evidence_count = sum(
        item.state == "insufficient_evidence" for item in arbitration
    )
    conflicting_evidence_count = sum(
        item.state == "conflicting_evidence" for item in arbitration
    )
    abstention_count = int(
        prediction is not None
        and not ranked_ids
        and prediction.escalated_uncertainty
    )
    model_call_count = _model_call_count(prediction)
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
        review_burden=min(primary_k, len(ranked_ids)),
        false_positive_count=false_positives[str(primary_k)],
        review_burden_at_full_recall=burden_at_full_recall,
        citation_traceability_error_count=unsupported_count,
        citation_traceability_claim_count=claim_count,
        citation_traceability_error_rate=unsupported_rate,
        semantically_supported_claim_count=semantic_supported,
        system_supported_claim_count=system_supported,
        claim_support_precision=claim_support_precision,
        runtime_seconds=prediction.runtime_seconds if prediction else None,
        estimated_cost_usd=estimated_cost,
        error_message=error_message,
        input_tokens=prediction.usage.input_tokens if prediction else None,
        output_tokens=prediction.usage.output_tokens if prediction else None,
        total_tokens=prediction.usage.total_tokens if prediction else None,
        shortlist_relevant_count=shortlist_relevant_count,
        shortlist_returned_count=shortlist_returned_count,
        shortlist_precision=(
            shortlist_relevant_count / shortlist_returned_count
            if shortlist_returned_count
            else None
        ),
        abstention_count=abstention_count,
        insufficient_evidence_count=insufficient_evidence_count,
        conflicting_evidence_count=conflicting_evidence_count,
        model_call_count=model_call_count,
        deterministic_runtime_seconds=(
            prediction.deterministic_runtime_seconds if prediction else None
        ),
        external_model_runtime_seconds=(
            prediction.external_model_runtime_seconds
            if prediction and prediction.external_model_runtime_seconds is not None
            else prediction.runtime_seconds if prediction else None
        ),
    )


def _model_call_count(prediction: Optional[Prediction]) -> Optional[int]:
    if prediction is None:
        return None
    if prediction.model_call_count is not None:
        return prediction.model_call_count
    if prediction.system == "verified-v2":
        return 2 if prediction.verified_claims else 1
    if prediction.system in {
        "baseline",
        "baseline-gemini",
        "baseline-openai",
        "v0-top3-control",
        "evidence-grounded-v1",
    }:
        return 1
    return None


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


def _claim_support(
    case: BenchmarkCase, prediction: Optional[Prediction], primary_k: int
) -> Tuple[int, int]:
    if prediction is None:
        return 0, 0
    evidence_by_variant = {
        variant.variant_id: {item.source_id: item for item in variant.evidence}
        for variant in case.candidate_variants
    }
    semantically_supported = 0
    system_supported = 0
    for ranked in prediction.ranked_variants[:primary_k]:
        available = evidence_by_variant.get(ranked.variant_id, {})
        for claim in ranked.claims:
            if claim.status != "supported":
                continue
            system_supported += 1
            cited = [available.get(evidence_id) for evidence_id in claim.evidence_ids]
            if not cited or any(item is None for item in cited):
                continue
            directions = {item.direction for item in cited if item is not None}
            if claim.interpretation == "supports_attention":
                supported = directions == {"supports"}
            elif claim.interpretation == "argues_against_attention":
                supported = directions == {"against"}
            else:
                supported = "uncertain" in directions or directions == {
                    "supports",
                    "against",
                }
            if supported:
                semantically_supported += 1
    return semantically_supported, system_supported


def _aggregate(
    cases: Sequence[CaseEvaluation],
    k_values: Sequence[int],
    *,
    primary_k: int,
    recall_constraint_at_3: float,
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
    trace_claim_count = sum(case.citation_traceability_claim_count for case in cases)
    trace_error_count = sum(case.citation_traceability_error_count for case in cases)
    system_supported_claims = sum(case.system_supported_claim_count for case in cases)
    semantically_supported_claims = sum(
        case.semantically_supported_claim_count for case in cases
    )
    full_recall_burdens = [case.review_burden_at_full_recall for case in cases]
    full_recall_burden = (
        sum(value for value in full_recall_burdens if value is not None)
        if all(value is not None for value in full_recall_burdens)
        else None
    )
    recall_at_3 = recall_means.get("3")
    shortlist_relevant_count = sum(
        case.shortlist_relevant_count for case in cases
    )
    shortlist_returned_count = sum(
        case.shortlist_returned_count for case in cases
    )
    model_calls = [case.model_call_count for case in cases if case.model_call_count is not None]
    deterministic_runtimes = [
        case.deterministic_runtime_seconds
        for case in cases
        if case.deterministic_runtime_seconds is not None
    ]
    external_runtimes = [
        case.external_model_runtime_seconds
        for case in cases
        if case.external_model_runtime_seconds is not None
    ]

    def token_total(field: str) -> Optional[int]:
        values = [getattr(case, field) for case in cases]
        present = [value for value in values if value is not None]
        return sum(present) if present else None

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
        review_burden=sum(review_counts),
        false_positives_per_case=(
            false_positive_totals[str(primary_k)] / len(cases) if cases else None
        ),
        review_burden_at_full_recall=full_recall_burden,
        recall_constraint_at_3=recall_constraint_at_3,
        recall_constraint_met=(
            recall_at_3 >= recall_constraint_at_3
            if recall_at_3 is not None
            else None
        ),
        citation_traceability_error_rate=(
            trace_error_count / trace_claim_count if trace_claim_count else None
        ),
        claim_support_precision=(
            semantically_supported_claims / system_supported_claims
            if system_supported_claims
            else None
        ),
        total_input_tokens=token_total("input_tokens"),
        total_output_tokens=token_total("output_tokens"),
        total_tokens=token_total("total_tokens"),
        shortlist_relevant_count=shortlist_relevant_count,
        shortlist_returned_count=shortlist_returned_count,
        shortlist_precision=(
            shortlist_relevant_count / shortlist_returned_count
            if shortlist_returned_count
            else None
        ),
        abstention_count=sum(case.abstention_count for case in cases),
        insufficient_evidence_count=sum(
            case.insufficient_evidence_count for case in cases
        ),
        conflicting_evidence_count=sum(
            case.conflicting_evidence_count for case in cases
        ),
        total_model_calls=sum(model_calls) if model_calls else None,
        mean_model_calls_per_case=mean(model_calls),
        mean_deterministic_runtime_seconds=mean(deterministic_runtimes),
        mean_external_model_runtime_seconds=mean(external_runtimes),
    )
