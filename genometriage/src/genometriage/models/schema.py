"""Pydantic schemas for inputs, hidden labels, predictions, and evaluations."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, root_validator, validator

from genometriage import SAFETY_DISCLAIMER


SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    class Config:
        extra = "forbid"
        validate_assignment = True


class EvidenceItem(StrictModel):
    source_id: str = Field(..., min_length=1)
    source_type: Literal["synthetic_benchmark_record"]
    direction: Literal["supports", "against", "uncertain"]
    statement: str = Field(..., min_length=1)
    strength: Literal["weak", "moderate", "strong"]


class CandidateVariant(StrictModel):
    variant_id: str = Field(..., min_length=1)
    genome_build: Literal["GRCh38-synthetic"]
    chromosome: str = Field(..., min_length=1)
    position: int = Field(..., gt=0)
    reference: str = Field(..., min_length=1)
    alternate: str = Field(..., min_length=1)
    gene: Optional[str] = None
    consequence: Optional[str] = None
    zygosity: Literal["heterozygous", "homozygous", "hemizygous", "unknown"]
    observed_inheritance: Optional[str] = None
    population_allele_frequency: Optional[float] = Field(None, ge=0.0, le=1.0)
    evidence: List[EvidenceItem] = Field(default_factory=list)

    @validator("chromosome", pre=True)
    def normalize_chromosome(cls, value: object) -> str:
        text = str(value).strip()
        if text.lower().startswith("chr"):
            text = text[3:]
        text = text.upper()
        if not text:
            raise ValueError("chromosome cannot be empty")
        return text

    @validator("reference", "alternate", pre=True)
    def normalize_allele(cls, value: object) -> str:
        text = str(value).strip().upper()
        if not text:
            raise ValueError("allele cannot be empty")
        return text

    @validator("gene", pre=True)
    def normalize_gene(cls, value: object) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None

    @property
    def canonical_id(self) -> str:
        return (
            f"{self.genome_build}:{self.chromosome}:{self.position}:"
            f"{self.reference}:{self.alternate}"
        )


class CaseContext(StrictModel):
    summary: str = Field(..., min_length=1)
    phenotype_terms: List[str] = Field(default_factory=list)
    inheritance_hypothesis: Optional[str] = None
    family_observations: List[str] = Field(default_factory=list)


class BenchmarkCase(StrictModel):
    schema_version: Literal["1.0"]
    case_id: str = Field(..., regex=r"^GT-[0-9]{3}$")
    data_origin: Literal["fully_synthetic"]
    safety_disclaimer: Literal[SAFETY_DISCLAIMER]
    context: CaseContext
    candidate_variants: List[CandidateVariant] = Field(..., min_items=1)

    @root_validator
    def require_unique_identifiers(cls, values: Dict[str, object]) -> Dict[str, object]:
        candidates = values.get("candidate_variants") or []
        variant_ids = [candidate.variant_id for candidate in candidates]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("candidate variant_id values must be unique within a case")
        canonical_ids = [candidate.canonical_id for candidate in candidates]
        if len(canonical_ids) != len(set(canonical_ids)):
            raise ValueError("candidate coordinates must be unique within a case")
        source_ids = [
            evidence.source_id
            for candidate in candidates
            for evidence in candidate.evidence
        ]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence source_id values must be unique within a case")
        return values


class GroundTruthRationale(StrictModel):
    variant_ids: List[str] = Field(..., min_items=1)
    summary: str = Field(..., min_length=1)
    evidence_source_ids: List[str] = Field(..., min_items=1)


class BenchmarkGroundTruth(StrictModel):
    schema_version: Literal["1.0"]
    case_id: str = Field(..., regex=r"^GT-[0-9]{3}$")
    relevant_variant_ids: List[str]
    rationale: List[GroundTruthRationale]
    difficulty: Literal["straightforward", "moderate", "ambiguous", "conflicting", "challenging"]
    challenge_tags: List[str] = Field(default_factory=list)

    @validator("relevant_variant_ids")
    def relevant_ids_are_unique(cls, value: List[str]) -> List[str]:
        if len(value) != len(set(value)):
            raise ValueError("relevant_variant_ids must be unique")
        return value


class RankedVariant(StrictModel):
    variant_id: str = Field(..., min_length=1)
    rank: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_source_ids: List[str] = Field(default_factory=list)

    @validator("evidence_source_ids")
    def evidence_ids_are_unique(cls, value: List[str]) -> List[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_source_ids must be unique")
        return value


class TokenUsage(StrictModel):
    input_tokens: Optional[int] = Field(None, ge=0)
    output_tokens: Optional[int] = Field(None, ge=0)
    total_tokens: Optional[int] = Field(None, ge=0)


class Prediction(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    case_id: str
    system: str
    prompt_version: str
    model: str
    safety_disclaimer: Literal[SAFETY_DISCLAIMER] = SAFETY_DISCLAIMER
    ranked_variants: List[RankedVariant]
    escalated_uncertainty: bool
    notes: Optional[str] = None
    runtime_seconds: float = Field(..., ge=0.0)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost_usd: Optional[float] = Field(None, ge=0.0)

    @root_validator
    def ranking_is_well_formed(cls, values: Dict[str, object]) -> Dict[str, object]:
        ranked = values.get("ranked_variants") or []
        ids = [item.variant_id for item in ranked]
        ranks = [item.rank for item in ranked]
        if len(ids) != len(set(ids)):
            raise ValueError("ranked variant_id values must be unique")
        if ranks != list(range(1, len(ranked) + 1)):
            raise ValueError("ranks must be contiguous and ordered starting at 1")
        return values


class CaseRunRecord(StrictModel):
    case_id: str
    status: Literal["completed", "error"]
    prediction: Optional[Prediction] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    @root_validator
    def status_matches_payload(cls, values: Dict[str, object]) -> Dict[str, object]:
        status = values.get("status")
        prediction = values.get("prediction")
        if status == "completed" and prediction is None:
            raise ValueError("completed records require a prediction")
        if status == "error" and prediction is not None:
            raise ValueError("error records cannot contain a prediction")
        return values


class SystemRun(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_status: Literal["in_progress", "completed"] = "completed"
    system: str
    benchmark_version: str
    prompt_version: str
    model: str
    created_at_utc: datetime
    benchmark_sha256: str
    prompt_sha256: str
    execution_config: Dict[str, object] = Field(default_factory=dict)
    records: List[CaseRunRecord]


class CaseEvaluation(StrictModel):
    case_id: str
    difficulty: str
    status: Literal["evaluated", "run_error"]
    relevant_count: int = Field(..., ge=0)
    returned_count: int = Field(..., ge=0)
    sent_for_human_review: int = Field(..., ge=0)
    recall_at_k: Dict[str, Optional[float]]
    precision_at_k: Dict[str, float]
    false_positives_at_k: Dict[str, int]
    reciprocal_rank: Optional[float]
    unsupported_claim_count: int = Field(..., ge=0)
    evaluated_claim_count: int = Field(..., ge=0)
    unsupported_claim_rate: Optional[float]
    runtime_seconds: Optional[float]
    estimated_cost_usd: Optional[float]
    error_message: Optional[str] = None


class AggregateMetrics(StrictModel):
    evaluated_case_count: int = Field(..., ge=0)
    failed_case_count: int = Field(..., ge=0)
    negative_control_count: int = Field(..., ge=0)
    recall_at_k: Dict[str, Optional[float]]
    precision_at_k: Dict[str, Optional[float]]
    mean_reciprocal_rank: Optional[float]
    false_positive_count_at_k: Dict[str, int]
    unsupported_claim_rate: Optional[float]
    total_variants_sent_for_human_review: int = Field(..., ge=0)
    mean_variants_sent_for_human_review: Optional[float]
    mean_runtime_seconds: Optional[float]
    total_estimated_cost_usd: Optional[float]
    costed_case_count: int = Field(..., ge=0)


class EvaluationResult(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    benchmark_version: str
    system: str
    model: str
    execution_config: Dict[str, object] = Field(default_factory=dict)
    primary_k: int = Field(..., gt=0)
    k_values: List[int] = Field(..., min_items=1)
    safety_disclaimer: Literal[SAFETY_DISCLAIMER] = SAFETY_DISCLAIMER
    generated_at_utc: datetime
    benchmark_sha256: str
    prompt_sha256: str
    metric_definitions: Dict[str, str]
    aggregate: AggregateMetrics
    cases: List[CaseEvaluation]
