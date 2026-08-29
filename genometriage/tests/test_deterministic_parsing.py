from __future__ import annotations

import pytest
from pydantic import ValidationError

from genometriage.models.schema import BenchmarkCase, CandidateVariant


def test_variant_normalization_is_deterministic() -> None:
    payload = {
        "variant_id": "V1",
        "genome_build": "GRCh38-synthetic",
        "chromosome": " chrX ",
        "position": 42,
        "reference": " a ",
        "alternate": " g ",
        "gene": " gene-z ",
        "consequence": "missense",
        "zygosity": "hemizygous",
        "evidence": [],
    }
    first = CandidateVariant.parse_obj(payload)
    second = CandidateVariant.parse_obj(payload)
    assert first.dict() == second.dict()
    assert first.chromosome == "X"
    assert first.reference == "A"
    assert first.alternate == "G"
    assert first.gene == "GENE-Z"
    assert first.canonical_id == "GRCh38-synthetic:X:42:A:G"


def test_duplicate_normalized_coordinates_are_rejected(benchmark_bundle) -> None:
    payload = benchmark_bundle.cases[0].dict()
    duplicate = payload["candidate_variants"][0].copy()
    duplicate["variant_id"] = "ANOTHER-ID"
    duplicate["chromosome"] = "chr1"
    payload["candidate_variants"].append(duplicate)
    with pytest.raises(ValidationError, match="coordinates must be unique"):
        BenchmarkCase.parse_obj(payload)

