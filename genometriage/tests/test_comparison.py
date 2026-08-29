from __future__ import annotations

from genometriage.reporting.comparison import build_comparison, build_failure_analysis
from genometriage.models.schema import AggregateMetrics, EvaluationResult


def test_comparison_verdict_requires_recall_and_efficiency() -> None:
    def result(
        system: str,
        burden: int,
        false_positives: int,
        runtime: float,
        shortlist_precision: float,
    ):
        return EvaluationResult(
            benchmark_version="benchmark_v1",
            system=system,
            model="fake",
            execution_config={},
            primary_k=5,
            k_values=[1, 3, 5],
            generated_at_utc="2026-01-01T00:00:00Z",
            benchmark_sha256="a" * 64,
            prompt_sha256="b" * 64,
            metric_definitions={},
            aggregate=AggregateMetrics(
                evaluated_case_count=1,
                failed_case_count=0,
                negative_control_count=0,
                recall_at_k={"1": 1.0, "3": 1.0, "5": 1.0},
                precision_at_k={"1": 1.0, "3": 1 / 3, "5": 0.2},
                mean_reciprocal_rank=1.0,
                false_positive_count_at_k={"1": 0, "3": 0, "5": false_positives},
                unsupported_claim_rate=0.0,
                total_variants_sent_for_human_review=burden,
                mean_variants_sent_for_human_review=float(burden),
                mean_runtime_seconds=runtime,
                total_estimated_cost_usd=0.0,
                costed_case_count=1,
                review_burden=burden,
                recall_constraint_met=True,
                claim_support_precision=1.0,
                shortlist_precision=shortlist_precision,
            ),
            cases=[],
        )

    comparison = build_comparison(
        {
            "V0": result("v0", 3, 2, 1.0, 1 / 3),
            "V0-top3": result("v0-top3", 2, 1, 1.0, 0.5),
            "V1": result("v1", 1, 0, 2.0, 1.0),
            "V2": result("v2", 1, 0, 4.0, 1.0),
        }
    )
    verdict = comparison["complexity_verdict"]
    assert verdict["V1_evidence_grounding_earned_complexity"] is True
    assert verdict["V2_independent_verification_earned_complexity"] is False
    attribution = comparison["attribution_analysis"]
    assert attribution["reduction_from_top3_truncation_alone"] == 1
    assert attribution["additional_reduction_in_v1_after_top3_control"] == 1
    assert attribution["truncation_share_of_total_reduction"] == 0.5
    assert attribution["v1_retains_measurable_advantage_after_top3_control"] is True
