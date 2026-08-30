"""Concise terminal output for benchmark evaluations."""

from __future__ import annotations

from typing import Optional

from genometriage import SAFETY_DISCLAIMER
from genometriage.models.schema import EvaluationResult


def _format_metric(value: Optional[float], digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_terminal_summary(result: EvaluationResult, output_path: str) -> str:
    metrics = result.aggregate
    primary = str(result.primary_k)
    lines = [
        SAFETY_DISCLAIMER,
        (
            f"System={result.system} | model={result.model} | "
            f"cases={metrics.evaluated_case_count} evaluated, "
            f"{metrics.failed_case_count} failed | primary K={result.primary_k}"
        ),
        (
            f"Recall@{primary}={_format_metric(metrics.recall_at_k[primary])} | "
            f"Precision@{primary}={_format_metric(metrics.precision_at_k[primary])} | "
            f"MRR={_format_metric(metrics.mean_reciprocal_rank)}"
        ),
        (
            f"False positives@{primary}={metrics.false_positive_count_at_k[primary]} | "
            f"FP/case={_format_metric(metrics.false_positives_per_case)} | "
            f"review burden={metrics.review_burden}"
        ),
        (
            "Review burden at full recall="
            f"{metrics.review_burden_at_full_recall if metrics.review_burden_at_full_recall is not None else 'n/a'} | "
            f"Recall@3 constraint={metrics.recall_constraint_met} | "
            "citation traceability error="
            f"{_format_metric(metrics.citation_traceability_error_rate)} | "
            f"claim support precision={_format_metric(metrics.claim_support_precision)}"
        ),
        (
            f"Shortlist precision={_format_metric(metrics.shortlist_precision)} | "
            f"relevant returned={metrics.shortlist_relevant_count}/"
            f"{metrics.shortlist_returned_count}"
        ),
        (
            f"Abstention cases={metrics.abstention_count} | "
            f"insufficient candidates={metrics.insufficient_evidence_count} | "
            f"conflicting candidates={metrics.conflicting_evidence_count}"
        ),
        (
            f"Mean runtime={_format_metric(metrics.mean_runtime_seconds)}s "
            f"(local={_format_metric(metrics.mean_deterministic_runtime_seconds)}s, "
            f"external={_format_metric(metrics.mean_external_model_runtime_seconds)}s) | "
            f"model calls/case={_format_metric(metrics.mean_model_calls_per_case)} | "
            f"tokens={metrics.total_tokens} | "
            f"estimated cost={_format_cost(metrics.total_estimated_cost_usd)}"
        ),
        f"Machine-readable result: {output_path}",
    ]
    return "\n".join(lines)


def _format_cost(value: Optional[float]) -> str:
    return "n/a (pricing not supplied)" if value is None else f"${value:.8f}"
