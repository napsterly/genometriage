from __future__ import annotations

import json

from genometriage.baseline.prompt import load_prompt_template, render_prompt
from genometriage.benchmark.loader import (
    DEFAULT_CASES_PATH,
    visible_fixture_contains_answer_fields,
)


FORBIDDEN_KEYS = {
    "ground_truth",
    "relevant_variant_ids",
    "rationale",
    "difficulty",
    "challenge_tags",
}


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_keys(nested)


def test_model_visible_jsonl_has_no_answer_keys() -> None:
    assert not visible_fixture_contains_answer_fields()
    for line in DEFAULT_CASES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            assert FORBIDDEN_KEYS.isdisjoint(set(_all_keys(json.loads(line))))


def test_rendered_baseline_prompt_contains_no_sealed_labels(benchmark_bundle) -> None:
    case = benchmark_bundle.cases[0]
    truth = benchmark_bundle.ground_truth[0]
    rendered = render_prompt(case, load_prompt_template())
    assert "relevant_variant_ids" not in rendered
    assert "ground_truth" not in rendered
    assert truth.rationale[0].summary not in rendered

