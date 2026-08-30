from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from genometriage import SAFETY_DISCLAIMER
from genometriage.app.repository import DemoRepository, DemoRepositoryError, REPLAY_LABEL
from genometriage.app.server import create_server
from genometriage.benchmark.loader import file_sha256
from genometriage.models.schema import EvaluationResult


ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def repository() -> DemoRepository:
    return DemoRepository()


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def test_dashboard_reads_frozen_metrics_instead_of_ui_constants(
    repository: DemoRepository,
) -> None:
    dashboard = repository.dashboard()
    baseline = EvaluationResult.parse_raw(
        (ROOT / "results" / "baseline-gemini-phase2-replay.json").read_text(
            encoding="utf-8"
        )
    ).aggregate
    v1 = EvaluationResult.parse_raw(
        (ROOT / "results" / "evidence-grounded-v1.json").read_text(encoding="utf-8")
    ).aggregate
    assert dashboard["systems"]["v0"]["false_positives"] == baseline.false_positive_count_at_k["5"]
    assert dashboard["systems"]["v1"]["review_burden"] == v1.review_burden
    assert dashboard["headline"]["false_positive_reduction_percent"] == pytest.approx(
        77.7777777778
    )
    assert dashboard["headline"]["review_burden_reduction_percent"] == pytest.approx(
        30.4347826087
    )
    assert dashboard["control"]["prediction_identical"] is True


def test_product_payload_has_no_evaluator_ground_truth_and_identifies_replay(
    repository: DemoRepository,
) -> None:
    payload = repository.case_payload("benchmark_v1", "GT-002")
    forbidden = {"ground_truth", "relevant_variant_ids", "rationale", "difficulty"}
    assert not (_all_keys(payload) & forbidden)
    assert payload["mode"] == "product"
    assert payload["execution_mode"] == "recorded_replay"
    assert payload["replay_label"] == REPLAY_LABEL
    assert payload["safety_disclaimer"] == SAFETY_DISCLAIMER
    assert payload["baseline_comparison"]["removed_by_v1"] == ["GT002-V4", "GT002-V2"]


def test_public_provenance_ids_and_links_are_renderable(repository: DemoRepository) -> None:
    payload = repository.case_payload("benchmark_public_v1", "GP-009")
    records = [
        record
        for variant_records in payload["retrieval"]["evidence_by_variant"].values()
        for record in variant_records
    ]
    assert records
    assert all(record["evidence_id"] for record in records)
    assert all(record["original_source_record_id"].startswith("CLINVAR:VCV") for record in records)
    assert all(record["provenance"]["source_release"] for record in records)
    assert all(record["provenance"]["source_url"].startswith("https://") for record in records)


def test_uploaded_inputs_are_normalization_only_and_malformed_inputs_are_safe(
    repository: DemoRepository,
) -> None:
    vcf = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\nchr1\t10\tdemo\tAC\tAT\t.\tPASS\t.\n"
    result = repository.inspect_vcf(vcf)
    assert result["model_called"] is False
    assert result["prediction_available"] is False
    assert result["normalized_variants"][0]["canonical_id"] == "GRCh38:1:11:C:T"
    assert result["safety_disclaimer"] == SAFETY_DISCLAIMER

    with pytest.raises(DemoRepositoryError, match="malformed VCF"):
        repository.inspect_vcf("not a VCF")
    with pytest.raises(DemoRepositoryError, match="malformed structured case"):
        repository.inspect_case({"case_id": "private-patient"})


def test_local_http_app_health_static_safety_and_malformed_request(
    repository: DemoRepository,
) -> None:
    server = create_server(port=0, repository=repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=5) as response:
            health = json.loads(response.read())
            assert health["safety_disclaimer"] == SAFETY_DISCLAIMER
            assert response.headers["Cache-Control"] == "no-store"
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
            page = response.read().decode("utf-8")
            assert SAFETY_DISCLAIMER in page
            assert "GenomeTriage V1" in page

        request = urllib.request.Request(
            f"http://{host}:{port}/api/inspect",
            data=b'{"format":"vcf","content":"bad"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as captured:
            urllib.request.urlopen(request, timeout=5)
        assert captured.value.code == 400
        error = json.loads(captured.value.read())
        assert error["safety_disclaimer"] == SAFETY_DISCLAIMER
        assert "malformed VCF" in error["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_phase4_input_manifest_guards_v0_v1_v2_v3_artifacts() -> None:
    freeze = json.loads(
        (ROOT / "docs" / "PHASE4_INPUT_FREEZE.json").read_text(encoding="utf-8")
    )
    assert len(freeze["artifacts"]) == 18
    for relative_path, expected in freeze["artifacts"].items():
        assert file_sha256(ROOT / relative_path) == expected


def test_phase4_readme_commands_and_static_assets_are_present() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required = (
        "genometriage.app.run",
        "validate_phase3_freezes.py",
        "build_trajectories.py",
        "genometriage.reporting.comparison",
        "genometriage.reporting.phase3",
    )
    assert all(command in readme for command in required)
    for filename in ("index.html", "styles.css", "app.js"):
        assert (ROOT / "src" / "genometriage" / "app" / "static" / filename).is_file()
