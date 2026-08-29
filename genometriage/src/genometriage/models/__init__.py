"""Validated data contracts used across the benchmark and systems."""

from .schema import (
    AggregateMetrics,
    BenchmarkCase,
    BenchmarkGroundTruth,
    CaseEvaluation,
    CaseRunRecord,
    EvaluationResult,
    Prediction,
    RankedVariant,
    SystemRun,
)
from .phase2 import (
    CanonicalVariant,
    EvidenceRecord,
    EvidenceSnapshotManifest,
    MaterialClaim,
    VerifiedClaim,
)

__all__ = [
    "AggregateMetrics",
    "BenchmarkCase",
    "BenchmarkGroundTruth",
    "CaseEvaluation",
    "CaseRunRecord",
    "EvaluationResult",
    "Prediction",
    "RankedVariant",
    "SystemRun",
    "CanonicalVariant",
    "EvidenceRecord",
    "EvidenceSnapshotManifest",
    "MaterialClaim",
    "VerifiedClaim",
]
