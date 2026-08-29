"""Future-stage protocol boundaries; intentionally no agent implementations yet."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from genometriage.models.schema import BenchmarkCase, CandidateVariant, Prediction


class VariantNormalizer(Protocol):
    """Deterministically parse, normalize, and identify candidate variants."""

    def normalize(self, raw_variant: Mapping[str, Any]) -> CandidateVariant: ...


class AnnotationProvider(Protocol):
    """Attach deterministic or source-traceable annotations."""

    def annotate(self, variants: Sequence[CandidateVariant]) -> Sequence[CandidateVariant]: ...


class EvidenceRetriever(Protocol):
    """Retrieve evidence records without making the prioritization decision."""

    def retrieve(self, case: BenchmarkCase) -> Sequence[Mapping[str, Any]]: ...


class Prioritizer(Protocol):
    """Rank candidates using only the case and retrieved evidence."""

    def prioritize(
        self, case: BenchmarkCase, evidence: Sequence[Mapping[str, Any]]
    ) -> Prediction: ...


class IndependentVerifier(Protocol):
    """Check ranked claims against evidence independently of prioritization."""

    def verify(
        self, prediction: Prediction, evidence: Sequence[Mapping[str, Any]]
    ) -> Sequence[Mapping[str, Any]]: ...


class ConflictResolver(Protocol):
    """Preserve and escalate unresolved conflicts rather than forcing certainty."""

    def resolve(
        self, verification: Sequence[Mapping[str, Any]]
    ) -> Sequence[Mapping[str, Any]]: ...


class HumanReviewReporter(Protocol):
    """Render evidence-linked, safety-labeled output for qualified review."""

    def render(
        self, prediction: Prediction, verified_claims: Sequence[Mapping[str, Any]]
    ) -> str: ...

