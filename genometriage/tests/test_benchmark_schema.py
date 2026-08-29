from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from genometriage import SAFETY_DISCLAIMER
from genometriage.benchmark.loader import validate_pairing
from genometriage.models.schema import BenchmarkCase


def test_all_benchmark_records_validate_and_pair(benchmark_bundle) -> None:
    assert len(benchmark_bundle.cases) == 12
    assert len(benchmark_bundle.ground_truth) == 12
    validate_pairing(benchmark_bundle.cases, benchmark_bundle.ground_truth)
    assert all(case.data_origin == "fully_synthetic" for case in benchmark_bundle.cases)
    assert all(
        case.safety_disclaimer == SAFETY_DISCLAIMER
        for case in benchmark_bundle.cases
    )


def test_case_schema_forbids_answer_fields(benchmark_bundle) -> None:
    payload = benchmark_bundle.cases[0].dict()
    payload["ground_truth"] = ["GT001-V1"]
    with pytest.raises(ValidationError):
        BenchmarkCase.parse_obj(payload)


def test_schema_round_trip_is_stable(benchmark_bundle) -> None:
    case = benchmark_bundle.cases[0]
    encoded = case.json(sort_keys=True)
    decoded = BenchmarkCase.parse_raw(encoded)
    assert json.loads(decoded.json()) == json.loads(case.json())

