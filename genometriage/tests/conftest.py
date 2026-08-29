from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Dict, List, Optional

import pytest

from genometriage.baseline.provider import ProviderResponse
from genometriage.benchmark.loader import BenchmarkBundle, load_benchmark
from genometriage.models.schema import (
    CaseRunRecord,
    Prediction,
    RankedVariant,
    SystemRun,
)


@pytest.fixture(scope="session")
def benchmark_bundle() -> BenchmarkBundle:
    return load_benchmark()


@pytest.fixture
def tmp_path(request) -> Path:
    """Project-local temp path for hosts that restrict the global temp directory."""

    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", request.node.name)
    path = Path(__file__).parent / ".runtime_tmp" / safe_name
    path.mkdir(parents=True, exist_ok=True)
    return path


class FakeProvider:
    provider_name = "fake"
    default_min_request_interval_seconds = 0.0
    execution_config = {
        "temperature": 0,
        "max_output_tokens": 2000,
        "structured_output": "test_json",
    }
    model = "fake-general-purpose-model"

    def __init__(self, outputs: Optional[List[str]] = None) -> None:
        self.outputs = outputs or [
            '{"ranked_variants":[],"escalated_uncertainty":true,"notes":"No supported candidate."}'
        ]
        self.prompts: List[str] = []

    def complete(self, prompt: str, response_schema: Dict[str, object]) -> ProviderResponse:
        self.prompts.append(prompt)
        index = min(len(self.prompts) - 1, len(self.outputs) - 1)
        return ProviderResponse(
            output_text=self.outputs[index],
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
        )


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


def make_prediction(
    case_id: str,
    ranked_variants: Optional[List[RankedVariant]] = None,
) -> Prediction:
    return Prediction(
        case_id=case_id,
        system="baseline",
        prompt_version="baseline_v1",
        model="fake-general-purpose-model",
        ranked_variants=ranked_variants or [],
        escalated_uncertainty=not bool(ranked_variants),
        notes=None,
        runtime_seconds=0.01,
    )


def make_system_run(bundle: BenchmarkBundle) -> SystemRun:
    return SystemRun(
        system="baseline",
        benchmark_version="benchmark_v1",
        prompt_version="baseline_v1",
        model="fake-general-purpose-model",
        created_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        benchmark_sha256="a" * 64,
        prompt_sha256="b" * 64,
        records=[
            CaseRunRecord(
                case_id=case.case_id,
                status="completed",
                prediction=make_prediction(case.case_id),
            )
            for case in bundle.cases
        ],
    )


@pytest.fixture
def complete_empty_run(benchmark_bundle: BenchmarkBundle) -> SystemRun:
    return make_system_run(benchmark_bundle)
