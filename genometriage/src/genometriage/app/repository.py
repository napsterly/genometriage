"""Read-only product views over frozen GenomeTriage artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

from pydantic import ValidationError

from genometriage import SAFETY_DISCLAIMER
from genometriage.baseline.runner import load_system_run
from genometriage.benchmark.loader import load_cases
from genometriage.evidence import EvidenceStore
from genometriage.models.phase2 import CanonicalVariant, EvidenceRecord
from genometriage.models.schema import BenchmarkCase, EvaluationResult, Prediction, SystemRun
from genometriage.normalization import (
    VariantNormalizationError,
    normalize_candidate,
    parse_vcf_text,
)


ROOT = Path(__file__).resolve().parents[3]
REPLAY_LABEL = "Recorded benchmark execution / deterministic replay"
MAX_INSPECTED_VARIANTS = 50


class DemoRepositoryError(ValueError):
    """The judge app cannot safely serve a requested artifact or input."""


@dataclass(frozen=True)
class TrackConfig:
    track_id: str
    label: str
    description: str
    cases_path: Path
    evidence_path: Path
    evidence_manifest_path: Path
    v1_predictions_path: Path
    v1_results_path: Path
    v3_predictions_path: Optional[Path] = None
    v3_results_path: Optional[Path] = None
    baseline_predictions_path: Optional[Path] = None


TRACKS: Mapping[str, TrackConfig] = {
    "benchmark_v1": TrackConfig(
        track_id="benchmark_v1",
        label="Frozen synthetic benchmark",
        description="The 12-case regression benchmark used for the V0→V1 comparison.",
        cases_path=ROOT / "data" / "cases" / "benchmark_v1.jsonl",
        evidence_path=ROOT / "data" / "evidence" / "evidence_v1.jsonl",
        evidence_manifest_path=ROOT / "data" / "evidence" / "evidence_v1_manifest.json",
        v1_predictions_path=ROOT / "predictions" / "evidence-grounded-v1.json",
        v1_results_path=ROOT / "results" / "evidence-grounded-v1.json",
        v3_predictions_path=ROOT / "predictions" / "conflict-arbitrated-v3.json",
        v3_results_path=ROOT / "results" / "conflict-arbitrated-v3.json",
        baseline_predictions_path=ROOT / "predictions" / "baseline-gemini.json",
    ),
    "benchmark_conflict_v1": TrackConfig(
        track_id="benchmark_conflict_v1",
        label="Held-out conflict benchmark",
        description="Thirteen unseen synthetic cases designed before the frozen V3 policy.",
        cases_path=ROOT / "data" / "cases" / "benchmark_conflict_v1.jsonl",
        evidence_path=ROOT / "data" / "evidence" / "evidence_conflict_v1.jsonl",
        evidence_manifest_path=ROOT
        / "data"
        / "evidence"
        / "evidence_conflict_v1_manifest.json",
        v1_predictions_path=ROOT
        / "predictions"
        / "benchmark_conflict_v1-evidence-grounded-v1.json",
        v1_results_path=ROOT
        / "results"
        / "benchmark_conflict_v1-evidence-grounded-v1.json",
        v3_predictions_path=ROOT
        / "predictions"
        / "benchmark_conflict_v1-conflict-arbitrated-v3.json",
        v3_results_path=ROOT
        / "results"
        / "benchmark_conflict_v1-conflict-arbitrated-v3.json",
    ),
    "benchmark_public_v1": TrackConfig(
        track_id="benchmark_public_v1",
        label="Frozen public ClinVar benchmark",
        description="Ten cases built from pinned, versioned public ClinVar aggregate records.",
        cases_path=ROOT / "data" / "cases" / "benchmark_public_v1.jsonl",
        evidence_path=ROOT / "data" / "evidence" / "evidence_public_v1.jsonl",
        evidence_manifest_path=ROOT
        / "data"
        / "evidence"
        / "evidence_public_v1_manifest.json",
        v1_predictions_path=ROOT
        / "predictions"
        / "benchmark_public_v1-evidence-grounded-v1.json",
        v1_results_path=ROOT
        / "results"
        / "benchmark_public_v1-evidence-grounded-v1.json",
        v3_predictions_path=ROOT
        / "predictions"
        / "benchmark_public_v1-conflict-arbitrated-v3.json",
        v3_results_path=ROOT
        / "results"
        / "benchmark_public_v1-conflict-arbitrated-v3.json",
    ),
}


def _records_by_case(run: SystemRun) -> Dict[str, Prediction]:
    return {
        record.case_id: record.prediction
        for record in run.records
        if record.status == "completed" and record.prediction is not None
    }


def _evidence_payload(record: EvidenceRecord, *, cited: bool) -> Dict[str, object]:
    provenance = record.provenance
    return {
        "evidence_id": record.evidence_id,
        "source": record.source,
        "original_source_record_id": record.original_source_record_id,
        "snapshot_version": record.snapshot_version,
        "snapshot_date": record.snapshot_date,
        "direction": record.content.direction,
        "statement": record.content.statement,
        "strength": record.content.strength,
        "category": record.content.dimension,
        "cited_by_shortlist": cited,
        "provenance": {
            "data_origin": provenance.data_origin,
            "source_fixture": provenance.source_fixture,
            "source_fixture_sha256": provenance.source_fixture_sha256,
            "source_case_id": provenance.source_case_id,
            "source_variant_id": provenance.source_variant_id,
            "extraction_method": provenance.extraction_method,
            "source_url": provenance.source_url,
            "source_release": provenance.source_release,
            "license_or_terms_url": provenance.license_or_terms_url,
            "retrieved_at_utc": provenance.retrieved_at_utc,
            "source_record_sha256": provenance.source_record_sha256,
        },
    }


def _normalized_payload(variant: CanonicalVariant) -> Dict[str, object]:
    return variant.dict()


def _recorded_provider(model: str, execution_config: Mapping[str, object]) -> Optional[str]:
    configured = execution_config.get("provider")
    if configured:
        return str(configured)
    return "gemini" if "gemini" in model.lower() else None


class DemoRepository:
    """Load frozen artifacts once and expose ground-truth-free product payloads."""

    def __init__(self, tracks: Mapping[str, TrackConfig] = TRACKS) -> None:
        self.tracks = dict(tracks)
        self._cases: Dict[str, Dict[str, BenchmarkCase]] = {}
        self._stores: Dict[str, EvidenceStore] = {}
        self._v1_runs: Dict[str, SystemRun] = {}
        self._v1_predictions: Dict[str, Dict[str, Prediction]] = {}
        self._v3_predictions: Dict[str, Dict[str, Prediction]] = {}
        self._baseline_predictions: Dict[str, Dict[str, Prediction]] = {}
        for track_id, config in self.tracks.items():
            cases = load_cases(config.cases_path)
            self._cases[track_id] = {case.case_id: case for case in cases}
            self._stores[track_id] = EvidenceStore.load(
                evidence_path=config.evidence_path,
                manifest_path=config.evidence_manifest_path,
                cases_path=config.cases_path,
            )
            v1_run = load_system_run(config.v1_predictions_path)
            self._v1_runs[track_id] = v1_run
            self._v1_predictions[track_id] = _records_by_case(v1_run)
            if config.v3_predictions_path:
                self._v3_predictions[track_id] = _records_by_case(
                    load_system_run(config.v3_predictions_path)
                )
            if config.baseline_predictions_path:
                self._baseline_predictions[track_id] = _records_by_case(
                    load_system_run(config.baseline_predictions_path)
                )

    def catalog(self) -> Dict[str, object]:
        tracks = []
        for track_id, config in self.tracks.items():
            cases = [
                {
                    "case_id": case.case_id,
                    "summary": case.context.summary,
                    "candidate_count": len(case.candidate_variants),
                    "data_origin": case.data_origin,
                    "baseline_comparison_available": case.case_id
                    in self._baseline_predictions.get(track_id, {}),
                }
                for case in self._cases[track_id].values()
            ]
            tracks.append(
                {
                    "track_id": track_id,
                    "label": config.label,
                    "description": config.description,
                    "cases": cases,
                }
            )
        return {
            "default_track": "benchmark_v1",
            "default_case": "GT-002",
            "default_system": "evidence-grounded-v1",
            "execution_mode": "recorded_replay",
            "replay_label": REPLAY_LABEL,
            "safety_disclaimer": SAFETY_DISCLAIMER,
            "tracks": tracks,
        }

    def case_payload(self, track_id: str, case_id: str) -> Dict[str, object]:
        if track_id not in self.tracks:
            raise DemoRepositoryError(f"unknown benchmark track: {track_id}")
        try:
            case = self._cases[track_id][case_id]
            prediction = self._v1_predictions[track_id][case_id]
        except KeyError as exc:
            raise DemoRepositoryError(f"unknown retained case: {case_id}") from exc

        store = self._stores[track_id]
        candidates_by_id = {candidate.variant_id: candidate for candidate in case.candidate_variants}
        normalized = {
            candidate.variant_id: normalize_candidate(candidate)
            for candidate in case.candidate_variants
        }
        cited_ids = {
            evidence_id
            for ranked in prediction.ranked_variants
            for evidence_id in ranked.evidence_source_ids
        }
        evidence_by_variant: Dict[str, List[Dict[str, object]]] = {}
        for variant_id, canonical in normalized.items():
            evidence_by_variant[variant_id] = [
                _evidence_payload(record, cited=record.evidence_id in cited_ids)
                for record in store.retrieve(canonical)
            ]

        shortlist = []
        for ranked in prediction.ranked_variants:
            candidate = candidates_by_id[ranked.variant_id]
            records = evidence_by_variant[ranked.variant_id]
            shortlist.append(
                {
                    "rank": ranked.rank,
                    "variant_id": ranked.variant_id,
                    "gene": candidate.gene,
                    "normalized": _normalized_payload(normalized[ranked.variant_id]),
                    "reason": ranked.reason,
                    "confidence": ranked.confidence,
                    "evidence_ids": ranked.evidence_source_ids,
                    "claims": [claim.dict() for claim in ranked.claims],
                    "supporting_evidence": [
                        record for record in records if record["direction"] == "supports"
                    ],
                    "counterevidence": [
                        record for record in records if record["direction"] == "against"
                    ],
                    "uncertainty_evidence": [
                        record for record in records if record["direction"] == "uncertain"
                    ],
                }
            )

        baseline = self._baseline_predictions.get(track_id, {}).get(case_id)
        comparison = self._comparison_payload(baseline, prediction)
        run = self._v1_runs[track_id]
        manifest = store.manifest
        return {
            "mode": "product",
            "execution_mode": "recorded_replay",
            "replay_label": REPLAY_LABEL,
            "safety_disclaimer": SAFETY_DISCLAIMER,
            "case": {
                "case_id": case.case_id,
                "data_origin": case.data_origin,
                "context": case.context.dict(),
                "candidate_count": len(case.candidate_variants),
                "candidates": [
                    {
                        "variant_id": candidate.variant_id,
                        "gene": candidate.gene,
                        "consequence": candidate.consequence,
                        "input_representation": (
                            f"{candidate.genome_build}:{candidate.chromosome}:"
                            f"{candidate.position}:{candidate.reference}:{candidate.alternate}"
                        ),
                        "normalized": _normalized_payload(normalized[candidate.variant_id]),
                        "retrieved_evidence_count": len(evidence_by_variant[candidate.variant_id]),
                    }
                    for candidate in case.candidate_variants
                ],
            },
            "normalization": [
                _normalized_payload(normalized[candidate.variant_id])
                for candidate in case.candidate_variants
            ],
            "retrieval": {
                "method": "exact normalized-allele match in a frozen local evidence store",
                "snapshot_version": manifest.snapshot_version,
                "snapshot_date": manifest.snapshot_date,
                "snapshot_sha256": manifest.evidence_file_sha256,
                "external_live_dependency": manifest.external_live_dependency,
                "evidence_by_variant": evidence_by_variant,
            },
            "system": {
                "name": "GenomeTriage V1",
                "system_version": prediction.system,
                "prompt_version": prediction.prompt_version,
                "prompt_sha256": run.prompt_sha256,
                "provider": _recorded_provider(run.model, run.execution_config),
                "model": prediction.model,
                "recorded_at_utc": run.created_at_utc.isoformat(),
                "model_call_count": (
                    prediction.model_call_count
                    if prediction.model_call_count is not None
                    else 1
                ),
                "model_call_count_source": (
                    "retained prediction field"
                    if prediction.model_call_count is not None
                    else "reconstructed from the frozen V1 one-call-per-completed-case contract"
                ),
                "runtime_seconds": prediction.runtime_seconds,
                "deterministic_runtime_seconds": prediction.deterministic_runtime_seconds,
                "external_model_runtime_seconds": prediction.external_model_runtime_seconds,
                "usage": prediction.usage.dict(),
                "estimated_cost_usd": prediction.estimated_cost_usd,
                "provider_retry_errors": prediction.provider_retry_errors,
            },
            "shortlist": shortlist,
            "uncertainty": {
                "escalated": prediction.escalated_uncertainty,
                "notes": prediction.notes,
            },
            "baseline_comparison": comparison,
            "human_review_checkpoint": (
                "A qualified reviewer must inspect the shortlist, evidence provenance, "
                "counterevidence, and uncertainty before any consequential interpretation."
            ),
        }

    @staticmethod
    def _comparison_payload(
        baseline: Optional[Prediction], v1: Prediction
    ) -> Optional[Dict[str, object]]:
        if baseline is None:
            return None
        baseline_ids = [item.variant_id for item in baseline.ranked_variants]
        v1_ids = [item.variant_id for item in v1.ranked_variants]
        return {
            "baseline_system": baseline.system,
            "baseline_model": baseline.model,
            "baseline_ranked_variants": [item.dict() for item in baseline.ranked_variants],
            "v1_ranked_variants": [item.dict() for item in v1.ranked_variants],
            "removed_by_v1": [variant_id for variant_id in baseline_ids if variant_id not in v1_ids],
            "added_by_v1": [variant_id for variant_id in v1_ids if variant_id not in baseline_ids],
            "baseline_review_burden": len(baseline_ids),
            "v1_review_burden": len(v1_ids),
            "review_burden_reduction": len(baseline_ids) - len(v1_ids),
        }

    def dashboard(self) -> Dict[str, object]:
        baseline = self._load_result(
            ROOT / "results" / "baseline-gemini-phase2-replay.json"
        )
        top3 = self._load_result(ROOT / "results" / "v0-top3-control.json")
        v1 = self._load_result(
            ROOT / "results" / "phase3" / "benchmark_v1-evidence-grounded-v1.json"
        )
        v2 = self._load_result(ROOT / "results" / "verified-v2.json")
        phase3 = json.loads(
            (ROOT / "results" / "phase3" / "comparison.json").read_text(encoding="utf-8")
        )
        v0_metrics = self._dashboard_metrics(baseline)
        v1_metrics = self._dashboard_metrics(v1)
        top3_metrics = self._dashboard_metrics(top3)
        v2_metrics = self._dashboard_metrics(v2)
        fp_reduction = self._relative_reduction(
            int(v0_metrics["false_positives"]), int(v1_metrics["false_positives"])
        )
        burden_reduction = self._relative_reduction(
            int(v0_metrics["review_burden"]), int(v1_metrics["review_burden"])
        )
        shortlist_delta = float(v1_metrics["shortlist_precision"]) - float(
            v0_metrics["shortlist_precision"]
        )
        return {
            "mode": "evaluation",
            "source": "retained machine-readable result artifacts",
            "safety_disclaimer": SAFETY_DISCLAIMER,
            "headline": {
                "false_positive_reduction_percent": fp_reduction,
                "review_burden_reduction_percent": burden_reduction,
                "recall_at_3_preserved": (
                    v0_metrics["recall_at_3"] == v1_metrics["recall_at_3"] == 1.0
                ),
                "shortlist_precision_absolute_change": shortlist_delta,
                "shortlist_precision_percentage_points": shortlist_delta * 100,
            },
            "systems": {
                "v0": v0_metrics,
                "v0_top3_control": top3_metrics,
                "v1": v1_metrics,
                "v2": v2_metrics,
            },
            "control": {
                "prediction_identical": self._runs_prediction_identical(
                    ROOT / "predictions" / "baseline-gemini.json",
                    ROOT / "predictions" / "v0-top3-control.json",
                ),
                "false_positive_reductions_explained_by_truncation": 0,
                "total_v0_to_v1_false_positive_reduction": int(
                    v0_metrics["false_positives"]
                )
                - int(v1_metrics["false_positives"]),
            },
            "generalization": phase3["tracks"],
            "generalization_gap": phase3["generalization_gap"],
            "pricing_note": (
                "Estimated API cost for retained benchmark runs: $0 under the "
                "configured Gemini free-tier pricing at test time; this is not a "
                "universal provider price."
            ),
        }

    def journey(self) -> Dict[str, object]:
        dashboard = self.dashboard()
        systems = dashboard["systems"]
        phase3_tracks = dashboard["generalization"]
        return {
            "safety_disclaimer": SAFETY_DISCLAIMER,
            "hot_take": "More agents did not make genomic triage more reliable. Better evidence structure did.",
            "technical_lesson": "The observed bottleneck was evidence calibration, not reasoning capacity.",
            "stages": [
                {
                    "stage": "V0",
                    "title": "Basic baseline",
                    "decision": "BASELINE",
                    "outcome": "Strong recall, but a noisy shortlist.",
                    "metrics": systems["v0"],
                },
                {
                    "stage": "V1",
                    "title": "Evidence-grounded prioritization",
                    "decision": "KEPT · DEFAULT",
                    "outcome": "Preserved Recall@3 while reducing false positives and review burden.",
                    "metrics": systems["v1"],
                },
                {
                    "stage": "V0-top3",
                    "title": "Deterministic control",
                    "decision": "CONTROL",
                    "outcome": "Prediction-identical to V0; truncation explained none of the improvement.",
                    "metrics": systems["v0_top3_control"],
                },
                {
                    "stage": "V2",
                    "title": "Independent verifier",
                    "decision": "NOT RETAINED",
                    "outcome": "Added runtime and tokens without shortlist-quality improvement.",
                    "metrics": systems["v2"],
                },
                {
                    "stage": "V3",
                    "title": "Conflict arbitration",
                    "decision": "EXPERIMENTAL",
                    "outcome": (
                        "Removed five false positives across conflict/public tracks, "
                        "but damaged legacy regression recall."
                    ),
                    "metrics": {
                        "regression": phase3_tracks["benchmark_v1"]["v3"],
                        "conflict": phase3_tracks["benchmark_conflict_v1"]["v3"],
                        "public": phase3_tracks["benchmark_public_v1"]["v3"],
                    },
                },
                {
                    "stage": "Quantum",
                    "title": "Optimization experiment",
                    "decision": "NOT IMPLEMENTED",
                    "outcome": "No demonstrated optimization bottleneck justified the complexity.",
                    "metrics": None,
                },
            ],
        }

    def inspect_case(self, value: object) -> Dict[str, object]:
        try:
            if isinstance(value, str):
                value = json.loads(value)
            case = BenchmarkCase.parse_obj(value)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise DemoRepositoryError(f"malformed structured case: {exc}") from exc
        if len(case.candidate_variants) > MAX_INSPECTED_VARIANTS:
            raise DemoRepositoryError(
                f"structured case exceeds the {MAX_INSPECTED_VARIANTS}-variant demo limit"
            )
        variants = [normalize_candidate(candidate) for candidate in case.candidate_variants]
        return self._inspection_payload("structured_case_json", variants)

    def inspect_vcf(self, content: str, *, genome_build: str = "GRCh38") -> Dict[str, object]:
        if not isinstance(content, str) or not content.strip():
            raise DemoRepositoryError("VCF content must be a non-empty string")
        try:
            variants = parse_vcf_text(content, genome_build=genome_build)
        except (OSError, VariantNormalizationError, ValueError) as exc:
            raise DemoRepositoryError(f"malformed VCF input: {exc}") from exc
        if len(variants) > MAX_INSPECTED_VARIANTS:
            raise DemoRepositoryError(
                f"VCF exceeds the {MAX_INSPECTED_VARIANTS}-variant demo limit"
            )
        return self._inspection_payload("vcf_subset", variants)

    @staticmethod
    def _inspection_payload(
        input_format: str, variants: Sequence[CanonicalVariant]
    ) -> Dict[str, object]:
        return {
            "mode": "input_inspection",
            "input_format": input_format,
            "execution_mode": "deterministic_local_only",
            "model_called": False,
            "prediction_available": False,
            "message": (
                "Input normalized successfully. Uploaded inputs are not assigned a "
                "retained ranking; use the documented live V1 CLI for a new model execution."
            ),
            "normalized_variants": [_normalized_payload(variant) for variant in variants],
            "safety_disclaimer": SAFETY_DISCLAIMER,
        }

    @staticmethod
    def _load_result(path: Path) -> EvaluationResult:
        return EvaluationResult.parse_raw(path.read_text(encoding="utf-8"))

    @staticmethod
    def _dashboard_metrics(result: EvaluationResult) -> Dict[str, object]:
        metrics = result.aggregate
        return {
            "system": result.system,
            "model": result.model,
            "provider": _recorded_provider(result.model, result.execution_config),
            "generated_at_utc": result.generated_at_utc.isoformat(),
            "recall_at_1": metrics.recall_at_k.get("1"),
            "recall_at_3": metrics.recall_at_k.get("3"),
            "recall_at_5": metrics.recall_at_k.get("5"),
            "mrr": metrics.mean_reciprocal_rank,
            "shortlist_precision": metrics.shortlist_precision,
            "false_positives": metrics.false_positive_count_at_k.get("5"),
            "review_burden": metrics.review_burden,
            "review_burden_at_full_recall": metrics.review_burden_at_full_recall,
            "mean_runtime_seconds": metrics.mean_runtime_seconds,
            "mean_deterministic_runtime_seconds": metrics.mean_deterministic_runtime_seconds,
            "mean_external_model_runtime_seconds": metrics.mean_external_model_runtime_seconds,
            "model_calls": metrics.total_model_calls,
            "input_tokens": metrics.total_input_tokens,
            "output_tokens": metrics.total_output_tokens,
            "total_tokens": metrics.total_tokens,
            "estimated_cost_usd": metrics.total_estimated_cost_usd,
        }

    @staticmethod
    def _relative_reduction(before: int, after: int) -> Optional[float]:
        if before == 0:
            return None
        return (before - after) / before * 100

    @staticmethod
    def _runs_prediction_identical(first_path: Path, second_path: Path) -> bool:
        first = _records_by_case(load_system_run(first_path))
        second = _records_by_case(load_system_run(second_path))
        if first.keys() != second.keys():
            return False
        return all(
            [item.variant_id for item in first[case_id].ranked_variants]
            == [item.variant_id for item in second[case_id].ranked_variants]
            for case_id in first
        )
