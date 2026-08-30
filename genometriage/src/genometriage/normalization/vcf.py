"""A deliberately small, deterministic VCF parser for benchmark-sized inputs.

This module supports literal DNA alleles (A/C/G/T/N), splits multiallelic
records, removes redundant shared allele sequence, and never calls an LLM.
Reference-backed repeat left-alignment is outside the Phase 2 subset.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from genometriage.models.phase2 import CanonicalVariant
from genometriage.models.schema import CandidateVariant


_ALLELE = re.compile(r"^[ACGTN]+$")


class VariantNormalizationError(ValueError):
    """A variant cannot be represented by the supported deterministic subset."""


def normalize_chromosome(value: object) -> str:
    chromosome = str(value).strip()
    if chromosome.lower().startswith("chr"):
        chromosome = chromosome[3:]
    chromosome = chromosome.upper()
    if not chromosome or any(character.isspace() for character in chromosome):
        raise VariantNormalizationError("chromosome must be non-empty and contain no whitespace")
    return chromosome


def normalize_alleles(position: int, reference: str, alternate: str) -> Tuple[int, str, str]:
    """Return a minimal literal representation without reference-backed alignment."""

    if position < 1:
        raise VariantNormalizationError("position must be a positive integer")
    ref = str(reference).strip().upper()
    alt = str(alternate).strip().upper()
    if not _ALLELE.fullmatch(ref) or not _ALLELE.fullmatch(alt):
        raise VariantNormalizationError(
            "only non-empty literal A/C/G/T/N alleles are supported; symbolic and breakend alleles are rejected"
        )
    if ref == alt:
        raise VariantNormalizationError("reference and alternate alleles must differ")

    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref = ref[:-1]
        alt = alt[:-1]
    while len(ref) > 1 and len(alt) > 1 and ref[0] == alt[0]:
        ref = ref[1:]
        alt = alt[1:]
        position += 1
    return position, ref, alt


def normalize_variant(
    *,
    variant_id: str,
    genome_build: str,
    chromosome: object,
    position: int,
    reference: str,
    alternate: str,
    gene: Optional[str] = None,
    consequence: Optional[str] = None,
) -> CanonicalVariant:
    normalized_chromosome = normalize_chromosome(chromosome)
    normalized_position, normalized_ref, normalized_alt = normalize_alleles(
        position, reference, alternate
    )
    normalized_build = str(genome_build).strip()
    if not normalized_build:
        raise VariantNormalizationError("genome_build must be non-empty")
    normalized_gene = str(gene).strip().upper() if gene is not None else None
    normalized_gene = normalized_gene or None
    canonical_id = (
        f"{normalized_build}:{normalized_chromosome}:{normalized_position}:"
        f"{normalized_ref}:{normalized_alt}"
    )
    return CanonicalVariant(
        variant_id=str(variant_id).strip(),
        genome_build=normalized_build,
        chromosome=normalized_chromosome,
        position=normalized_position,
        reference=normalized_ref,
        alternate=normalized_alt,
        canonical_id=canonical_id,
        gene=normalized_gene,
        consequence=consequence,
    )


def normalize_candidate(candidate: CandidateVariant) -> CanonicalVariant:
    return normalize_variant(
        variant_id=candidate.variant_id,
        genome_build=candidate.genome_build,
        chromosome=candidate.chromosome,
        position=candidate.position,
        reference=candidate.reference,
        alternate=candidate.alternate,
        gene=candidate.gene,
        consequence=candidate.consequence,
    )


def parse_vcf(
    path: Path,
    *,
    genome_build: str,
) -> List[CanonicalVariant]:
    """Parse the Phase 2 VCF subset, preserving record and ALT order."""

    source_path = Path(path)
    with source_path.open("r", encoding="utf-8") as handle:
        return _parse_vcf_lines(
            handle,
            genome_build=genome_build,
            source_label=str(source_path),
        )


def parse_vcf_text(
    content: str,
    *,
    genome_build: str,
    source_label: str = "uploaded VCF",
) -> List[CanonicalVariant]:
    """Parse the supported VCF subset from in-memory text without temporary files."""

    if not isinstance(content, str):
        raise VariantNormalizationError("VCF content must be text")
    return _parse_vcf_lines(
        content.splitlines(),
        genome_build=genome_build,
        source_label=source_label,
    )


def _parse_vcf_lines(
    lines: Iterable[str],
    *,
    genome_build: str,
    source_label: str,
) -> List[CanonicalVariant]:
    """Shared deterministic parser implementation for file and in-memory input."""

    variants: List[CanonicalVariant] = []
    saw_column_header = False
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        if not line:
            continue
        if line.startswith("##"):
            continue
        if line.startswith("#CHROM"):
            columns = line.split("\t")
            if columns[:8] != ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]:
                raise VariantNormalizationError(
                    f"{source_label}:{line_number}: expected the standard first eight VCF columns"
                )
            saw_column_header = True
            continue
        if line.startswith("#"):
            raise VariantNormalizationError(
                f"{source_label}:{line_number}: unrecognized VCF header line"
            )
        if not saw_column_header:
            raise VariantNormalizationError(
                f"{source_label}:{line_number}: data encountered before #CHROM header"
            )

        columns = line.split("\t")
        if len(columns) < 8:
            raise VariantNormalizationError(
                f"{source_label}:{line_number}: expected at least eight tab-separated columns"
            )
        chromosome, raw_position, record_id, reference, alt_field = columns[:5]
        try:
            position = int(raw_position)
        except ValueError as exc:
            raise VariantNormalizationError(
                f"{source_label}:{line_number}: POS must be an integer"
            ) from exc
        alternates = alt_field.split(",")
        if any(not allele or allele == "." for allele in alternates):
            raise VariantNormalizationError(f"{source_label}:{line_number}: ALT is missing")
        for alt_index, alternate in enumerate(alternates, start=1):
            base_id = record_id if record_id != "." else (
                f"{normalize_chromosome(chromosome)}-{position}-{reference.upper()}-{alternate.upper()}"
            )
            variant_id = (
                f"{base_id}:ALT{alt_index}" if len(alternates) > 1 else base_id
            )
            variants.append(
                normalize_variant(
                    variant_id=variant_id,
                    genome_build=genome_build,
                    chromosome=chromosome,
                    position=position,
                    reference=reference,
                    alternate=alternate,
                )
            )
    if not saw_column_header:
        raise VariantNormalizationError(f"{source_label}: missing #CHROM header")
    return variants
