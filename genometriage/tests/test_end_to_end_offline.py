from genometriage.baseline.runner import BaselineSystem
from genometriage.benchmark.loader import DEFAULT_CASES_PATH
from genometriage.evaluation.evaluator import evaluate_run
from genometriage.models.schema import EvaluationResult


def test_fake_provider_exercises_full_phase_one_path(
    benchmark_bundle, fake_provider
) -> None:
    raw_run = BaselineSystem(fake_provider).run(
        benchmark_bundle.cases,
        cases_path=DEFAULT_CASES_PATH,
        fail_fast=True,
    )
    result = evaluate_run(benchmark_bundle, raw_run)
    assert len(fake_provider.prompts) == 12
    assert result.aggregate.evaluated_case_count == 12
    assert result.aggregate.failed_case_count == 0
    EvaluationResult.parse_raw(result.json())

