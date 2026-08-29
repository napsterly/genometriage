from __future__ import annotations

import json

import pytest

from genometriage.benchmark.loader import BenchmarkFormatError, load_cases


def test_invalid_json_reports_file_and_line(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"case_id":\n', encoding="utf-8")
    with pytest.raises(BenchmarkFormatError, match=r"bad\.jsonl:1: invalid JSON"):
        load_cases(path)


def test_schema_error_is_wrapped_as_benchmark_error(tmp_path) -> None:
    path = tmp_path / "bad_schema.jsonl"
    path.write_text(
        json.dumps({"schema_version": "1.0", "case_id": "not-valid"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkFormatError, match="schema validation failed"):
        load_cases(path)


def test_empty_fixture_is_rejected(tmp_path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("\n# comment only\n", encoding="utf-8")
    with pytest.raises(BenchmarkFormatError, match="fixture is empty"):
        load_cases(path)

