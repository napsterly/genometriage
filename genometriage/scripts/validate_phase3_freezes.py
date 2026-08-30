"""Read-only validation for all sealed GenomeTriage Phase 3 artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from genometriage import SAFETY_DISCLAIMER
from genometriage.benchmark.loader import (
    file_sha256,
    load_benchmark,
    visible_fixture_contains_answer_fields,
)
from genometriage.evidence import EvidenceStore


ROOT = Path(__file__).resolve().parents[1]


def _load_json(relative_path: str) -> Dict[str, Any]:
    path = ROOT / relative_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid JSON artifact {relative_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"expected a JSON object: {relative_path}")
    return value


def _validate_artifact_map(manifest_path: str) -> int:
    manifest = _load_json(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise SystemExit(f"freeze manifest has no artifacts: {manifest_path}")
    for relative_path, expected_sha256 in artifacts.items():
        actual_sha256 = file_sha256(ROOT / relative_path)
        if actual_sha256 != expected_sha256:
            raise SystemExit(
                f"freeze hash mismatch for {relative_path}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
    return len(artifacts)


def _validate_benchmark(cases: str, ground_truth: str) -> int:
    cases_path = ROOT / cases
    bundle = load_benchmark(cases_path, ROOT / ground_truth)
    if visible_fixture_contains_answer_fields(cases_path):
        raise SystemExit(f"model-visible fixture leaks evaluator labels: {cases}")
    return len(bundle.cases)


def _validate_evidence(cases: str, evidence: str, manifest: str) -> int:
    store = EvidenceStore.load(
        evidence_path=ROOT / evidence,
        manifest_path=ROOT / manifest,
        cases_path=ROOT / cases,
    )
    return len(store.records)


def main() -> int:
    conflict_artifacts = _validate_artifact_map(
        "data/manifests/benchmark_conflict_v1_freeze.json"
    )
    public_artifacts = _validate_artifact_map(
        "data/manifests/benchmark_public_v1_freeze.json"
    )

    policy = _load_json("docs/CONFLICT_ARBITRATION_SPEC_FREEZE.json")
    policy_path = str(policy["spec_path"])
    policy_sha256 = file_sha256(ROOT / policy_path)
    if policy_sha256 != policy["spec_sha256"]:
        raise SystemExit(f"arbitration specification hash mismatch: {policy_path}")
    preregistration = policy.get("preregistration", {})
    if preregistration.get("evaluation_run_before_spec") is not False:
        raise SystemExit("arbitration freeze does not assert pre-evaluation registration")
    if preregistration.get("post_hoc_changes_permitted") is not False:
        raise SystemExit("arbitration freeze unexpectedly permits post-hoc changes")

    conflict_cases = _validate_benchmark(
        "data/cases/benchmark_conflict_v1.jsonl",
        "data/ground_truth/benchmark_conflict_v1_ground_truth.jsonl",
    )
    public_cases = _validate_benchmark(
        "data/cases/benchmark_public_v1.jsonl",
        "data/ground_truth/benchmark_public_v1_ground_truth.jsonl",
    )
    conflict_evidence = _validate_evidence(
        "data/cases/benchmark_conflict_v1.jsonl",
        "data/evidence/evidence_conflict_v1.jsonl",
        "data/evidence/evidence_conflict_v1_manifest.json",
    )
    public_evidence = _validate_evidence(
        "data/cases/benchmark_public_v1.jsonl",
        "data/evidence/evidence_public_v1.jsonl",
        "data/evidence/evidence_public_v1_manifest.json",
    )

    print(SAFETY_DISCLAIMER)
    print(
        "Phase 3 freeze validation passed: "
        f"conflict={conflict_cases} cases/{conflict_evidence} evidence records/"
        f"{conflict_artifacts} frozen artifacts; "
        f"public={public_cases} cases/{public_evidence} evidence records/"
        f"{public_artifacts} frozen artifacts; arbitration spec={policy_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
