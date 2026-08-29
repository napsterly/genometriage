from __future__ import annotations

from pathlib import Path

import pytest

from genometriage.normalization import (
    VariantNormalizationError,
    normalize_candidate,
    normalize_variant,
    parse_vcf,
)


def test_candidate_normalization_is_canonical_and_deterministic(benchmark_bundle) -> None:
    candidate = benchmark_bundle.cases[0].candidate_variants[0]
    first = normalize_candidate(candidate)
    second = normalize_candidate(candidate)
    assert first == second
    assert first.canonical_id == "GRCh38-synthetic:1:101001:G:A"
    assert first.gene == "GTA1"


def test_redundant_sequence_is_trimmed() -> None:
    variant = normalize_variant(
        variant_id="V1",
        genome_build="GRCh38-synthetic",
        chromosome="chr2",
        position=100,
        reference="AAC",
        alternate="AGC",
    )
    assert (variant.position, variant.reference, variant.alternate) == (101, "A", "G")
    assert variant.canonical_id == "GRCh38-synthetic:2:101:A:G"


@pytest.mark.parametrize("alternate", ["<DEL>", "A]2:20]", ".", ""])
def test_unsupported_alleles_are_rejected(alternate: str) -> None:
    with pytest.raises(VariantNormalizationError):
        normalize_variant(
            variant_id="bad",
            genome_build="GRCh38-synthetic",
            chromosome="1",
            position=1,
            reference="A",
            alternate=alternate,
        )


def test_vcf_subset_and_multiallelic_split_are_deterministic() -> None:
    fixture = Path(__file__).parents[1] / "data" / "vcf" / "benchmark_subset.vcf"
    first = parse_vcf(fixture, genome_build="GRCh38-synthetic")
    second = parse_vcf(fixture, genome_build="GRCh38-synthetic")
    assert first == second
    assert [variant.variant_id for variant in first] == [
        "GT001-V1",
        "GT002-V1",
        "SYN-MULTI:ALT1",
        "SYN-MULTI:ALT2",
    ]


def test_malformed_vcf_reports_line(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.vcf"
    malformed.write_text(
        "##fileformat=VCFv4.3\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n1\tnope\t.\tA\tG\t.\tPASS\t.\n",
        encoding="utf-8",
    )
    with pytest.raises(VariantNormalizationError, match=r":3: POS"):
        parse_vcf(malformed, genome_build="GRCh38-synthetic")
