from __future__ import annotations

import json

import pytest

from genometriage.baseline.runner import write_system_run
from genometriage.evaluation.evaluator import evaluate_run
from genometriage.evaluation.run import main
from genometriage.models.schema import EvaluationResult, TokenUsage


def test_evaluation_result_validates_and_serializes(
    benchmark_bundle, complete_empty_run
) -> None:
    result = evaluate_run(benchmark_bundle, complete_empty_run)
    reparsed = EvaluationResult.parse_raw(result.json())
    assert reparsed.aggregate.evaluated_case_count == 12
    assert reparsed.aggregate.failed_case_count == 0
    assert reparsed.aggregate.negative_control_count == 1
    assert reparsed.aggregate.total_estimated_cost_usd is None
    assert reparsed.model == "fake-general-purpose-model"
    assert len(reparsed.cases) == 12
    assert reparsed.cases[-3].case_id == "GT-010"
    assert reparsed.cases[-3].recall_at_k["5"] is None


def test_replay_cli_writes_machine_readable_schema(
    tmp_path, benchmark_bundle, complete_empty_run, capsys
) -> None:
    predictions = tmp_path / "predictions.json"
    output = tmp_path / "result.json"
    write_system_run(complete_empty_run, predictions)
    exit_code = main(
        [
            "--system",
            "baseline",
            "--predictions",
            str(predictions),
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    EvaluationResult.parse_obj(payload)
    terminal = capsys.readouterr().out
    assert "For research/expert review. Not a medical diagnosis." in terminal
    assert str(output) in terminal


def test_evaluator_rejects_in_progress_checkpoint(
    benchmark_bundle, complete_empty_run
) -> None:
    checkpoint = complete_empty_run.copy(update={"run_status": "in_progress"})
    with pytest.raises(ValueError, match="in-progress"):
        evaluate_run(benchmark_bundle, checkpoint)


def test_replay_can_price_stored_usage(
    benchmark_bundle, complete_empty_run, monkeypatch
) -> None:
    records = list(complete_empty_run.records)
    first_prediction = records[0].prediction.copy(
        update={
            "usage": TokenUsage(
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            )
        }
    )
    records[0] = records[0].copy(update={"prediction": first_prediction})
    priced_run = complete_empty_run.copy(update={"records": records})
    monkeypatch.setenv("GENOMETRIAGE_INPUT_COST_PER_MILLION", "0")
    monkeypatch.setenv("GENOMETRIAGE_OUTPUT_COST_PER_MILLION", "0")

    result = evaluate_run(benchmark_bundle, priced_run)
    assert result.cases[0].estimated_cost_usd == 0
    assert result.aggregate.total_estimated_cost_usd == 0
    assert result.aggregate.costed_case_count == 1
