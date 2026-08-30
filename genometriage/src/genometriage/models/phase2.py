"""Phase 2 contracts for normalized variants, evidence, and claims."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator


class Phase2StrictModel(BaseModel):
    class Config:
        extra = "forbid"
        validate_assignment = True


class CanonicalVariant(Phase2StrictModel):
    variant_id: str = Field(..., min_length=1)
    genome_build: str = Field(..., min_length=1)
    chromosome: str = Field(..., min_length=1)
    position: int = Field(..., gt=0)
    reference: str = Field(..., regex=r"^[ACGTN]+$")
    alternate: str = Field(..., regex=r"^[ACGTN]+$")
    canonical_id: str = Field(..., min_length=1)
    gene: Optional[str] = None
    consequence: Optional[str] = None


class EvidenceContent(Phase2StrictModel):
    source_type: Literal["synthetic_benchmark_record", "clinvar_public_record"]
    direction: Literal["supports", "against", "uncertain"]
    statement: str = Field(..., min_length=1)
    strength: Literal["weak", "moderate", "strong"]
    dimension: Literal[
        "molecular",
        "functional",
        "regulatory",
        "phenotype_context",
        "inheritance",
        "population",
        "provenance",
        "other",
    ] = "other"


class EvidenceProvenance(Phase2StrictModel):
    data_origin: Literal["fully_synthetic", "appropriately_public"]
    source_fixture: str
    source_fixture_sha256: str = Field(..., regex=r"^[0-9a-f]{64}$")
    source_case_id: str
    source_variant_id: str
    extraction_method: str = Field(..., min_length=1)
    public_resource_compatibility_note: str
    source_url: Optional[str] = None
    source_release: Optional[str] = None
    license_or_terms_url: Optional[str] = None
    retrieved_at_utc: Optional[str] = None
    source_record_sha256: Optional[str] = Field(None, regex=r"^[0-9a-f]{64}$")


class EvidenceRecord(Phase2StrictModel):
    evidence_id: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    original_source_record_id: str = Field(..., min_length=1)
    snapshot_version: str = Field(..., min_length=1)
    snapshot_date: str = Field(..., regex=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    canonical_variant_id: str = Field(..., min_length=1)
    content: EvidenceContent
    provenance: EvidenceProvenance


class MaterialClaim(Phase2StrictModel):
    claim_id: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)
    evidence_ids: List[str] = Field(default_factory=list)
    interpretation: Literal[
        "supports_attention",
        "argues_against_attention",
        "uncertainty_or_conflict",
    ]
    status: Literal["supported", "contradicted", "conflicting", "insufficient"]

    @validator("evidence_ids")
    def evidence_ids_are_unique(cls, value: List[str]) -> List[str]:
        if len(value) != len(set(value)):
            raise ValueError("claim evidence_ids must be unique")
        return value


class VerifiedClaim(Phase2StrictModel):
    claim_id: str = Field(..., min_length=1)
    variant_id: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)
    evidence_ids: List[str] = Field(default_factory=list)
    status: Literal["supported", "contradicted", "insufficient"]
    reason: str = Field(..., min_length=1)

    @validator("evidence_ids")
    def evidence_ids_are_unique(cls, value: List[str]) -> List[str]:
        if len(value) != len(set(value)):
            raise ValueError("verified evidence_ids must be unique")
        return value


class EvidenceSnapshotManifest(Phase2StrictModel):
    snapshot_version: str = Field(..., min_length=1)
    snapshot_date: str
    record_count: int = Field(..., ge=0)
    evidence_file: str
    evidence_file_sha256: str = Field(..., regex=r"^[0-9a-f]{64}$")
    source_fixture: str
    source_fixture_sha256: str = Field(..., regex=r"^[0-9a-f]{64}$")
    provenance_model: str
    external_live_dependency: Literal[False]
    notes: List[str] = Field(default_factory=list)
    source_metadata: Dict[str, object] = Field(default_factory=dict)
