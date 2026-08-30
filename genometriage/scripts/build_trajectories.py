"""Build representative Phase 4 trajectories from retained artifacts only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping, Optional

from genometriage import SAFETY_DISCLAIMER
from genometriage.app.repository import DemoRepository, ROOT, TRACKS
from genometriage.baseline.runner import load_system_run
from genometriage.models.schema import EvaluationResult, Prediction


OUTPUT_DIR = ROOT / "artifacts" / "trajectories"
TRAJECTORIES = (
    {
        "filename": "01_straightforward_gt001.json",
        "trajectory_id": "trajectory-straightforward-gt001",
        "title": "Straightforward V1 success",
        "category": "straightforward_success",
        "track": "benchmark_v1",
        "case_id": "GT-001",
        "include_baseline": True,
        "include_v3": False,
        "why_selected": "A single supported candidate is ranked first without uncertainty escalation.",
    },
    {
        "filename": "02_noisy_gt002.json",
        "trajectory_id": "trajectory-noisy-gt002",
        "title": "Evidence grounding removes noisy candidates",
        "category": "noisy_case",
        "track": "benchmark_v1",
        "case_id": "GT-002",
        "include_baseline": True,
        "include_v3": False,
        "why_selected": "V0 returned three candidates; V1 retained one and removed two review items.",
    },
    {
        "filename": "03_conflict_gc003.json",
        "trajectory_id": "trajectory-conflict-gc003",
        "title": "Held-out conflict-heavy case",
        "category": "conflicting_evidence",
        "track": "benchmark_conflict_v1",
        "case_id": "GC-003",
        "include_baseline": False,
        "include_v3": True,
        "why_selected": "The retained V1 output escalates uncertainty on two plausible candidates; V3 remains experimental.",
    },
    {
        "filename": "04_public_gp009.json",
        "trajectory_id": "trajectory-public-gp009",
        "title": "Pinned public ClinVar example",
        "category": "public_clinvar_proxy",
        "track": "benchmark_public_v1",
        "case_id": "GP-009",
        "include_baseline": False,
        "include_v3": False,
        "why_selected": "A real public PAH locus with an expert-panel aggregate review record and versioned provenance.",
    },
    {
        "filename": "05_v3_regression_gt004.json",
        "trajectory_id": "trajectory-v3-regression-gt004",
        "title": "Why V3 was not promoted globally",
        "category": "experimental_regression_failure",
        "track": "benchmark_v1",
        "case_id": "GT-004",
        "include_baseline": True,
        "include_v3": True,
        "why_selected": "The frozen V3 support threshold removes both relevant V1 candidates, failing the regression recall constraint.",
    },
)


def _predictions(path: Path) -> Dict[str, Prediction]:
    run = load_system_run(path)
    return {
        record.case_id: record.prediction
        for record in run.records
        if record.status == "completed" and record.prediction is not None
    }


def _evaluations(path: Path) -> Dict[str, Mapping[str, object]]:
    result = EvaluationResult.parse_raw(path.read_text(encoding="utf-8"))
    return {item.case_id: item.dict() for item in result.cases}


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _experimental_payload(
    track_id: str,
    case_id: str,
    *,
    result_path: Optional[Path],
    prediction_path: Optional[Path],
) -> Optional[Dict[str, object]]:
    if result_path is None or prediction_path is None:
        return None
    prediction = _predictions(prediction_path)[case_id]
    evaluation = _evaluations(result_path)[case_id]
    return {
        "system": prediction.system,
        "purpose": "Experimental deterministic conflict arbitration; not the product default.",
        "structured_response": prediction.dict(),
        "evaluator_outcome": evaluation,
        "decision": (
            "V3 is promising on dimensioned evidence but is not retained globally "
            "because benchmark_v1 Recall@3 regressed."
        ),
    }


def build_trajectories() -> None:
    repository = DemoRepository()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for item in TRAJECTORIES:
        track_id = str(item["track"])
        case_id = str(item["case_id"])
        config = TRACKS[track_id]
        product = repository.case_payload(track_id, case_id)
        v1_prediction = _predictions(config.v1_predictions_path)[case_id]
        v1_evaluation = _evaluations(config.v1_results_path)[case_id]
        evidence_ids = sorted(
            {
                record["evidence_id"]
                for records in product["retrieval"]["evidence_by_variant"].values()
                for record in records
            }
        )
        baseline = product["baseline_comparison"] if item["include_baseline"] else None
        experimental = (
            _experimental_payload(
                track_id,
                case_id,
                result_path=config.v3_results_path,
                prediction_path=config.v3_predictions_path,
            )
            if item["include_v3"]
            else None
        )
        payload = {
            "schema_version": "1.0",
            "trajectory_id": item["trajectory_id"],
            "title": item["title"],
            "category": item["category"],
            "why_selected": item["why_selected"],
            "artifact_policy": {
                "recorded_execution": True,
                "execution_label": product["replay_label"],
                "hidden_reasoning_included": False,
                "chain_of_thought_invented": False,
                "content_scope": (
                    "Recorded instructions/configuration, deterministic preprocessing, "
                    "retrieved evidence, structured model output, and evaluator feedback only."
                ),
            },
            "case_input": product["case"],
            "system_configuration": product["system"],
            "deterministic_preprocessing": {
                "normalization": product["normalization"],
                "retrieval_method": product["retrieval"]["method"],
                "evidence_snapshot_version": product["retrieval"]["snapshot_version"],
                "evidence_snapshot_sha256": product["retrieval"]["snapshot_sha256"],
            },
            "evidence_retrieved": product["retrieval"]["evidence_by_variant"],
            "model_input_summary": {
                "case_id": case_id,
                "candidate_variant_ids": [
                    candidate["variant_id"] for candidate in product["case"]["candidates"]
                ],
                "retrieved_evidence_ids": evidence_ids,
                "input_boundary": (
                    "V1 received model-visible context, normalized candidates, and only "
                    "the exact frozen evidence retrieved for those candidates."
                ),
                "prompt_version": v1_prediction.prompt_version,
                "prompt_sha256": product["system"]["prompt_sha256"],
            },
            "model_structured_response": v1_prediction.dict(),
            "resulting_shortlist": product["shortlist"],
            "provider_retries_or_failures": v1_prediction.provider_retry_errors,
            "baseline_comparison": baseline,
            "evaluator_outcome": {
                "mode": "explicit_evaluation_feedback",
                "ground_truth_variant_ids_exposed": False,
                "metrics": v1_evaluation,
            },
            "experimental_follow_up": experimental,
            "human_review_checkpoint": product["human_review_checkpoint"],
            "safety_disclaimer": SAFETY_DISCLAIMER,
        }
        _atomic_json(OUTPUT_DIR / str(item["filename"]), payload)
        print(f"wrote {OUTPUT_DIR / str(item['filename'])}")


def main() -> int:
    build_trajectories()
    print(SAFETY_DISCLAIMER)
    print("Trajectories contain no hidden chain-of-thought or private genomic data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
