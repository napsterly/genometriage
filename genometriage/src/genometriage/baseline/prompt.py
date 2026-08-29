"""Versioned prompt loading and deterministic case serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict

from genometriage.benchmark.loader import PROJECT_ROOT
from genometriage.models.schema import BenchmarkCase


PROMPT_VERSION = "baseline_v1"
DEFAULT_PROMPT_PATH = PROJECT_ROOT / "prompts" / f"{PROMPT_VERSION}.md"


def load_prompt_template(path: Path = DEFAULT_PROMPT_PATH) -> str:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"baseline prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def prompt_sha256(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def render_prompt(case: BenchmarkCase, template: str) -> str:
    case_json = json.dumps(
        case.dict(),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
    return f"{template.rstrip()}\n\n## Model-visible case JSON\n\n```json\n{case_json}\n```\n"


def baseline_response_schema() -> Dict[str, object]:
    """Strict JSON Schema for the content produced by the one LLM call."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["ranked_variants", "escalated_uncertainty", "notes"],
        "properties": {
            "ranked_variants": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "variant_id",
                        "rank",
                        "reason",
                        "confidence",
                        "evidence_source_ids",
                    ],
                    "properties": {
                        "variant_id": {"type": "string", "minLength": 1},
                        "rank": {"type": "integer", "minimum": 1},
                        "reason": {"type": "string", "minLength": 1},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "evidence_source_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "escalated_uncertainty": {"type": "boolean"},
            "notes": {"type": ["string", "null"]},
        },
    }
