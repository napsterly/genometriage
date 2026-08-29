"""Fetch once and deterministically rebuild benchmark_public_v1 from ClinVar.

The ``fetch`` command is the only mode that uses the network. ``rebuild`` consumes
the retained raw E-utilities responses and is fully offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from genometriage import SAFETY_DISCLAIMER
from genometriage.benchmark.loader import file_sha256, load_benchmark
from genometriage.evidence import EvidenceStore, build_case_evidence_snapshot


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = Path(__file__).resolve()
RAW_POOL = ROOT / "data" / "public" / "clinvar" / "benchmark_public_v1_query_pool.json"
SELECTED_RECORDS = (
    ROOT / "data" / "public" / "clinvar" / "benchmark_public_v1_selected_records.json"
)
SOURCE_MANIFEST = (
    ROOT / "data" / "public" / "clinvar" / "benchmark_public_v1_source_manifest.json"
)
CASES = ROOT / "data" / "cases" / "benchmark_public_v1.jsonl"
GROUND_TRUTH = (
    ROOT / "data" / "ground_truth" / "benchmark_public_v1_ground_truth.jsonl"
)
EVIDENCE = ROOT / "data" / "evidence" / "evidence_public_v1.jsonl"
EVIDENCE_MANIFEST = ROOT / "data" / "evidence" / "evidence_public_v1_manifest.json"
FREEZE_MANIFEST = ROOT / "data" / "manifests" / "benchmark_public_v1_freeze.json"

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CLINVAR_USE_URL = "https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/"
CLINVAR_REVIEW_URL = "https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/"
CLINVAR_DOWNLOAD_URL = "https://www.ncbi.nlm.nih.gov/clinvar/docs/downloads/"
GENES = ("APC", "BRCA1", "BRCA2", "CFTR", "LDLR", "MLH1", "MSH2", "MYH7", "PAH", "TP53")
CATEGORY_TERMS = {
    "relevant": '"clinsig pathogenic"[Properties]',
    "benign": '"clinsig benign"[Properties]',
    "ambiguous": (
        '("clinsig vus"[Properties] OR "clinsig has conflicts"[Properties])'
    ),
}
MIN_RELEVANT_REVIEW_RANK = 1
RETRIEVAL_DELAY_SECONDS = 0.4
MAX_ATTEMPTS = 4


class PublicBenchmarkError(ValueError):
    """The retained public snapshot is malformed or cannot satisfy the fixed design."""


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _atomic_jsonl(path: Path, records: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
            for record in records
        ),
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _request_json(url: str) -> Mapping[str, object]:
    headers = {"User-Agent": "GenomeTriage/0.3 research benchmark snapshot"}
    last_error: Optional[BaseException] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=45
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == MAX_ATTEMPTS:
                raise PublicBenchmarkError(f"NCBI request failed: HTTP {exc.code}: {url}") from exc
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else min(2 ** attempt, 16)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                break
            delay = min(2 ** attempt, 16)
        time.sleep(delay)
    raise PublicBenchmarkError(f"NCBI request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def _eutils_url(endpoint: str, params: Mapping[str, object]) -> str:
    return f"{EUTILS_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"


def fetch_query_pool() -> Mapping[str, object]:
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    queries: List[Mapping[str, object]] = []
    for gene in GENES:
        for category, category_term in CATEGORY_TERMS.items():
            term = f"{gene}[gene] AND single_gene[prop] AND {category_term}"
            search_url = _eutils_url(
                "esearch.fcgi",
                {"db": "clinvar", "term": term, "retmax": 60, "retmode": "json"},
            )
            search_response = _request_json(search_url)
            time.sleep(RETRIEVAL_DELAY_SECONDS)
            ids = sorted(
                search_response.get("esearchresult", {}).get("idlist", []),
                key=lambda value: int(value),
            )
            if not ids:
                raise PublicBenchmarkError(f"ClinVar query returned no records: {term}")
            summary_url = _eutils_url(
                "esummary.fcgi",
                {"db": "clinvar", "id": ",".join(ids), "retmode": "json"},
            )
            summary_response = _request_json(summary_url)
            time.sleep(RETRIEVAL_DELAY_SECONDS)
            queries.append(
                {
                    "gene": gene,
                    "category": category,
                    "term": term,
                    "search_url": search_url,
                    "summary_url": summary_url,
                    "esearch_response": search_response,
                    "esummary_response": summary_response,
                }
            )
            print(f"fetched {gene} {category}: {len(ids)} candidate records")
    payload = {
        "schema_version": "1.0",
        "snapshot_id": "clinvar_eutils_public_v1",
        "retrieved_at_utc": retrieved_at,
        "database": "ClinVar",
        "provider": "NCBI E-utilities",
        "queries": queries,
    }
    _atomic_json(RAW_POOL, payload)
    return payload


def _records_for_query(query: Mapping[str, object]) -> List[Mapping[str, object]]:
    result = query["esummary_response"]["result"]
    records = []
    for uid in result.get("uids", []):
        record = result.get(str(uid))
        if isinstance(record, dict):
            records.append(record)
    return records


def _classification(record: Mapping[str, object]) -> Mapping[str, object]:
    value = record.get("germline_classification") or {}
    return value if isinstance(value, dict) else {}


def _traits(record: Mapping[str, object]) -> List[str]:
    result = []
    for trait in _classification(record).get("trait_set", []) or []:
        name = str(trait.get("trait_name", "")).strip()
        if name:
            result.append(name)
    return sorted(set(result), key=str.casefold)


def _review_rank(review_status: str) -> int:
    normalized = review_status.strip().casefold()
    if normalized == "practice guideline":
        return 4
    if normalized == "reviewed by expert panel":
        return 3
    if normalized == "criteria provided, multiple submitters, no conflicts":
        return 2
    if "criteria provided" in normalized:
        return 1
    return 0


def _category_matches(record: Mapping[str, object], category: str) -> bool:
    description = str(_classification(record).get("description", "")).casefold()
    if "conflicting" in description:
        kind = "ambiguous"
    elif "uncertain" in description:
        kind = "ambiguous"
    elif "benign" in description and "pathogenic" not in description:
        kind = "benign"
    elif "pathogenic" in description:
        kind = "relevant"
    else:
        return False
    return kind == category


def _variant_fields(record: Mapping[str, object], gene: str) -> Optional[Mapping[str, object]]:
    genes = {str(item.get("symbol", "")).upper() for item in record.get("genes", []) or []}
    if gene not in genes:
        return None
    variation_sets = record.get("variation_set", []) or []
    if len(variation_sets) != 1:
        return None
    variation = variation_sets[0]
    spdi = str(variation.get("canonical_spdi", ""))
    parts = spdi.split(":")
    if len(parts) != 4:
        return None
    _, position_zero, reference, alternate = parts
    if (
        not position_zero.isdigit()
        or len(reference) != 1
        or len(alternate) != 1
        or reference not in "ACGT"
        or alternate not in "ACGT"
    ):
        return None
    locations = [
        item
        for item in variation.get("variation_loc", []) or []
        if item.get("assembly_name") == "GRCh38" and item.get("status") == "current"
    ]
    if not locations:
        return None
    chromosome = str(locations[0].get("chr", "")).upper().removeprefix("CHR")
    if chromosome not in {*(str(value) for value in range(1, 23)), "X", "Y"}:
        return None
    position = int(position_zero) + 1
    if str(locations[0].get("start", "")) and int(locations[0]["start"]) != position:
        return None
    return {
        "chromosome": chromosome,
        "position": position,
        "reference": reference,
        "alternate": alternate,
        "canonical_spdi": spdi,
    }


def _eligible(
    record: Mapping[str, object], gene: str, category: str
) -> Optional[Mapping[str, object]]:
    if not _category_matches(record, category):
        return None
    fields = _variant_fields(record, gene)
    if fields is None or not _traits(record):
        return None
    review = str(_classification(record).get("review_status", ""))
    if category == "relevant" and _review_rank(review) < MIN_RELEVANT_REVIEW_RANK:
        return None
    return fields


def _query_map(pool: Mapping[str, object]) -> Dict[Tuple[str, str], Mapping[str, object]]:
    result = {}
    for query in pool.get("queries", []):
        key = (str(query.get("gene")), str(query.get("category")))
        if key in result:
            raise PublicBenchmarkError(f"duplicate retained query: {key}")
        result[key] = query
    return result


def _select_records(pool: Mapping[str, object]) -> List[Mapping[str, object]]:
    queries = _query_map(pool)
    selected: List[Mapping[str, object]] = []
    used_uids = set()
    for case_number, gene in enumerate(GENES, start=1):
        relevant_options = []
        for record in _records_for_query(queries[(gene, "relevant")]):
            fields = _eligible(record, gene, "relevant")
            if fields and str(record["uid"]) not in used_uids:
                relevant_options.append((record, fields))
        if not relevant_options:
            raise PublicBenchmarkError(
                f"no eligible criteria-provided relevant record for {gene}"
            )
        relevant, relevant_fields = sorted(
            relevant_options,
            key=lambda item: (
                -_review_rank(str(_classification(item[0]).get("review_status", ""))),
                int(item[0]["uid"]),
            ),
        )[0]
        target_traits = set(_traits(relevant))
        used_uids.add(str(relevant["uid"]))

        chosen = [("relevant", relevant, relevant_fields)]
        for category in ("benign", "ambiguous"):
            options = []
            for record in _records_for_query(queries[(gene, category)]):
                fields = _eligible(record, gene, category)
                if fields and str(record["uid"]) not in used_uids:
                    overlap = len(target_traits & set(_traits(record)))
                    options.append((record, fields, overlap))
            if not options:
                raise PublicBenchmarkError(f"no eligible {category} decoy for {gene}")
            record, fields, _ = sorted(
                options,
                key=lambda item: (
                    -item[2],
                    -_review_rank(str(_classification(item[0]).get("review_status", ""))),
                    int(item[0]["uid"]),
                ),
            )[0]
            used_uids.add(str(record["uid"]))
            chosen.append((category, record, fields))

        for candidate_number, (role, record, fields) in enumerate(chosen, start=1):
            selected.append(
                {
                    "case_id": f"GP-{case_number:03d}",
                    "variant_id": f"GP{case_number:03d}-V{candidate_number}",
                    "gene": gene,
                    "role": role,
                    "target_traits": sorted(target_traits, key=str.casefold),
                    "variant_fields": fields,
                    "clinvar_record": record,
                }
            )
    return selected


def _evidence_for(selected: Mapping[str, object]) -> List[Mapping[str, object]]:
    record = selected["clinvar_record"]
    classification = _classification(record)
    description = str(classification.get("description", "")).strip()
    review = str(classification.get("review_status", "")).strip()
    accession = str(record.get("accession_version") or record.get("accession"))
    role = str(selected["role"])
    direction = {"relevant": "supports", "benign": "against", "ambiguous": "uncertain"}[role]
    review_strength = "strong" if _review_rank(review) >= 2 else "moderate" if _review_rank(review) == 1 else "weak"
    target_traits = set(selected["target_traits"])
    record_traits = set(_traits(record))
    overlap = sorted(target_traits & record_traits, key=str.casefold)
    if overlap:
        context_direction = "supports"
        context_strength = "moderate"
        context_statement = (
            "The ClinVar aggregate record includes the case target trait(s): "
            + "; ".join(overlap)
            + "."
        )
    else:
        context_direction = "against"
        context_strength = "strong"
        context_statement = (
            "The ClinVar aggregate record traits do not include the case target trait; "
            "record traits are: "
            + "; ".join(sorted(record_traits, key=str.casefold))
            + "."
        )
    return [
        {
            "source_id": f"CLINVAR:{accession}:germline-classification",
            "source_type": "clinvar_public_record",
            "direction": direction,
            "statement": f"ClinVar aggregate germline classification: {description}.",
            "strength": "moderate",
            "dimension": "provenance",
        },
        {
            "source_id": f"CLINVAR:{accession}:review-status",
            "source_type": "clinvar_public_record",
            "direction": direction,
            "statement": f"ClinVar aggregate germline review status: {review or 'not provided'}.",
            "strength": review_strength,
            "dimension": "provenance",
        },
        {
            "source_id": f"CLINVAR:{accession}:trait-context",
            "source_type": "clinvar_public_record",
            "direction": context_direction,
            "statement": context_statement,
            "strength": context_strength,
            "dimension": "phenotype_context",
        },
    ]


def _build_cases_and_truth(
    selected: Sequence[Mapping[str, object]],
) -> Tuple[List[Mapping[str, object]], List[Mapping[str, object]]]:
    by_case: Dict[str, List[Mapping[str, object]]] = {}
    for item in selected:
        by_case.setdefault(str(item["case_id"]), []).append(item)
    cases = []
    truths = []
    for case_id in sorted(by_case):
        group = sorted(by_case[case_id], key=lambda item: str(item["variant_id"]))
        if [item["role"] for item in group] != ["relevant", "benign", "ambiguous"]:
            raise PublicBenchmarkError(f"unexpected candidate roles for {case_id}")
        target_traits = list(group[0]["target_traits"])
        candidates = []
        for item in group:
            record = item["clinvar_record"]
            fields = item["variant_fields"]
            consequences = record.get("molecular_consequence_list", []) or []
            candidates.append(
                {
                    "variant_id": item["variant_id"],
                    "genome_build": "GRCh38",
                    "chromosome": fields["chromosome"],
                    "position": fields["position"],
                    "reference": fields["reference"],
                    "alternate": fields["alternate"],
                    "gene": item["gene"],
                    "consequence": ", ".join(consequences) or str(record.get("obj_type", "")) or None,
                    "zygosity": "unknown",
                    "observed_inheritance": "not represented in the public aggregate record",
                    "population_allele_frequency": None,
                    "evidence": _evidence_for(item),
                }
            )
        cases.append(
            {
                "schema_version": "1.0",
                "case_id": case_id,
                "data_origin": "appropriately_public",
                "safety_disclaimer": SAFETY_DISCLAIMER,
                "context": {
                    "summary": (
                        "Public ClinVar-record prioritization exercise for target trait(s): "
                        + "; ".join(target_traits)
                        + ". Candidate evidence is a pinned aggregate-record snapshot."
                    ),
                    "phenotype_terms": target_traits,
                    "inheritance_hypothesis": None,
                    "family_observations": [],
                },
                "candidate_variants": candidates,
            }
        )
        relevant = group[0]
        relevant_evidence = [item["source_id"] for item in _evidence_for(relevant)]
        classification = _classification(relevant["clinvar_record"])
        truths.append(
            {
                "schema_version": "1.0",
                "case_id": case_id,
                "relevant_variant_ids": [relevant["variant_id"]],
                "rationale": [
                    {
                        "variant_ids": [relevant["variant_id"]],
                        "summary": (
                            "Ground truth was assigned before model evaluation: the record has "
                            f"ClinVar germline classification {classification.get('description')} "
                            f"with review status {classification.get('review_status')} and includes "
                            "the target trait."
                        ),
                        "evidence_source_ids": relevant_evidence,
                    }
                ],
                "difficulty": "moderate",
                "challenge_tags": [
                    "appropriately_public",
                    "clinvar_aggregate_record",
                    "ambiguous_decoy",
                    "independent_label_rule",
                ],
            }
        )
    return cases, truths


def rebuild_from_snapshot() -> None:
    try:
        pool = json.loads(RAW_POOL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicBenchmarkError(f"invalid retained query pool: {exc}") from exc
    selected = _select_records(pool)
    cases, truths = _build_cases_and_truth(selected)
    _atomic_json(SELECTED_RECORDS, {"records": selected})
    _atomic_jsonl(CASES, cases)
    _atomic_jsonl(GROUND_TRUTH, truths)

    selected_sha = file_sha256(SELECTED_RECORDS)
    retrieved_at = str(pool["retrieved_at_utc"])
    source_manifest = {
        "schema_version": "1.0",
        "snapshot_id": "clinvar_eutils_public_v1",
        "source": "NCBI ClinVar via E-utilities esearch and esummary",
        "snapshot_date": retrieved_at[:10],
        "retrieved_at_utc": retrieved_at,
        "release_or_version": (
            "Pinned E-utilities subset; every selected record retains its exact VCV "
            "accession_version from the captured response."
        ),
        "record_count": len(selected),
        "selected_record_versions": sorted(
            str(item["clinvar_record"].get("accession_version")) for item in selected
        ),
        "selected_variation_ids": sorted(
            str(item["clinvar_record"]["uid"]) for item in selected
        ),
        "retrieval_method": (
            "Fixed gene/category ESearch queries, at most 60 IDs per query, then JSON "
            "ESummary. Bounded to four attempts with backoff and no model involvement."
        ),
        "selection_method": (
            "For each fixed gene, deterministic filters require a current GRCh38 SNV, "
            "one gene, traits, and at least criteria-provided review for the relevant record. "
            "The relevant record is the lowest Variation ID among the highest-review "
            "pathogenic candidates; benign and ambiguous decoys prefer "
            "trait overlap, then review rank, then the lowest Variation ID."
        ),
        "ground_truth_rule": (
            "The sole relevant record per case is selected independently as Pathogenic or "
            "Likely pathogenic with at least criteria-provided aggregate review; the highest "
            "available review tier is preferred, and its ClinVar trait defines the case target."
        ),
        "usage_and_safety": (
            "ClinVar requests attribution and warns that data are not for direct diagnostic "
            "or medical decision-making without genetics-professional review. This repository "
            "contains public aggregate records only, not identifiable patient data."
        ),
        "source_urls": [CLINVAR_USE_URL, CLINVAR_REVIEW_URL, CLINVAR_DOWNLOAD_URL],
        "artifacts": {
            RAW_POOL.relative_to(ROOT).as_posix(): file_sha256(RAW_POOL),
            SELECTED_RECORDS.relative_to(ROOT).as_posix(): selected_sha,
            SCRIPT_PATH.relative_to(ROOT).as_posix(): file_sha256(SCRIPT_PATH),
        },
        "external_live_dependency_during_evaluation": False,
        "safety_disclaimer": SAFETY_DISCLAIMER,
    }
    _atomic_json(SOURCE_MANIFEST, source_manifest)

    build_case_evidence_snapshot(
        cases_path=CASES,
        evidence_path=EVIDENCE,
        manifest_path=EVIDENCE_MANIFEST,
        snapshot_version="evidence_public_v1",
        snapshot_date=retrieved_at[:10],
        source_fixture_label="data/cases/benchmark_public_v1.jsonl",
        source_name="NCBI ClinVar E-utilities pinned public subset",
        extraction_method="deterministic_clinvar_esummary_transform_v1",
        provenance_model="deterministic_clinvar_esummary_transform_v1",
        compatibility_note=(
            "Evidence statements are deterministic transformations of retained public ClinVar "
            "aggregate-record metadata; no private or patient-identifiable data are included."
        ),
        notes=[
            "The raw query pool and exact selected VCV accession versions are retained locally.",
            "Ground truth is stored separately and is not read by system runners.",
            "No network access is used during evidence retrieval or benchmark evaluation.",
            "ClinVar classifications are submitted/aggregated data and require expert review.",
        ],
        source_metadata={
            "source_url": CLINVAR_USE_URL,
            "source_release": "pinned VCV accession-version subset " + retrieved_at[:10],
            "license_or_terms_url": CLINVAR_USE_URL,
            "retrieved_at_utc": retrieved_at,
            "source_record_sha256": selected_sha,
        },
    )

    artifact_paths = [
        RAW_POOL,
        SELECTED_RECORDS,
        SOURCE_MANIFEST,
        CASES,
        GROUND_TRUTH,
        EVIDENCE,
        EVIDENCE_MANIFEST,
        SCRIPT_PATH,
    ]
    freeze = {
        "freeze_id": "benchmark_public_v1",
        "frozen_at_utc": retrieved_at,
        "hash_algorithm": "sha256",
        "case_count": len(cases),
        "candidate_count": len(selected),
        "source_snapshot_id": "clinvar_eutils_public_v1",
        "benchmark_created_before_model_predictions": True,
        "external_live_dependency_during_evaluation": False,
        "artifacts": {
            path.relative_to(ROOT).as_posix(): file_sha256(path)
            for path in artifact_paths
        },
        "safety_disclaimer": SAFETY_DISCLAIMER,
    }
    _atomic_json(FREEZE_MANIFEST, freeze)

    bundle = load_benchmark(CASES, GROUND_TRUTH)
    store = EvidenceStore.load(
        evidence_path=EVIDENCE,
        manifest_path=EVIDENCE_MANIFEST,
        cases_path=CASES,
    )
    if len(bundle.cases) != len(GENES) or len(store.records) != len(selected) * 3:
        raise PublicBenchmarkError("rebuilt public benchmark count validation failed")
    print(
        f"rebuilt benchmark_public_v1: {len(bundle.cases)} cases, "
        f"{len(selected)} candidates, {len(store.records)} evidence records"
    )


def validate_freeze() -> None:
    try:
        freeze = json.loads(FREEZE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicBenchmarkError(f"invalid public freeze manifest: {exc}") from exc
    for relative, expected in freeze.get("artifacts", {}).items():
        path = ROOT / relative
        actual = file_sha256(path)
        if actual != expected:
            raise PublicBenchmarkError(f"public freeze hash mismatch: {relative}")
    load_benchmark(CASES, GROUND_TRUTH)
    EvidenceStore.load(
        evidence_path=EVIDENCE,
        manifest_path=EVIDENCE_MANIFEST,
        cases_path=CASES,
    )
    print(f"public freeze validation: pass ({len(freeze['artifacts'])} artifacts)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["fetch", "rebuild", "validate"])
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "fetch":
        fetch_query_pool()
        rebuild_from_snapshot()
    elif args.mode == "rebuild":
        rebuild_from_snapshot()
    else:
        validate_freeze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
