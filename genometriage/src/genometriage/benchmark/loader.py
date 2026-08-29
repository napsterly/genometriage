"""Deterministic JSONL benchmark loading with answer separation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, List, Optional, Sequence, Type, TypeVar

from pydantic import BaseModel, ValidationError

from genometriage.models.schema import BenchmarkCase, BenchmarkGroundTruth


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES_PATH = PROJECT_ROOT / "data" / "cases" / "benchmark_v1.jsonl"
DEFAULT_GROUND_TRUTH_PATH = (
    PROJECT_ROOT / "data" / "ground_truth" / "benchmark_v1_ground_truth.jsonl"
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class BenchmarkFormatError(ValueError):
    """A benchmark fixture is unreadable, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class BenchmarkBundle:
    cases: Sequence[BenchmarkCase]
    ground_truth: Sequence[BenchmarkGroundTruth]
    sha256: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_sha256(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read_jsonl(path: Path, model: Type[ModelT]) -> List[ModelT]:
    if not path.is_file():
        raise BenchmarkFormatError(f"benchmark fixture not found: {path}")

    records: List[ModelT] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BenchmarkFormatError(
                    f"{path}:{line_number}: invalid JSON: {exc.msg}"
                ) from exc
            try:
                records.append(model.parse_obj(payload))
            except ValidationError as exc:
                raise BenchmarkFormatError(
                    f"{path}:{line_number}: schema validation failed: {exc}"
                ) from exc
    if not records:
        raise BenchmarkFormatError(f"benchmark fixture is empty: {path}")
    return records


def load_cases(path: Path = DEFAULT_CASES_PATH) -> List[BenchmarkCase]:
    """Load only model-visible cases; this function never reads answer files."""

    return _read_jsonl(Path(path), BenchmarkCase)


def load_ground_truth(
    path: Path = DEFAULT_GROUND_TRUTH_PATH,
) -> List[BenchmarkGroundTruth]:
    """Load evaluator-only labels."""

    return _read_jsonl(Path(path), BenchmarkGroundTruth)


def load_benchmark(
    cases_path: Path = DEFAULT_CASES_PATH,
    ground_truth_path: Path = DEFAULT_GROUND_TRUTH_PATH,
) -> BenchmarkBundle:
    cases_path = Path(cases_path)
    ground_truth_path = Path(ground_truth_path)
    cases = load_cases(cases_path)
    ground_truth = load_ground_truth(ground_truth_path)
    validate_pairing(cases, ground_truth)
    return BenchmarkBundle(
        cases=cases,
        ground_truth=ground_truth,
        sha256=combined_sha256([cases_path, ground_truth_path]),
    )


def validate_pairing(
    cases: Sequence[BenchmarkCase],
    truths: Sequence[BenchmarkGroundTruth],
) -> None:
    case_by_id = {case.case_id: case for case in cases}
    truth_by_id = {truth.case_id: truth for truth in truths}
    if len(case_by_id) != len(cases):
        raise BenchmarkFormatError("duplicate case_id in model-visible cases")
    if len(truth_by_id) != len(truths):
        raise BenchmarkFormatError("duplicate case_id in ground truth")
    if set(case_by_id) != set(truth_by_id):
        missing_truth = sorted(set(case_by_id) - set(truth_by_id))
        missing_cases = sorted(set(truth_by_id) - set(case_by_id))
        raise BenchmarkFormatError(
            "case/ground-truth IDs differ; "
            f"missing truth={missing_truth}, missing cases={missing_cases}"
        )

    for case_id, case in case_by_id.items():
        truth = truth_by_id[case_id]
        candidate_ids = {variant.variant_id for variant in case.candidate_variants}
        evidence_ids = {
            evidence.source_id
            for variant in case.candidate_variants
            for evidence in variant.evidence
        }
        unknown_relevant = set(truth.relevant_variant_ids) - candidate_ids
        if unknown_relevant:
            raise BenchmarkFormatError(
                f"{case_id}: ground truth references unknown variants: "
                f"{sorted(unknown_relevant)}"
            )
        rationale_variant_ids = {
            variant_id
            for rationale in truth.rationale
            for variant_id in rationale.variant_ids
        }
        if rationale_variant_ids != set(truth.relevant_variant_ids):
            raise BenchmarkFormatError(
                f"{case_id}: rationale variant IDs must exactly cover relevant_variant_ids"
            )
        rationale_evidence_ids = {
            source_id
            for rationale in truth.rationale
            for source_id in rationale.evidence_source_ids
        }
        unknown_evidence = rationale_evidence_ids - evidence_ids
        if unknown_evidence:
            raise BenchmarkFormatError(
                f"{case_id}: ground truth references unknown evidence IDs: "
                f"{sorted(unknown_evidence)}"
            )


def visible_fixture_contains_answer_fields(path: Path = DEFAULT_CASES_PATH) -> bool:
    """Conservative lexical guard against accidentally leaking evaluator labels."""

    forbidden = {
        "relevant_variant_ids",
        "ground_truth",
        "difficulty",
        "challenge_tags",
        "rationale",
    }
    with Path(path).open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            payload = json.loads(line)
            if forbidden.intersection(payload):
                return True
    return False

