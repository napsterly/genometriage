from __future__ import annotations

import pytest

from genometriage.baseline.runner import BaselineSystem
from genometriage.benchmark.loader import DEFAULT_CASES_PATH

from conftest import FakeProvider


def test_baseline_makes_exactly_one_call_per_case(benchmark_bundle, fake_provider) -> None:
    cases = benchmark_bundle.cases[:3]
    run = BaselineSystem(fake_provider).run(cases, cases_path=DEFAULT_CASES_PATH)
    assert len(fake_provider.prompts) == 3
    assert all(record.status == "completed" for record in run.records)
    assert all("ground_truth" not in prompt for prompt in fake_provider.prompts)
    assert all("For research/expert review" in prompt for prompt in fake_provider.prompts)


def test_malformed_model_output_becomes_case_error(benchmark_bundle) -> None:
    provider = FakeProvider(outputs=["not-json"])
    run = BaselineSystem(provider).run(
        benchmark_bundle.cases[:1], cases_path=DEFAULT_CASES_PATH
    )
    assert len(provider.prompts) == 1
    assert run.records[0].status == "error"
    assert run.records[0].error_type == "ValueError"
    assert "malformed ranking JSON" in run.records[0].error_message


def test_negative_request_interval_is_rejected(fake_provider) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        BaselineSystem(fake_provider, min_request_interval_seconds=-0.01)


def test_checkpoint_resume_skips_completed_cases(benchmark_bundle) -> None:
    first_provider = FakeProvider()
    first = BaselineSystem(first_provider).run(
        benchmark_bundle.cases[:1],
        cases_path=DEFAULT_CASES_PATH,
        fail_fast=True,
    )
    resumed_provider = FakeProvider()
    checkpoints = []
    resumed = BaselineSystem(resumed_provider).run(
        benchmark_bundle.cases[:2],
        cases_path=DEFAULT_CASES_PATH,
        fail_fast=True,
        initial_records=first.records,
        created_at_utc=first.created_at_utc,
        checkpoint_callback=checkpoints.append,
    )

    assert len(resumed_provider.prompts) == 1
    assert resumed.run_status == "completed"
    assert [record.case_id for record in resumed.records] == ["GT-001", "GT-002"]
    assert checkpoints[0].run_status == "in_progress"
    assert checkpoints[-1].run_status == "completed"
