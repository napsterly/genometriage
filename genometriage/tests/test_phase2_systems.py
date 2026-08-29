from __future__ import annotations

import json
from datetime import datetime, timezone

from conftest import FakeProvider
from genometriage.evidence import EvidenceStore
from genometriage.models.phase2 import MaterialClaim
from genometriage.models.schema import (
    CaseRunRecord,
    Prediction,
    RankedVariant,
    SystemRun,
)
from genometriage.phase2.prompt import (
    load_prompt,
    prompt_sha256,
    render_v1_prompt,
    V1_PROMPT_PATH,
)
from genometriage.phase2.runner import EvidenceGroundedSystem, VerificationSystem


def _v1_output() -> str:
    return json.dumps(
        {
            "ranked_variants": [
                {
                    "variant_id": "GT001-V1",
                    "rank": 1,
                    "reason": "Exact synthetic evidence supports expert attention.",
                    "confidence": 0.9,
                    "evidence_source_ids": ["GT001-E1"],
                    "claims": [
                        {
                            "claim_id": "GT001-C1",
                            "claim": "The exact allele has strong synthetic functional support.",
                            "evidence_ids": ["GT001-E1"],
                            "interpretation": "supports_attention",
                            "status": "supported",
                        }
                    ],
                }
            ],
            "escalated_uncertainty": False,
            "notes": None,
        }
    )


def test_v1_prompt_uses_retrieved_snapshot_without_answers(benchmark_bundle) -> None:
    prompt = render_v1_prompt(
        benchmark_bundle.cases[0], EvidenceStore.load(), load_prompt(V1_PROMPT_PATH)
    )
    assert "GT001-E1" in prompt
    assert "relevant_variant_ids" not in prompt
    assert "ground_truth" not in prompt


def test_v1_runs_one_grounded_call_and_limits_review(benchmark_bundle) -> None:
    provider = FakeProvider([_v1_output()])
    system = EvidenceGroundedSystem(provider, EvidenceStore.load())
    prediction = system.run_case(benchmark_bundle.cases[0])
    assert len(provider.prompts) == 1
    assert prediction.system == "evidence-grounded-v1"
    assert [item.variant_id for item in prediction.ranked_variants] == ["GT001-V1"]
    assert prediction.ranked_variants[0].claims[0].claim_id == "GT-001:GT001-V1:C1"


def test_v1_replaces_duplicate_model_claim_ids_deterministically(benchmark_bundle) -> None:
    payload = json.loads(_v1_output())
    duplicate = dict(payload["ranked_variants"][0]["claims"][0])
    duplicate["claim"] = "A second material claim."
    payload["ranked_variants"][0]["claims"].append(duplicate)
    provider = FakeProvider([json.dumps(payload)])
    prediction = EvidenceGroundedSystem(provider, EvidenceStore.load()).run_case(
        benchmark_bundle.cases[0]
    )
    assert [claim.claim_id for claim in prediction.ranked_variants[0].claims] == [
        "GT-001:GT001-V1:C1",
        "GT-001:GT001-V1:C2",
    ]


def test_v2_verifies_instead_of_reprioritizing_and_removes_weak_candidate(
    benchmark_bundle,
) -> None:
    claims = [
        MaterialClaim(
            claim_id="GT001-C1",
            claim="The exact allele has strong synthetic functional support.",
            evidence_ids=["GT001-E1"],
            interpretation="supports_attention",
            status="supported",
        ),
        MaterialClaim(
            claim_id="GT001-C2",
            claim="The common inherited allele argues against attention.",
            evidence_ids=["GT001-E3"],
            interpretation="argues_against_attention",
            status="supported",
        ),
    ]
    v1_prediction = Prediction(
        case_id="GT-001",
        system="evidence-grounded-v1",
        prompt_version="evidence_grounded_v1",
        model="fake-prioritizer",
        ranked_variants=[
            RankedVariant(
                variant_id="GT001-V1",
                rank=1,
                reason="positive",
                confidence=0.9,
                evidence_source_ids=["GT001-E1"],
                claims=[claims[0]],
            ),
            RankedVariant(
                variant_id="GT001-V2",
                rank=2,
                reason="weak",
                confidence=0.3,
                evidence_source_ids=["GT001-E3"],
                claims=[claims[1]],
            ),
        ],
        escalated_uncertainty=False,
        runtime_seconds=0.1,
    )
    v1_run = SystemRun(
        system="evidence-grounded-v1",
        benchmark_version="benchmark_v1",
        prompt_version="evidence_grounded_v1",
        model="fake-prioritizer",
        created_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        benchmark_sha256="a" * 64,
        prompt_sha256=prompt_sha256(load_prompt(V1_PROMPT_PATH)),
        execution_config={
            "evidence_snapshot_sha256": EvidenceStore.load().manifest.evidence_file_sha256
        },
        records=[
            CaseRunRecord(
                case_id="GT-001", status="completed", prediction=v1_prediction
            )
        ],
    )
    verifier_output = json.dumps(
        {
            "verified_claims": [
                {
                    "claim_id": "GT001-C1",
                    "variant_id": "GT001-V1",
                    "claim": claims[0].claim,
                    "evidence_ids": ["GT001-E1"],
                    "status": "supported",
                    "reason": "The cited record directly supports the interpretation.",
                },
                {
                    "claim_id": "GT001-C2",
                    "variant_id": "GT001-V2",
                    "claim": claims[1].claim,
                    "evidence_ids": ["GT001-E3"],
                    "status": "supported",
                    "reason": "The cited record directly supports the negative interpretation.",
                },
            ],
            "notes": None,
        }
    )
    provider = FakeProvider([verifier_output])
    system = VerificationSystem(provider, EvidenceStore.load(), v1_run)
    prediction = system.run_case(benchmark_bundle.cases[0])
    assert len(provider.prompts) == 1
    assert [item.variant_id for item in prediction.ranked_variants] == ["GT001-V1"]
    assert len(prediction.verified_claims) == 2
    assert "GT001-V2" in prediction.notes
