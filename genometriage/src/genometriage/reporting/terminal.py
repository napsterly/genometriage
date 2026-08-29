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
            f"unsupported-claim proxy={_format_metric(metrics.unsupported_claim_rate)} | "
            f"sent for review={metrics.total_variants_sent_for_human_review}"
        ),
        (
            f"Mean runtime={_format_metric(metrics.mean_runtime_seconds)}s | "
            f"estimated cost={_format_cost(metrics.total_estimated_cost_usd)}"
        ),
        f"Machine-readable result: {output_path}",
    ]
    return "\n".join(lines)


def _format_cost(value: Optional[float]) -> str:
    return "n/a (pricing not supplied)" if value is None else f"${value:.8f}"
