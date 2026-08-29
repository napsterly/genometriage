"""Versioned Phase 2 prompt rendering and strict response schemas."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Sequence

from genometriage.benchmark.loader import PROJECT_ROOT
from genometriage.evidence import EvidenceStore
from genometriage.models.phase2 import MaterialClaim
from genometriage.models.schema import BenchmarkCase, RankedVariant
from genometriage.normalization import normalize_candidate


V1_PROMPT_VERSION = "evidence_grounded_v1"
V2_PROMPT_VERSION = "independent_verifier_v1"
V1_PROMPT_PATH = PROJECT_ROOT / "prompts" / f"{V1_PROMPT_VERSION}.md"
V2_PROMPT_PATH = PROJECT_ROOT / "prompts" / f"{V2_PROMPT_VERSION}.md"


def load_prompt(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def prompt_sha256(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def combined_prompt_sha256(*templates: str) -> str:
    digest = hashlib.sha256()
    for template in templates:
        digest.update(template.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def render_v1_prompt(case: BenchmarkCase, store: EvidenceStore, template: str) -> str:
    candidates = []
    for candidate in case.candidate_variants:
        canonical = normalize_candidate(candidate)
        candidates.append(
            {
                "variant": canonical.dict(),
                "zygosity": candidate.zygosity,
                "observed_inheritance": candidate.observed_inheritance,
                "population_allele_frequency": candidate.population_allele_frequency,
                "retrieved_evidence": [
                    record.dict() for record in store.retrieve(canonical)
                ],
            }
        )
    payload = {
        "case_id": case.case_id,
        "data_origin": case.data_origin,
        "safety_disclaimer": case.safety_disclaimer,
        "context": case.context.dict(),
        "normalized_candidates": candidates,
    }
    serialized = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
    return f"{template.rstrip()}\n\n## Retrieved case package\n\n```json\n{serialized}\n```\n"


def render_v2_prompt(
    case: BenchmarkCase,
    ranked_variants: Sequence[RankedVariant],
    store: EvidenceStore,
    template: str,
) -> str:
    candidate_by_id = {candidate.variant_id: candidate for candidate in case.candidate_variants}
    claims = []
    for ranked in ranked_variants:
        canonical = normalize_candidate(candidate_by_id[ranked.variant_id])
        records = {record.evidence_id: record for record in store.retrieve(canonical)}
        for claim in ranked.claims:
            claims.append(
                {
                    "claim_id": claim.claim_id,
                    "variant_id": ranked.variant_id,
                    "claim": claim.claim,
                    "evidence_ids": claim.evidence_ids,
                    "interpretation": claim.interpretation,
                    "prioritizer_status": claim.status,
                    "cited_evidence": [
                        records[evidence_id].dict()
                        for evidence_id in claim.evidence_ids
                        if evidence_id in records
                    ],
                }
            )
    payload = {
        "case_id": case.case_id,
        "safety_disclaimer": case.safety_disclaimer,
        "claims_to_verify": claims,
    }
    serialized = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
    return f"{template.rstrip()}\n\n## Claims and frozen evidence\n\n```json\n{serialized}\n```\n"


def _claim_schema() -> Dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["claim_id", "claim", "evidence_ids", "interpretation", "status"],
        "properties": {
            "claim_id": {"type": "string", "minLength": 1},
            "claim": {"type": "string", "minLength": 1},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "interpretation": {
                "type": "string",
                "enum": [
                    "supports_attention",
                    "argues_against_attention",
                    "uncertainty_or_conflict",
                ],
            },
            "status": {
                "type": "string",
                "enum": ["supported", "contradicted", "conflicting", "insufficient"],
            },
        },
    }


def v1_response_schema() -> Dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["ranked_variants", "escalated_uncertainty", "notes"],
        "properties": {
            "ranked_variants": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "variant_id",
                        "rank",
                        "reason",
                        "confidence",
                        "evidence_source_ids",
                        "claims",
                    ],
                    "properties": {
                        "variant_id": {"type": "string", "minLength": 1},
                        "rank": {"type": "integer", "minimum": 1},
                        "reason": {"type": "string", "minLength": 1},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidence_source_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "claims": {
                            "type": "array",
                            "minItems": 1,
                            "items": _claim_schema(),
                        },
                    },
                },
            },
            "escalated_uncertainty": {"type": "boolean"},
            "notes": {"type": ["string", "null"]},
        },
    }


def v2_response_schema() -> Dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["verified_claims", "notes"],
        "properties": {
            "verified_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "claim_id",
                        "variant_id",
                        "claim",
                        "evidence_ids",
                        "status",
                        "reason",
                    ],
                    "properties": {
                        "claim_id": {"type": "string", "minLength": 1},
                        "variant_id": {"type": "string", "minLength": 1},
                        "claim": {"type": "string", "minLength": 1},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "status": {
                            "type": "string",
                            "enum": ["supported", "contradicted", "insufficient"],
                        },
                        "reason": {"type": "string", "minLength": 1},
                    },
                },
            },
            "notes": {"type": ["string", "null"]},
        },
    }
