from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
GIT_ROOT = Path(
    subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
).resolve()
PROJECT_PREFIX = ROOT.resolve().relative_to(GIT_ROOT).as_posix()
ARTIFACT_MANIFESTS = (
    "docs/PHASE1_FREEZE.json",
    "docs/PHASE4_INPUT_FREEZE.json",
    "data/manifests/benchmark_conflict_v1_freeze.json",
    "data/manifests/benchmark_public_v1_freeze.json",
    "data/public/clinvar/benchmark_public_v1_source_manifest.json",
)
EVIDENCE_MANIFESTS = (
    "data/evidence/evidence_v1_manifest.json",
    "data/evidence/evidence_conflict_v1_manifest.json",
    "data/evidence/evidence_public_v1_manifest.json",
)


def _git(*arguments: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=GIT_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=not binary,
    )
    return result.stdout if binary else result.stdout.strip()


def _add_expected(
    expected: dict[str, str], relative_path: str, sha256: str
) -> None:
    previous = expected.setdefault(relative_path, sha256)
    assert previous == sha256, f"conflicting freeze hashes: {relative_path}"


def _frozen_artifacts() -> dict[str, str]:
    expected: dict[str, str] = {}
    for manifest_path in ARTIFACT_MANIFESTS:
        manifest = json.loads((ROOT / manifest_path).read_text(encoding="utf-8"))
        for relative_path, sha256 in manifest.get("artifacts", {}).items():
            _add_expected(expected, relative_path, sha256)

    policy = json.loads(
        (ROOT / "docs/CONFLICT_ARBITRATION_SPEC_FREEZE.json").read_text(
            encoding="utf-8"
        )
    )
    _add_expected(expected, policy["spec_path"], policy["spec_sha256"])

    for manifest_path in EVIDENCE_MANIFESTS:
        manifest = json.loads((ROOT / manifest_path).read_text(encoding="utf-8"))
        _add_expected(
            expected, manifest["evidence_file"], manifest["evidence_file_sha256"]
        )
        _add_expected(
            expected, manifest["source_fixture"], manifest["source_fixture_sha256"]
        )
        source_record_sha256 = manifest.get("source_metadata", {}).get(
            "source_record_sha256"
        )
        if source_record_sha256:
            _add_expected(
                expected,
                "data/public/clinvar/benchmark_public_v1_selected_records.json",
                source_record_sha256,
            )
    return expected


def _git_paths(relative_paths: list[str]) -> dict[str, str]:
    return {
        path: f"{PROJECT_PREFIX}/{path}" if PROJECT_PREFIX != "." else path
        for path in relative_paths
    }


def _index_oids(git_paths: list[str]) -> dict[str, str]:
    output = str(_git("ls-files", "--stage", "--", *git_paths))
    result: dict[str, str] = {}
    for line in output.splitlines():
        metadata, path = line.split("\t", 1)
        _mode, oid, stage = metadata.split()
        assert stage == "0"
        result[path] = oid
    return result


def _cat_file_batch(oids: list[str]) -> dict[str, bytes]:
    process = subprocess.run(
        ("git", "cat-file", "--batch"),
        cwd=GIT_ROOT,
        check=True,
        input=("\n".join(oids) + "\n").encode(),
        stdout=subprocess.PIPE,
    )
    output = process.stdout
    position = 0
    result: dict[str, bytes] = {}
    for requested_oid in oids:
        header_end = output.index(b"\n", position)
        header = output[position:header_end].decode().split()
        assert header[0] == requested_oid and header[1] == "blob"
        size = int(header[2])
        data_start = header_end + 1
        data_end = data_start + size
        result[requested_oid] = output[data_start:data_end]
        assert output[data_end : data_end + 1] == b"\n"
        position = data_end + 1
    return result


def test_byte_frozen_artifacts_match_worktree_index_and_clean_conversion() -> None:
    expected = _frozen_artifacts()
    assert len(expected) == 36
    git_paths = _git_paths(sorted(expected))
    index_oids = _index_oids(list(git_paths.values()))
    assert set(index_oids) == set(git_paths.values())
    blobs = _cat_file_batch(list(dict.fromkeys(index_oids.values())))

    for relative_path, expected_sha256 in expected.items():
        worktree_sha256 = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert worktree_sha256 == expected_sha256, (
            f"frozen worktree bytes changed: {relative_path}"
        )

        git_path = git_paths[relative_path]
        index_sha256 = hashlib.sha256(blobs[index_oids[git_path]]).hexdigest()
        assert index_sha256 == expected_sha256, (
            f"staged Git bytes differ from freeze: {relative_path}"
        )

    byte_exact_paths = sorted(
        path
        for path in expected
        if path.startswith(("predictions/", "results/"))
        and Path(path).suffix in {".json", ".jsonl"}
    )
    for relative_path in byte_exact_paths:
        git_path = git_paths[relative_path]
        attributes = str(_git("check-attr", "text", "eol", "--", git_path))
        assert f"{git_path}: text: unset" in attributes
        assert f"{git_path}: eol: unset" in attributes
        clean_oid = str(
            _git(
                "hash-object",
                f"--path={git_path}",
                git_path,
            )
        )
        assert clean_oid == index_oids[git_path], (
            f"Git clean conversion would change frozen bytes: {relative_path}"
        )
