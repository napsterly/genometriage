"""Run deterministic V3 arbitration over a completed V1 artifact."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from genometriage.benchmark.loader import file_sha256
from genometriage.evidence import EvidenceStore
from genometriage.models.schema import (
    BenchmarkCase,
    CaseRunRecord,
    Prediction,
    RankedVariant,
    SystemRun,
)
from genometriage.normalization import normalize_candidate
from genometriage.phase2.prompt import V1_PROMPT_VERSION

from .arbitration import POLICY_VERSION, arbitrate_candidate


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SPEC_PATH = PROJECT_ROOT / "docs" / "CONFLICT_ARBITRATION_SPEC.md"
DEFAULT_SPEC_FREEZE_PATH = (
    PROJECT_ROOT / "docs" / "CONFLICT_ARBITRATION_SPEC_FREEZE.json"
)


class ConflictArbitrationSystem:
    """Filter V1 candidates using the preregistered local evidence policy."""

    system_name = "conflict-arbitrated-v3"
    prompt_version = f"{V1_PROMPT_VERSION}+{POLICY_VERSION}"

    def __init__(
        self,
        store: EvidenceStore,
        v1_run: SystemRun,
        *,
        spec_path: Path = DEFAULT_SPEC_PATH,
        freeze_path: Path = DEFAULT_SPEC_FREEZE_PATH,
    ) -> None:
        if v1_run.run_status != "completed":
            raise ValueError("V3 requires a completed V1 run")
        if v1_run.system != "evidence-grounded-v1":
            raise ValueError("V3 source must be an evidence-grounded-v1 run")
        if v1_run.prompt_version != V1_PROMPT_VERSION:
            raise ValueError("V3 source V1 prompt version does not match the frozen contract")
        if (
            v1_run.execution_config.get("evidence_snapshot_sha256")
            != store.manifest.evidence_file_sha256
        ):
            raise ValueError("V3 source V1 run and evidence snapshot hashes differ")
        self.store = store
        self.v1_run = v1_run
        self.spec_path = Path(spec_path)
        self.freeze_path = Path(freeze_path)
        self.spec_sha256 = self._validate_spec_freeze()
        self._v1_by_case = {
            record.case_id: record
            for record in v1_run.records
            if record.status == "completed"
        }

    def _validate_spec_freeze(self) -> str:
        try:
            freeze = json.loads(self.freeze_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid arbitration freeze manifest: {exc}") from exc
        actual = file_sha256(self.spec_path)
        if freeze.get("policy_version") != POLICY_VERSION:
            raise ValueError("arbitration policy version does not match freeze manifest")
        if freeze.get("spec_sha256") != actual:
            raise ValueError("arbitration specification hash does not match freeze manifest")
        return actual

    @property
    def model(self) -> str:
        return self.v1_run.model

    @property
    def prompt_hash(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.v1_run.prompt_sha256.encode("ascii"))
        digest.update(b"\0")
        digest.update(self.spec_sha256.encode("ascii"))
        return digest.hexdigest()

    @property
    def execution_config(self) -> Dict[str, object]:
        source_digest = hashlib.sha256(
            self.v1_run.json(sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "source_system": self.v1_run.system,
            "source_prompt_version": self.v1_run.prompt_version,
            "source_prompt_sha256": self.v1_run.prompt_sha256,
            "source_v1_run_sha256": source_digest,
            "evidence_snapshot_version": self.store.manifest.snapshot_version,
            "evidence_snapshot_sha256": self.store.manifest.evidence_file_sha256,
            "arbitration_policy_version": POLICY_VERSION,
            "arbitration_spec_sha256": self.spec_sha256,
            "additional_model_calls_per_case": 0,
            "candidate_promotion_allowed": False,
            "relative_reranking_allowed": False,
        }

    def run_case(self, case: BenchmarkCase) -> Prediction:
        source_record = self._v1_by_case.get(case.case_id)
        if source_record is None or source_record.prediction is None:
            raise ValueError(f"V3 has no completed V1 prediction for {case.case_id}")
        source = source_record.prediction
        candidate_by_id = {
            candidate.variant_id: candidate for candidate in case.candidate_variants
        }

        started = time.perf_counter()
        audits = []
        retained: List[RankedVariant] = []
        for ranked in source.ranked_variants:
            candidate = candidate_by_id.get(ranked.variant_id)
            if candidate is None:
                raise ValueError(f"V1 ranked unknown candidate: {ranked.variant_id}")
            evidence = self.store.retrieve(normalize_candidate(candidate))
            audit = arbitrate_candidate(ranked.variant_id, ranked.rank, evidence)
            audits.append(audit)
            if not audit.retained_for_review:
                continue
            all_evidence_ids = sorted(
                set(ranked.evidence_source_ids)
                | {record.evidence_id for record in evidence}
            )
            retained.append(
                RankedVariant(
                    variant_id=ranked.variant_id,
                    rank=len(retained) + 1,
                    reason=f"{audit.reason} V1 rationale: {ranked.reason}",
                    confidence=ranked.confidence,
                    evidence_source_ids=all_evidence_ids,
                    claims=ranked.claims,
                )
            )
        arbitration_runtime = time.perf_counter() - started
        removed = [audit.variant_id for audit in audits if not audit.retained_for_review]
        state_summary = ", ".join(
            f"{audit.variant_id}={audit.state}" for audit in audits
        ) or "no V1 candidates"
        return Prediction(
            case_id=case.case_id,
            system=self.system_name,
            prompt_version=self.prompt_version,
            model=self.model,
            ranked_variants=retained,
            escalated_uncertainty=(
                source.escalated_uncertainty
                or bool(removed)
                or any(audit.state == "conflicting_evidence" for audit in audits)
                or not retained
            ),
            notes=(
                f"Deterministic arbitration states: {state_summary}. "
                f"Removed from final shortlist: {removed or ['none']}."
            ),
            runtime_seconds=source.runtime_seconds + arbitration_runtime,
            usage=source.usage,
            estimated_cost_usd=source.estimated_cost_usd,
            verified_claims=source.verified_claims,
            arbitration_records=audits,
            deterministic_runtime_seconds=(
                (source.deterministic_runtime_seconds or 0.0) + arbitration_runtime
            ),
            external_model_runtime_seconds=(
                source.external_model_runtime_seconds or source.runtime_seconds
            ),
            model_call_count=(source.model_call_count or 1),
            provider_retry_errors=source.provider_retry_errors,
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
        cases_path = Path(cases_path)
        actual_benchmark_hash = file_sha256(cases_path)
        if actual_benchmark_hash != self.v1_run.benchmark_sha256:
            raise ValueError("V3 cases hash does not match its V1 source run")
        case_ids = [case.case_id for case in cases]
        initial_by_id: Dict[str, CaseRunRecord] = {}
        for record in initial_records:
            if record.case_id in initial_by_id:
                raise ValueError(f"duplicate initial record: {record.case_id}")
            if record.case_id not in case_ids:
                raise ValueError(f"unknown initial record: {record.case_id}")
            if record.status == "completed":
                initial_by_id[record.case_id] = record
        records = [
            initial_by_id[case_id] for case_id in case_ids if case_id in initial_by_id
        ]
        started_at = created_at_utc or datetime.now(timezone.utc)

        def snapshot(status: str) -> SystemRun:
            return SystemRun(
                run_status=status,
                system=self.system_name,
                benchmark_version=self.v1_run.benchmark_version,
                prompt_version=self.prompt_version,
                model=self.model,
                created_at_utc=started_at,
                benchmark_sha256=actual_benchmark_hash,
                prompt_sha256=self.prompt_hash,
                execution_config=self.execution_config,
                records=records,
            )

        if checkpoint_callback:
            checkpoint_callback(snapshot("in_progress"))
        for case in cases:
            if case.case_id in initial_by_id:
                continue
            try:
                prediction = self.run_case(case)
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

    def validate_resume_run(self, run: SystemRun, *, cases_path: Path) -> None:
        expected = {
            "system": self.system_name,
            "benchmark_version": self.v1_run.benchmark_version,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "benchmark_sha256": file_sha256(Path(cases_path)),
            "prompt_sha256": self.prompt_hash,
            "execution_config": self.execution_config,
        }
        mismatches = [
            key for key, value in expected.items() if getattr(run, key) != value
        ]
        if mismatches:
            raise ValueError(
                "resume checkpoint does not match current V3 configuration: "
                + ", ".join(mismatches)
            )
