"""Execution logic for the intentionally simple one-call baseline."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from pydantic import BaseModel, ValidationError

from genometriage.benchmark.loader import file_sha256
from genometriage.models.schema import (
    BenchmarkCase,
    CaseRunRecord,
    Prediction,
    RankedVariant,
    SystemRun,
    TokenUsage,
)

from .prompt import (
    DEFAULT_PROMPT_PATH,
    PROMPT_VERSION,
    baseline_response_schema,
    load_prompt_template,
    prompt_sha256,
    render_prompt,
)
from .provider import LLMProvider


BENCHMARK_VERSION = "benchmark_v1"


class BaselineLLMOutput(BaseModel):
    ranked_variants: List[RankedVariant]
    escalated_uncertainty: bool
    notes: Optional[str]

    class Config:
        extra = "forbid"


class BaselineSystem:
    """A case-to-one-LLM-call system with no retrieval or verification loop."""

    system_name = "baseline"

    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_path: Path = DEFAULT_PROMPT_PATH,
        system_name: str = "baseline",
        min_request_interval_seconds: float = 0.0,
    ) -> None:
        if min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds cannot be negative")
        self.provider = provider
        self.prompt_path = Path(prompt_path)
        self.system_name = system_name
        self.min_request_interval_seconds = min_request_interval_seconds
        self._last_request_started_at: Optional[float] = None
        self.template = load_prompt_template(self.prompt_path)

    def run_case(self, case: BenchmarkCase) -> Prediction:
        prompt = render_prompt(case, self.template)
        self._wait_for_request_slot()
        started = time.perf_counter()
        self._last_request_started_at = started
        response = self.provider.complete(prompt, baseline_response_schema())
        runtime = time.perf_counter() - started
        try:
            parsed = BaselineLLMOutput.parse_raw(response.output_text)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ValueError(f"model returned malformed ranking JSON: {exc}") from exc

        cost = estimate_cost_usd(response.input_tokens, response.output_tokens)
        return Prediction(
            case_id=case.case_id,
            system=self.system_name,
            prompt_version=PROMPT_VERSION,
            model=self.provider.model,
            ranked_variants=parsed.ranked_variants,
            escalated_uncertainty=parsed.escalated_uncertainty,
            notes=parsed.notes,
            runtime_seconds=runtime,
            usage=TokenUsage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                total_tokens=response.total_tokens,
            ),
            estimated_cost_usd=cost,
        )

    def _wait_for_request_slot(self) -> None:
        if self._last_request_started_at is None:
            return
        elapsed = time.perf_counter() - self._last_request_started_at
        remaining = self.min_request_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

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
        benchmark_hash = file_sha256(Path(cases_path))
        template_hash = prompt_sha256(self.template)

        def snapshot(run_status: str) -> SystemRun:
            return SystemRun(
                run_status=run_status,
                system=self.system_name,
                benchmark_version=BENCHMARK_VERSION,
                prompt_version=PROMPT_VERSION,
                model=self.provider.model,
                created_at_utc=started_at,
                benchmark_sha256=benchmark_hash,
                prompt_sha256=template_hash,
                execution_config={
                    **self.provider.execution_config,
                    "min_request_interval_seconds": self.min_request_interval_seconds,
                },
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

    @property
    def execution_config(self) -> Dict[str, object]:
        return {
            **self.provider.execution_config,
            "min_request_interval_seconds": self.min_request_interval_seconds,
        }


def estimate_cost_usd(
    input_tokens: Optional[int], output_tokens: Optional[int]
) -> Optional[float]:
    input_rate = os.getenv("GENOMETRIAGE_INPUT_COST_PER_MILLION")
    output_rate = os.getenv("GENOMETRIAGE_OUTPUT_COST_PER_MILLION")
    if input_tokens is None or output_tokens is None or not input_rate or not output_rate:
        return None
    try:
        cost = (
            input_tokens * float(input_rate) + output_tokens * float(output_rate)
        ) / 1_000_000
    except ValueError as exc:
        raise ValueError("cost environment variables must be numeric") from exc
    if cost < 0:
        raise ValueError("cost environment variables cannot be negative")
    return round(cost, 8)


def write_system_run(run: SystemRun, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    temporary_path.write_text(run.json(indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(output_path)


def load_system_run(path: Path) -> SystemRun:
    return SystemRun.parse_raw(Path(path).read_text(encoding="utf-8"))


def validate_resume_run(
    run: SystemRun,
    system: BaselineSystem,
    *,
    cases_path: Path,
) -> None:
    """Reject checkpoints produced by a different benchmark configuration."""

    expected = {
        "system": system.system_name,
        "benchmark_version": BENCHMARK_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": system.provider.model,
        "benchmark_sha256": file_sha256(Path(cases_path)),
        "prompt_sha256": prompt_sha256(system.template),
        "execution_config": system.execution_config,
    }
    actual = {key: getattr(run, key) for key in expected}
    mismatches = [key for key in expected if actual[key] != expected[key]]
    if mismatches:
        raise ValueError(
            "resume checkpoint does not match current run configuration: "
            + ", ".join(mismatches)
        )
