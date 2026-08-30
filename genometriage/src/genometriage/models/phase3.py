"""Phase 3 contracts for deterministic evidence-conflict arbitration."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, validator


class Phase3StrictModel(BaseModel):
    class Config:
        extra = "forbid"
        validate_assignment = True


class ArbitrationRecord(Phase3StrictModel):
    variant_id: str = Field(..., min_length=1)
    source_rank: int = Field(..., gt=0)
    state: Literal[
        "retain",
        "deprioritize",
        "insufficient_evidence",
        "conflicting_evidence",
    ]
    support_score: int = Field(..., ge=0)
    counter_score: int = Field(..., ge=0)
    uncertainty_score: int = Field(..., ge=0)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    counterevidence_ids: List[str] = Field(default_factory=list)
    uncertainty_evidence_ids: List[str] = Field(default_factory=list)
    contextual_strong_counter_ids: List[str] = Field(default_factory=list)
    fired_rule: Literal[
        "1_insufficient_no_directional_evidence",
        "2_counterevidence_only",
        "3_contextual_strong_counter",
        "4_aggregate_counter_dominance",
        "5_below_support_threshold",
        "6_material_conflict_or_uncertainty",
        "7_unopposed_support",
    ]
    retained_for_review: bool
    reason: str = Field(..., min_length=1)

    @validator(
        "supporting_evidence_ids",
        "counterevidence_ids",
        "uncertainty_evidence_ids",
        "contextual_strong_counter_ids",
    )
    def evidence_ids_are_unique(cls, value: List[str]) -> List[str]:
        if len(value) != len(set(value)):
            raise ValueError("arbitration evidence IDs must be unique")
        return value
