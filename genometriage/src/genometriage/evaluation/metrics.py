"""Pure, deterministic ranking metric functions."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Set


def relevant_variant_recall_at_k(
    ranked_variant_ids: Sequence[str], relevant_variant_ids: Iterable[str], k: int
) -> Optional[float]:
    relevant = set(relevant_variant_ids)
    if not relevant:
        return None
    return len(set(ranked_variant_ids[:k]) & relevant) / len(relevant)


def precision_at_k(
    ranked_variant_ids: Sequence[str], relevant_variant_ids: Iterable[str], k: int
) -> float:
    relevant = set(relevant_variant_ids)
    return len(set(ranked_variant_ids[:k]) & relevant) / k


def false_positive_count_at_k(
    ranked_variant_ids: Sequence[str], relevant_variant_ids: Iterable[str], k: int
) -> int:
    relevant = set(relevant_variant_ids)
    return sum(variant_id not in relevant for variant_id in ranked_variant_ids[:k])


def reciprocal_rank(
    ranked_variant_ids: Sequence[str], relevant_variant_ids: Iterable[str]
) -> Optional[float]:
    relevant: Set[str] = set(relevant_variant_ids)
    if not relevant:
        return None
    for index, variant_id in enumerate(ranked_variant_ids, start=1):
        if variant_id in relevant:
            return 1.0 / index
    return 0.0


def review_burden_at_full_recall(
    ranked_variant_ids: Sequence[str], relevant_variant_ids: Iterable[str]
) -> Optional[int]:
    """Smallest prefix containing every relevant variant, or null on any miss."""

    relevant = set(relevant_variant_ids)
    if not relevant:
        return 0
    positions = {
        variant_id: index
        for index, variant_id in enumerate(ranked_variant_ids, start=1)
        if variant_id in relevant
    }
    if set(positions) != relevant:
        return None
    return max(positions.values())


def mean(values: Iterable[float]) -> Optional[float]:
    materialized = list(values)
    if not materialized:
        return None
    return sum(materialized) / len(materialized)
