"""Execution for evidence-grounded V1 and verification-only V2."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ValidationError, root_validator

from genometriage.baseline.provider import LLMProvider
from genometriage.baseline.runner import estimate_cost_usd
from genometriage.benchmark.loader import file_sha256
from genometriage.evidence import EvidenceStore
from genometriage.models.phase2 import MaterialClaim, VerifiedClaim
from genometriage.models.schema import (
    BenchmarkCase,
    CaseRunRecord,
    Prediction,
    RankedVariant,
    SystemRun,
    TokenUsage,
)
from genometriage.normalization import normalize_candidate

from .prompt import (
    V1_PROMPT_PATH,
    V1_PROMPT_VERSION,
    V2_PROMPT_PATH,
    V2_PROMPT_VERSION,
    combined_prompt_sha256,
    load_prompt,
    prompt_sha256,
    render_v1_prompt,
    render_v2_prompt,
    v1_response_schema,
    v2_response_schema,
)


BENCHMARK_VERSION = "benchmark_v1"


class V1LLMOutput(BaseModel):
    ranked_variants: List[RankedVariant]
    escalated_uncertainty: bool
    notes: Optional[str]

    class Config:
        extra = "forbid"

    @root_validator
    def at_most_three(cls, values: Dict[str, object]) -> Dict[str, object]:
        if len(values.get("ranked_variants") or []) > 3:
            raise ValueError("V1 may send at most three variants for review")
        return values


class V2LLMOutput(BaseModel):
    verified_claims: List[VerifiedClaim]
    notes: Optional[str]

    class Config:
        extra = "forbid"


class _RateLimitedSystem:
    def __init__(self, min_request_interval_seconds: float) -> None:
        if min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds cannot be negative")
        self.min_request_interval_seconds = min_request_interval_seconds
        self._last_request_started_at: Optional[float] = None

    def _call(
        self,
        provider: LLMProvider,
        prompt: str,
        response_schema: Dict[str, object],
    ):
        if self._last_request_started_at is not None:
            elapsed = time.perf_counter() - self._last_request_started_at
            remaining = self.min_request_interval_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        started = time.perf_counter()
        self._last_request_started_at = started
        response = provider.complete(prompt, response_schema)
        return response, time.perf_counter() - started


class EvidenceGroundedSystem(_RateLimitedSystem):
    """Normalize, retrieve exact local evidence, then make one prioritization call."""

    system_name = "evidence-grounded-v1"
    prompt_version = V1_PROMPT_VERSION

    def __init__(
        self,
        provider: LLMProvider,
        store: EvidenceStore,
        *,
        prompt_path: Path = V1_PROMPT_PATH,
        min_request_interval_seconds: float = 0.0,
        benchmark_version: str = BENCHMARK_VERSION,
    ) -> None:
        super().__init__(min_request_interval_seconds)
        self.provider = provider
        self.store = store
        self.template = load_prompt(prompt_path)
        self.benchmark_version = benchmark_version

    @property
    def model(self) -> str:
        return self.provider.model

    @property
    def prompt_hash(self) -> str:
        return prompt_sha256(self.template)

    @property
    def execution_config(self) -> Dict[str, object]:
        return {
            **self.provider.execution_config,
            "min_request_interval_seconds": self.min_request_interval_seconds,
            "normalization": "literal_vcf_subset_v1",
            "retrieval": "exact_canonical_variant_match_v1",
            "claim_identifiers": "deterministic_case_variant_order_v1",
            "evidence_snapshot_version": self.store.manifest.snapshot_version,
            "evidence_snapshot_sha256": self.store.manifest.evidence_file_sha256,
            "max_review_variants": 3,
        }

    def run_case(self, case: BenchmarkCase) -> Prediction:
        prompt = render_v1_prompt(case, self.store, self.template)
        response, runtime = self._call(self.provider, prompt, v1_response_schema())
        try:
            parsed = V1LLMOutput.parse_raw(response.output_text)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ValueError(f"V1 model returned malformed ranking JSON: {exc}") from exc
        parsed = self._assign_claim_ids(case, parsed)
        self._validate_output(case, parsed)
        return Prediction(
            case_id=case.case_id,
            system=self.system_name,
            prompt_version=self.prompt_version,
            model=self.model,
            ranked_variants=parsed.ranked_variants,
            escalated_uncertainty=parsed.escalated_uncertainty,
            notes=parsed.notes,
            runtime_seconds=runtime,
            usage=TokenUsage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                total_tokens=response.total_tokens,
            ),
            estimated_cost_usd=estimate_cost_usd(
                response.input_tokens, response.output_tokens
            ),
            external_model_runtime_seconds=runtime,
            model_call_count=response.request_attempt_count,
            provider_retry_errors=list(response.retry_errors),
        )

    @staticmethod
    def _assign_claim_ids(case: BenchmarkCase, output: V1LLMOutput) -> V1LLMOutput:
        """Replace model bookkeeping IDs without changing any substantive field."""

        ranked_variants = []
        for ranked in output.ranked_variants:
            claims = [
                MaterialClaim(
                    claim_id=f"{case.case_id}:{ranked.variant_id}:C{index}",
                    claim=claim.claim,
                    evidence_ids=claim.evidence_ids,
                    interpretation=claim.interpretation,
                    status=claim.status,
                )
                for index, claim in enumerate(ranked.claims, start=1)
            ]
            ranked_variants.append(ranked.copy(update={"claims": claims}))
        return output.copy(update={"ranked_variants": ranked_variants})

    def _validate_output(self, case: BenchmarkCase, output: V1LLMOutput) -> None:
        candidate_by_id = {
            candidate.variant_id: candidate for candidate in case.candidate_variants
        }
        claim_ids: List[str] = []
        for ranked in output.ranked_variants:
            if ranked.variant_id not in candidate_by_id:
                raise ValueError(f"V1 ranked unknown candidate: {ranked.variant_id}")
            candidate = candidate_by_id[ranked.variant_id]
            retrieved_ids = {
                record.evidence_id
                for record in self.store.retrieve(normalize_candidate(candidate))
            }
            if not set(ranked.evidence_source_ids).issubset(retrieved_ids):
                raise ValueError(
                    f"V1 cited evidence not retrieved for {ranked.variant_id}"
                )
            if not ranked.claims:
                raise ValueError(f"V1 ranked variant has no material claims: {ranked.variant_id}")
            for claim in ranked.claims:
                claim_ids.append(claim.claim_id)
                if not set(claim.evidence_ids).issubset(retrieved_ids):
                    raise ValueError(
                        f"V1 claim cited evidence not retrieved for {ranked.variant_id}"
                    )
                if claim.status != "insufficient" and not claim.evidence_ids:
                    raise ValueError(
                        f"V1 {claim.status} claim requires evidence IDs: {claim.claim_id}"
                    )
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("V1 claim IDs must be unique within a case")

    def run(
        self,
        cases: Sequence[BenchmarkCase],
        *,
        cases_path: Path,
        fail_fast: bool = False,
        initial_records: Sequence[CaseRunRecord] = (),
        created_at_utc: Optional[datetime] = None,
        checkpoint_callback: Optional[Callable[[SystemRun], None]] = None,
    ) -> SystemRun:
        return _execute_cases(
            cases,
            run_case=self.run_case,
            system=self.system_name,
            prompt_version=self.prompt_version,
            model=self.model,
            prompt_hash=self.prompt_hash,
            execution_config=self.execution_config,
            benchmark_version=self.benchmark_version,
            cases_path=cases_path,
            fail_fast=fail_fast,
            initial_records=initial_records,
            created_at_utc=created_at_utc,
            checkpoint_callback=checkpoint_callback,
        )


class VerificationSystem(_RateLimitedSystem):
    """Verify V1 claims once, then deterministically remove unsupported candidates."""

    system_name = "verified-v2"
    prompt_version = V2_PROMPT_VERSION

    def __init__(
        self,
        provider: LLMProvider,
        store: EvidenceStore,
        v1_run: SystemRun,
        *,
        prompt_path: Path = V2_PROMPT_PATH,
        v1_prompt_path: Path = V1_PROMPT_PATH,
        min_request_interval_seconds: float = 0.0,
    ) -> None:
        super().__init__(min_request_interval_seconds)
        if v1_run.run_status != "completed":
            raise ValueError("V2 requires a completed V1 run")
        self.provider = provider
        self.store = store
        self.v1_run = v1_run
        self.benchmark_version = v1_run.benchmark_version
        self.template = load_prompt(prompt_path)
        self.v1_template = load_prompt(v1_prompt_path)
        expected_v1 = {
            "system": EvidenceGroundedSystem.system_name,
            "prompt_version": V1_PROMPT_VERSION,
            "prompt_sha256": prompt_sha256(self.v1_template),
        }
        mismatches = [
            field
            for field, expected in expected_v1.items()
            if getattr(v1_run, field) != expected
        ]
        if (
            v1_run.execution_config.get("evidence_snapshot_sha256")
            != store.manifest.evidence_file_sha256
        ):
            mismatches.append("evidence_snapshot_sha256")
        if mismatches:
            raise ValueError(
                "V2 source run does not match the frozen V1 contract: "
                + ", ".join(mismatches)
            )
        self._v1_by_case = {
            record.case_id: record
            for record in v1_run.records
            if record.status == "completed"
        }

    @property
    def model(self) -> str:
        return f"{self.v1_run.model}+{self.provider.model}"

    @property
    def prompt_hash(self) -> str:
        return combined_prompt_sha256(self.v1_template, self.template)

    @property
    def execution_config(self) -> Dict[str, object]:
        v1_digest = hashlib.sha256(
            self.v1_run.json(sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "prioritizer_model": self.v1_run.model,
            "verifier_model": self.provider.model,
            "verifier": self.provider.execution_config,
            "min_request_interval_seconds": self.min_request_interval_seconds,
            "evidence_snapshot_version": self.store.manifest.snapshot_version,
            "evidence_snapshot_sha256": self.store.manifest.evidence_file_sha256,
            "v1_run_sha256": v1_digest,
            "filter_policy": "retain_supported_attention_or_supported_uncertainty_v1",
        }

    def run_case(self, case: BenchmarkCase) -> Prediction:
        v1_record = self._v1_by_case.get(case.case_id)
        if v1_record is None or v1_record.prediction is None:
            raise ValueError(f"V2 has no completed V1 prediction for {case.case_id}")
        v1_prediction = v1_record.prediction
        expected = _claims_by_id(v1_prediction.ranked_variants)
        if expected:
            prompt = render_v2_prompt(
                case, v1_prediction.ranked_variants, self.store, self.template
            )
            response, verifier_runtime = self._call(
                self.provider, prompt, v2_response_schema()
            )
            try:
                parsed = V2LLMOutput.parse_raw(response.output_text)
            except (ValidationError, json.JSONDecodeError) as exc:
                raise ValueError(f"V2 model returned malformed verification JSON: {exc}") from exc
            self._validate_verification(expected, parsed.verified_claims)
            verifier_usage = TokenUsage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                total_tokens=response.total_tokens,
            )
            verifier_cost = estimate_cost_usd(
                response.input_tokens, response.output_tokens
            )
            verifier_notes = parsed.notes
            verified_claims = parsed.verified_claims
        else:
            verifier_runtime = 0.0
            verifier_usage = TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)
            verifier_cost = 0.0 if v1_prediction.estimated_cost_usd is not None else None
            verifier_notes = "No V1 material claims required verification."
            verified_claims = []

        ranked_variants, removed = _finalize_verified_shortlist(
            v1_prediction.ranked_variants, verified_claims
        )
        notes = (
            f"Verification-only stage. Removed candidates: {removed or ['none']}. "
            f"Verifier notes: {verifier_notes or 'none'}"
        )
        return Prediction(
            case_id=case.case_id,
            system=self.system_name,
            prompt_version=self.prompt_version,
            model=self.model,
            ranked_variants=ranked_variants,
            escalated_uncertainty=(
                v1_prediction.escalated_uncertainty
                or bool(removed)
                or any(claim.status != "supported" for claim in verified_claims)
            ),
            notes=notes,
            runtime_seconds=v1_prediction.runtime_seconds + verifier_runtime,
            usage=TokenUsage(
                input_tokens=_sum_usage(
                    v1_prediction.usage.input_tokens, verifier_usage.input_tokens
                ),
                output_tokens=_sum_usage(
                    v1_prediction.usage.output_tokens, verifier_usage.output_tokens
                ),
                total_tokens=_sum_usage(
                    v1_prediction.usage.total_tokens, verifier_usage.total_tokens
                ),
            ),
            estimated_cost_usd=_sum_costs(
                v1_prediction.estimated_cost_usd, verifier_cost
            ),
            verified_claims=verified_claims,
            deterministic_runtime_seconds=v1_prediction.deterministic_runtime_seconds,
            external_model_runtime_seconds=(
                (v1_prediction.external_model_runtime_seconds or v1_prediction.runtime_seconds)
                + verifier_runtime
            ),
            model_call_count=(v1_prediction.model_call_count or 1)
            + (response.request_attempt_count if expected else 0),
            provider_retry_errors=(
                v1_prediction.provider_retry_errors
                + (list(response.retry_errors) if expected else [])
            ),
        )

    @staticmethod
    def _validate_verification(
        expected: Dict[str, Tuple[str, MaterialClaim]],
        verified: Sequence[VerifiedClaim],
    ) -> None:
        actual_ids = [claim.claim_id for claim in verified]
        if len(actual_ids) != len(set(actual_ids)):
            raise ValueError("V2 returned duplicate claim IDs")
        if set(actual_ids) != set(expected):
            raise ValueError("V2 must verify every V1 claim exactly once")
        for claim in verified:
            expected_variant, expected_claim = expected[claim.claim_id]
            if (
                claim.variant_id != expected_variant
                or claim.claim != expected_claim.claim
                or claim.evidence_ids != expected_claim.evidence_ids
            ):
                raise ValueError(
                    f"V2 altered immutable claim fields: {claim.claim_id}"
                )

    def run(
        self,
        cases: Sequence[BenchmarkCase],
        *,
        cases_path: Path,
        fail_fast: bool = False,
        initial_records: Sequence[CaseRunRecord] = (),
        created_at_utc: Optional[datetime] = None,
        checkpoint_callback: Optional[Callable[[SystemRun], None]] = None,
    ) -> SystemRun:
        return _execute_cases(
            cases,
            run_case=self.run_case,
            system=self.system_name,
            prompt_version=self.prompt_version,
            model=self.model,
            prompt_hash=self.prompt_hash,
            execution_config=self.execution_config,
            benchmark_version=self.benchmark_version,
            cases_path=cases_path,
            fail_fast=fail_fast,
            initial_records=initial_records,
            created_at_utc=created_at_utc,
            checkpoint_callback=checkpoint_callback,
        )


def _claims_by_id(
    ranked_variants: Sequence[RankedVariant],
) -> Dict[str, Tuple[str, MaterialClaim]]:
    result: Dict[str, Tuple[str, MaterialClaim]] = {}
    for ranked in ranked_variants:
        for claim in ranked.claims:
            if claim.claim_id in result:
                raise ValueError(f"duplicate V1 claim ID: {claim.claim_id}")
            result[claim.claim_id] = (ranked.variant_id, claim)
    return result


def _finalize_verified_shortlist(
    ranked_variants: Sequence[RankedVariant],
    verified_claims: Sequence[VerifiedClaim],
) -> Tuple[List[RankedVariant], List[str]]:
    verified_by_id = {claim.claim_id: claim for claim in verified_claims}
    retained: List[RankedVariant] = []
    removed: List[str] = []
    for ranked in ranked_variants:
        updated_claims = []
        retaining_claims = []
        for original in ranked.claims:
            verified = verified_by_id[original.claim_id]
            updated = MaterialClaim(
                claim_id=original.claim_id,
                claim=original.claim,
                evidence_ids=original.evidence_ids,
                interpretation=original.interpretation,
                status=verified.status,
            )
            updated_claims.append(updated)
            if verified.status == "supported" and original.interpretation in {
                "supports_attention",
                "uncertainty_or_conflict",
            }:
                retaining_claims.append(updated)
        if not retaining_claims:
            removed.append(ranked.variant_id)
            continue
        evidence_ids = sorted(
            {
                evidence_id
                for claim in retaining_claims
                for evidence_id in claim.evidence_ids
            }
        )
        retained.append(
            RankedVariant(
                variant_id=ranked.variant_id,
                rank=len(retained) + 1,
                reason="Independent verification retained: "
                + "; ".join(claim.claim for claim in retaining_claims),
                confidence=ranked.confidence,
                evidence_source_ids=evidence_ids,
                claims=updated_claims,
            )
        )
    return retained, removed


def _sum_usage(first: Optional[int], second: Optional[int]) -> Optional[int]:
    return first + second if first is not None and second is not None else None


def _sum_costs(first: Optional[float], second: Optional[float]) -> Optional[float]:
    return round(first + second, 8) if first is not None and second is not None else None


def _execute_cases(
    cases: Sequence[BenchmarkCase],
    *,
    run_case: Callable[[BenchmarkCase], Prediction],
    system: str,
    prompt_version: str,
    model: str,
    prompt_hash: str,
    execution_config: Dict[str, object],
    benchmark_version: str,
    cases_path: Path,
    fail_fast: bool,
    initial_records: Sequence[CaseRunRecord],
    created_at_utc: Optional[datetime],
    checkpoint_callback: Optional[Callable[[SystemRun], None]],
) -> SystemRun:
    case_ids = [case.case_id for case in cases]
    initial_by_id: Dict[str, CaseRunRecord] = {}
    for record in initial_records:
        if record.case_id in initial_by_id:
            raise ValueError(f"duplicate initial record: {record.case_id}")
        if record.case_id not in case_ids:
            raise ValueError(f"unknown initial record: {record.case_id}")
        if record.status == "completed":
            initial_by_id[record.case_id] = record
    records = [initial_by_id[case_id] for case_id in case_ids if case_id in initial_by_id]
    started_at = created_at_utc or datetime.now(timezone.utc)

    def snapshot(status: str) -> SystemRun:
        return SystemRun(
            run_status=status,
            system=system,
            benchmark_version=benchmark_version,
            prompt_version=prompt_version,
            model=model,
            created_at_utc=started_at,
            benchmark_sha256=file_sha256(Path(cases_path)),
            prompt_sha256=prompt_hash,
            execution_config=execution_config,
            records=records,
        )

    if checkpoint_callback:
        checkpoint_callback(snapshot("in_progress"))
    for case in cases:
        if case.case_id in initial_by_id:
            continue
        try:
            prediction = run_case(case)
            records.append(
                CaseRunRecord(
                    case_id=case.case_id,
                    status="completed",
                    prediction=prediction,
                )
            )
        except Exception as exc:
            if fail_fast:
                raise
            records.append(
                CaseRunRecord(
                    case_id=case.case_id,
                    status="error",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
        if checkpoint_callback:
            checkpoint_callback(snapshot("in_progress"))
    completed = snapshot("completed")
    if checkpoint_callback:
        checkpoint_callback(completed)
    return completed


def validate_resume_run(
    run: SystemRun,
    *,
    system: str,
    prompt_version: str,
    model: str,
    prompt_hash: str,
    execution_config: Dict[str, object],
    cases_path: Path,
    benchmark_version: str = BENCHMARK_VERSION,
) -> None:
    expected = {
        "system": system,
        "benchmark_version": benchmark_version,
        "prompt_version": prompt_version,
        "model": model,
        "benchmark_sha256": file_sha256(Path(cases_path)),
        "prompt_sha256": prompt_hash,
        "execution_config": execution_config,
    }
    mismatches = [key for key, value in expected.items() if getattr(run, key) != value]
    if mismatches:
        raise ValueError(
            "resume checkpoint does not match current run configuration: "
            + ", ".join(mismatches)
        )
