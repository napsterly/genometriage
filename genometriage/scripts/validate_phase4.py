"""Read-only validation and tracked-file secret scan for the Phase 4 package."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List

from genometriage import SAFETY_DISCLAIMER
from genometriage.app.repository import DemoRepository, REPLAY_LABEL, ROOT
from genometriage.benchmark.loader import file_sha256


FREEZE_PATH = ROOT / "docs" / "PHASE4_INPUT_FREEZE.json"
TRAJECTORY_DIR = ROOT / "artifacts" / "trajectories"
SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"sk-[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?i)(?:gemini|google|openai)_api_key\s*[=:]\s*['\"]?[A-Za-z0-9_-]{20,}"),
)


def validate_historical_hashes() -> int:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    artifacts: Dict[str, str] = freeze["artifacts"]
    for relative_path, expected in artifacts.items():
        actual = file_sha256(ROOT / relative_path)
        if actual != expected:
            raise SystemExit(f"historical artifact changed: {relative_path}")
    return len(artifacts)


def validate_demo() -> None:
    repository = DemoRepository()
    catalog = repository.catalog()
    product = repository.case_payload(catalog["default_track"], catalog["default_case"])
    dashboard = repository.dashboard()
    serialized = json.dumps(product, sort_keys=True)
    forbidden = ("relevant_variant_ids", "ground_truth", "evaluator-only")
    if any(term in serialized for term in forbidden):
        raise SystemExit("product payload contains evaluator-only data")
    if product["replay_label"] != REPLAY_LABEL:
        raise SystemExit("demo does not identify retained replay mode")
    if product["safety_disclaimer"] != SAFETY_DISCLAIMER:
        raise SystemExit("product safety label is missing")
    if dashboard["systems"]["v1"]["false_positives"] != 2:
        raise SystemExit("dashboard did not load the frozen V1 metrics")


def validate_trajectories() -> int:
    paths = sorted(TRAJECTORY_DIR.glob("*.json"))
    if len(paths) != 5:
        raise SystemExit(f"expected five trajectories, found {len(paths)}")
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("safety_disclaimer") != SAFETY_DISCLAIMER:
            raise SystemExit(f"trajectory safety label missing: {path.name}")
        policy = value.get("artifact_policy", {})
        if policy.get("hidden_reasoning_included") is not False:
            raise SystemExit(f"trajectory exposes hidden reasoning: {path.name}")
        if policy.get("chain_of_thought_invented") is not False:
            raise SystemExit(f"trajectory invents chain-of-thought: {path.name}")
    return len(paths)


def _submission_paths() -> Iterable[Path]:
    paths = set()
    try:
        output = subprocess.run(
            ["git", "ls-files", "-z", "--", "genometriage"],
            cwd=ROOT.parent,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        raise SystemExit(f"unable to enumerate tracked submission files: {exc}") from exc
    prefix = "genometriage/"
    for item in output.split("\0"):
        if not item:
            continue
        relative = item.replace("\\", "/")
        if relative.startswith(prefix):
            paths.add(ROOT / relative[len(prefix) :])
    for directory in ("src", "scripts", "docs", "artifacts", "tests"):
        paths.update(path for path in (ROOT / directory).rglob("*") if path.is_file())
    for filename in ("README.md", "pyproject.toml", ".gitignore", ".env.example"):
        path = ROOT / filename
        if path.is_file():
            paths.add(path)
    yield from sorted(paths)


def secret_scan() -> int:
    findings: List[str] = []
    checked = 0
    for path in _submission_paths():
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        checked += 1
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            findings.append(path.relative_to(ROOT).as_posix())
    if findings:
        raise SystemExit("possible secret in tracked file(s): " + ", ".join(findings))
    return checked


def main() -> int:
    frozen_count = validate_historical_hashes()
    validate_demo()
    trajectory_count = validate_trajectories()
    scanned_count = secret_scan()
    print(SAFETY_DISCLAIMER)
    print(
        "Phase 4 validation passed: "
        f"{frozen_count} historical artifacts unchanged; "
        f"{trajectory_count} trajectories; {scanned_count} tracked text files secret-scanned; "
        "offline demo payload safe."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
