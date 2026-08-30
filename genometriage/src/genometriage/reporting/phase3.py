"""Build machine- and human-readable Phase 3 comparison and failure reports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from genometriage import SAFETY_DISCLAIMER
from genometriage.baseline.runner import load_system_run
from genometriage.benchmark.loader import load_benchmark
from genometriage.models.schema import AggregateMetrics, EvaluationResult, Prediction


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_JSON = ROOT / "results" / "phase3" / "comparison.json"
OUTPUT_MARKDOWN = ROOT / "results" / "phase3" / "COMPARISON.md"
OUTPUT_FAILURES = ROOT / "results" / "phase3" / "failures.jsonl"

TRACKS = {
    "benchmark_v1": {
        "cases": ROOT / "data" / "cases" / "benchmark_v1.jsonl",
        "truth": ROOT / "data" / "ground_truth" / "benchmark_v1_ground_truth.jsonl",
        "v1_prediction": ROOT / "predictions" / "evidence-grounded-v1.json",
        "v3_prediction": ROOT / "predictions" / "conflict-arbitrated-v3.json",
        "v1_result": ROOT / "results" / "phase3" / "benchmark_v1-evidence-grounded-v1.json",
        "v3_result": ROOT / "results" / "phase3" / "benchmark_v1-conflict-arbitrated-v3.json",
    },
    "benchmark_conflict_v1": {
        "cases": ROOT / "data" / "cases" / "benchmark_conflict_v1.jsonl",
        "truth": ROOT / "data" / "ground_truth" / "benchmark_conflict_v1_ground_truth.jsonl",
        "v1_prediction": ROOT / "predictions" / "benchmark_conflict_v1-evidence-grounded-v1.json",
        "v3_prediction": ROOT / "predictions" / "benchmark_conflict_v1-conflict-arbitrated-v3.json",
        "v1_result": ROOT / "results" / "benchmark_conflict_v1-evidence-grounded-v1.json",
        "v3_result": ROOT / "results" / "benchmark_conflict_v1-conflict-arbitrated-v3.json",
    },
    "benchmark_public_v1": {
        "cases": ROOT / "data" / "cases" / "benchmark_public_v1.jsonl",
        "truth": ROOT / "data" / "ground_truth" / "benchmark_public_v1_ground_truth.jsonl",
        "v1_prediction": ROOT / "predictions" / "benchmark_public_v1-evidence-grounded-v1.json",
        "v3_prediction": ROOT / "predictions" / "benchmark_public_v1-conflict-arbitrated-v3.json",
        "v1_result": ROOT / "results" / "benchmark_public_v1-evidence-grounded-v1.json",
        "v3_result": ROOT / "results" / "benchmark_public_v1-conflict-arbitrated-v3.json",
    },
}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _load_result(path: Path) -> EvaluationResult:
    return EvaluationResult.parse_raw(path.read_text(encoding="utf-8"))


def _metric_values(metrics: AggregateMetrics) -> Dict[str, object]:
    case_count = metrics.evaluated_case_count + metrics.failed_case_count
    return {
        "recall_at_1": metrics.recall_at_k.get("1"),
        "recall_at_3": metrics.recall_at_k.get("3"),
        "recall_at_5": metrics.recall_at_k.get("5"),
        "mrr": metrics.mean_reciprocal_rank,
        "shortlist_precision": metrics.shortlist_precision,
        "false_positives": metrics.false_positive_count_at_k.get("5"),
        "false_positives_per_case": metrics.false_positives_per_case,
        "review_burden": metrics.review_burden,
        "review_burden_per_case": metrics.review_burden / case_count if case_count else None,
        "review_burden_at_full_recall": metrics.review_burden_at_full_recall,
        "citation_traceability_error": metrics.citation_traceability_error_rate,
        "claim_support_precision": metrics.claim_support_precision,
        "abstention_count": metrics.abstention_count,
        "insufficient_evidence_count": metrics.insufficient_evidence_count,
        "conflicting_evidence_count": metrics.conflicting_evidence_count,
        "mean_runtime_seconds": metrics.mean_runtime_seconds,
        "mean_deterministic_runtime_seconds": metrics.mean_deterministic_runtime_seconds,
        "mean_external_model_runtime_seconds": metrics.mean_external_model_runtime_seconds,
        "total_model_calls": metrics.total_model_calls,
        "model_calls_per_case": metrics.mean_model_calls_per_case,
        "input_tokens": metrics.total_input_tokens,
        "output_tokens": metrics.total_output_tokens,
        "total_tokens": metrics.total_tokens,
        "cost_usd": metrics.total_estimated_cost_usd,
        "recall_constraint_met": metrics.recall_constraint_met,
    }


def _delta(v1: Mapping[str, object], v3: Mapping[str, object]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for key in v1:
        first = v1[key]
        second = v3.get(key)
        if (
            isinstance(first, (int, float))
            and not isinstance(first, bool)
            and isinstance(second, (int, float))
            and not isinstance(second, bool)
        ):
            result[key] = second - first
        else:
            result[key] = None
    return result


def _predictions_by_case(path: Path) -> Dict[str, Prediction]:
    run = load_system_run(path)
    return {
        record.case_id: record.prediction
        for record in run.records
        if record.status == "completed" and record.prediction is not None
    }


def _failure_trajectories() -> List[Dict[str, object]]:
    failures: List[Dict[str, object]] = []
    for track, paths in TRACKS.items():
        bundle = load_benchmark(paths["cases"], paths["truth"])
        truth_by_case = {truth.case_id: truth for truth in bundle.ground_truth}
        v1_by_case = _predictions_by_case(paths["v1_prediction"])
        v3_by_case = _predictions_by_case(paths["v3_prediction"])
        for case_id in sorted(truth_by_case):
            relevant = set(truth_by_case[case_id].relevant_variant_ids)
            v1 = v1_by_case[case_id]
            v3 = v3_by_case[case_id]
            v1_ids = [item.variant_id for item in v1.ranked_variants]
            v3_ids = [item.variant_id for item in v3.ranked_variants]
            removed = [variant_id for variant_id in v1_ids if variant_id not in v3_ids]
            added = [variant_id for variant_id in v3_ids if variant_id not in v1_ids]
            removed_true = [variant_id for variant_id in removed if variant_id in relevant]
            new_false = [variant_id for variant_id in added if variant_id not in relevant]
            retained_false = [variant_id for variant_id in v3_ids if variant_id not in relevant]
            failure_types = []
            if removed_true:
                failure_types.extend(
                    ["removed_true_positive", "incorrectly_resolved_relevant_evidence"]
                )
            if new_false:
                failure_types.append("introduced_new_false_positive")
            if retained_false:
                failure_types.extend(
                    [
                        "incorrectly_promoted_or_retained_weak_candidate",
                        "claimed_sufficient_attention_where_label_is_irrelevant",
                    ]
                )
            if relevant and not (set(v3_ids) & relevant):
                failure_types.append("abstained_despite_sufficient_ground_truth")
            if not failure_types:
                continue
            audits = {
                audit.variant_id: audit.dict() for audit in v3.arbitration_records
            }
            causes = []
            for variant_id in removed_true:
                audit = audits.get(variant_id, {})
                causes.append(
                    {
                        "variant_id": variant_id,
                        "cause": (
                            "The preregistered minimum support threshold fired on a relevant "
                            "legacy candidate whose evidence summed below 3."
                            if audit.get("fired_rule") == "5_below_support_threshold"
                            else "The preregistered arbitration rule removed a relevant candidate."
                        ),
                    }
                )
            for variant_id in retained_false:
                causes.append(
                    {
                        "variant_id": variant_id,
                        "cause": (
                            "The candidate survived as retain/conflicting_evidence; V3 cannot "
                            "semantically repair missing or legacy-default evidence dimensions."
                        ),
                    }
                )
            failures.append(
                {
                    "track": track,
                    "case_id": case_id,
                    "failure_types": sorted(set(failure_types)),
                    "ground_truth_relevant_variant_ids": sorted(relevant),
                    "v1_ranked_variant_ids": v1_ids,
                    "v3_ranked_variant_ids": v3_ids,
                    "removed_variant_ids": removed,
                    "added_variant_ids": added,
                    "removed_true_positive_ids": removed_true,
                    "new_false_positive_ids": new_false,
                    "retained_false_positive_ids": retained_false,
                    "arbitration_audit": [audits[key] for key in sorted(audits)],
                    "causes": causes,
                    "safety_disclaimer": SAFETY_DISCLAIMER,
                }
            )
    return failures


def _generalization_gap(
    tracks: Mapping[str, Mapping[str, Mapping[str, object]]]
) -> Dict[str, object]:
    measures = (
        "recall_at_3",
        "mrr",
        "shortlist_precision",
        "false_positives_per_case",
        "review_burden_per_case",
        "claim_support_precision",
    )
    result: Dict[str, object] = {}
    for system in ("v1", "v3"):
        base = tracks["benchmark_v1"][system]
        result[system] = {}
        for target in ("benchmark_conflict_v1", "benchmark_public_v1"):
            target_values = tracks[target][system]
            result[system][f"{target}_minus_benchmark_v1"] = {
                metric: (
                    target_values[metric] - base[metric]
                    if isinstance(target_values[metric], (int, float))
                    and isinstance(base[metric], (int, float))
                    else None
                )
                for metric in measures
            }
    return result


def build_reports(
    *,
    output_json: Path = OUTPUT_JSON,
    output_markdown: Path = OUTPUT_MARKDOWN,
    output_failures: Path = OUTPUT_FAILURES,
) -> Tuple[Path, Path, Path]:
    output_json = Path(output_json)
    output_markdown = Path(output_markdown)
    output_failures = Path(output_failures)
    track_metrics: Dict[str, Dict[str, Mapping[str, object]]] = {}
    for track, paths in TRACKS.items():
        v1 = _metric_values(_load_result(paths["v1_result"]).aggregate)
        v3 = _metric_values(_load_result(paths["v3_result"]).aggregate)
        track_metrics[track] = {"v1": v1, "v3": v3, "v3_minus_v1": _delta(v1, v3)}

    failures = _failure_trajectories()
    failure_counts: Dict[str, int] = {}
    for item in failures:
        for failure_type in item["failure_types"]:
            failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1

    try:
        failure_artifact = output_failures.relative_to(ROOT).as_posix()
    except ValueError:
        failure_artifact = output_failures.as_posix()
    payload = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "safety_disclaimer": SAFETY_DISCLAIMER,
        "policy_version": "conflict_arbitration_v1",
        "tracks": track_metrics,
        "generalization_gap": _generalization_gap(track_metrics),
        "failure_summary": {
            "case_count": len(failures),
            "counts_by_type": failure_counts,
            "artifact": failure_artifact,
        },
        "success_assessment": {
            "regression_recall_constraint_met": bool(
                track_metrics["benchmark_v1"]["v3"]["recall_constraint_met"]
            ),
            "held_out_conflict_recall_preserved": (
                track_metrics["benchmark_conflict_v1"]["v3"]["recall_at_3"]
                >= track_metrics["benchmark_conflict_v1"]["v1"]["recall_at_3"]
            ),
            "held_out_conflict_precision_improved": (
                track_metrics["benchmark_conflict_v1"]["v3"]["shortlist_precision"]
                > track_metrics["benchmark_conflict_v1"]["v1"]["shortlist_precision"]
            ),
            "public_recall_preserved": (
                track_metrics["benchmark_public_v1"]["v3"]["recall_at_3"]
                >= track_metrics["benchmark_public_v1"]["v1"]["recall_at_3"]
            ),
            "public_precision_improved": (
                track_metrics["benchmark_public_v1"]["v3"]["shortlist_precision"]
                > track_metrics["benchmark_public_v1"]["v1"]["shortlist_precision"]
            ),
            "decision": (
                "revise_not_global_default: V3 earned its small deterministic complexity on "
                "dimensioned held-out/public tracks, but failed backward-compatible recall."
            ),
        },
        "clearest_remaining_bottleneck": (
            "Evidence-strength and dimension calibration does not transfer safely between "
            "legacy untyped evidence and newer structured/public evidence."
        ),
        "quantum_recommendation": (
            "Do not implement quantum functionality. The observed bottleneck is evidence "
            "calibration and schema transfer, not a demonstrated combinatorial optimization "
            "limit. If a future shortlist-selection constraint is formalized, benchmark a "
            "classical constrained optimizer before considering a separate quantum experiment."
        ),
    }
    _atomic_write(output_json, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _atomic_write(
        output_failures,
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in failures),
    )
    _atomic_write(output_markdown, _render_markdown(payload))
    return output_json, output_markdown, output_failures


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _render_markdown(payload: Mapping[str, object]) -> str:
    tracks = payload["tracks"]
    columns = [
        ("benchmark_v1 V1", tracks["benchmark_v1"]["v1"]),
        ("benchmark_v1 V3", tracks["benchmark_v1"]["v3"]),
        ("conflict V1", tracks["benchmark_conflict_v1"]["v1"]),
        ("conflict V3", tracks["benchmark_conflict_v1"]["v3"]),
        ("public V1", tracks["benchmark_public_v1"]["v1"]),
        ("public V3", tracks["benchmark_public_v1"]["v3"]),
    ]
    rows = [
        ("Recall@1", "recall_at_1"),
        ("Recall@3", "recall_at_3"),
        ("Recall@5", "recall_at_5"),
        ("MRR", "mrr"),
        ("Shortlist precision", "shortlist_precision"),
        ("False positives", "false_positives"),
        ("False positives/case", "false_positives_per_case"),
        ("Review burden", "review_burden"),
        ("Review burden/case", "review_burden_per_case"),
        ("Review burden at full recall", "review_burden_at_full_recall"),
        ("Citation traceability error", "citation_traceability_error"),
        ("Claim support precision", "claim_support_precision"),
        ("Abstention cases", "abstention_count"),
        ("Insufficient-evidence candidates", "insufficient_evidence_count"),
        ("Conflicting-evidence candidates", "conflicting_evidence_count"),
        ("Mean runtime seconds", "mean_runtime_seconds"),
        ("Mean deterministic seconds", "mean_deterministic_runtime_seconds"),
        ("Mean external-model seconds", "mean_external_model_runtime_seconds"),
        ("Total model calls", "total_model_calls"),
        ("Model calls/case", "model_calls_per_case"),
        ("Input tokens", "input_tokens"),
        ("Output tokens", "output_tokens"),
        ("Total tokens", "total_tokens"),
        ("Cost USD", "cost_usd"),
    ]
    lines = [
        "# GenomeTriage Phase 3 comparison",
        "",
        SAFETY_DISCLAIMER,
        "",
        "V3 used the preregistered `conflict_arbitration_v1` policy and made zero additional model calls.",
        "",
        "| Metric | " + " | ".join(label for label, _ in columns) + " |",
        "| --- | " + " | ".join("---:" for _ in columns) + " |",
    ]
    for label, key in rows:
        lines.append(
            f"| {label} | "
            + " | ".join(_fmt(values.get(key)) for _, values in columns)
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Regression: V3 reduced burden 16→14 but Recall@3 fell 1.000→0.909; this is a trade-off and fails the recall constraint.",
            "- Held-out conflict: V3 preserved Recall@3=1.000, removed all four false positives, reduced burden 17→13, and improved shortlist precision 0.764706→1.000000.",
            "- Public: V3 preserved Recall@3=1.000, removed the sole false positive, reduced burden 11→10, and improved shortlist precision 0.909091→1.000000.",
            "- V3 therefore earns its small deterministic complexity on evidence with explicit dimensions, but not as a global replacement for V1 because legacy-evidence recall regressed.",
            "",
            "## Generalization gap",
            "",
            "The held-out and public tracks did not degrade V1/V3 recall. V3 actually performed better there than on `benchmark_v1`; this inverse gap is evidence of schema-transfer sensitivity, not proof of universal generalization. The legacy track defaults evidence dimension to `other`, while the new tracks contain explicit context/provenance dimensions.",
            "",
            "## Failure analysis",
            "",
            f"Structured failures: `{payload['failure_summary']['artifact']}`. "
            f"Failure cases recorded: {payload['failure_summary']['case_count']}.",
            "",
            "The clearest failure is GT-004: both relevant V1 candidates had support score 2 and were removed by the fixed minimum-support rule, producing an empty shortlist. Two legacy false positives also survive because arbitration cannot recover missing semantic dimensions from records defaulted to `other`.",
            "",
            "## Decision and next experiment",
            "",
            str(payload["success_assessment"]["decision"]),
            "",
            "Remaining bottleneck: " + str(payload["clearest_remaining_bottleneck"]),
            "",
            "Quantum recommendation: " + str(payload["quantum_recommendation"]),
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=OUTPUT_MARKDOWN)
    parser.add_argument("--failure-analysis", type=Path, default=OUTPUT_FAILURES)
    args = parser.parse_args(argv)
    outputs = build_reports(
        output_json=args.output_json,
        output_markdown=args.output_markdown,
        output_failures=args.failure_analysis,
    )
    print(SAFETY_DISCLAIMER)
    print("Phase 3 reports: " + ", ".join(str(path) for path in outputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
