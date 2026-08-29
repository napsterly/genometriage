"""CLI for benchmark schema and separation checks."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .loader import (
    DEFAULT_CASES_PATH,
    DEFAULT_GROUND_TRUTH_PATH,
    load_benchmark,
    visible_fixture_contains_answer_fields,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH_PATH)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    bundle = load_benchmark(args.cases, args.ground_truth)
    if visible_fixture_contains_answer_fields(args.cases):
        raise SystemExit("model-visible fixture contains evaluator-only answer fields")
    negative_controls = sum(
        1 for truth in bundle.ground_truth if not truth.relevant_variant_ids
    )
    print(
        f"Validated {len(bundle.cases)} cases "
        f"({negative_controls} negative control); benchmark sha256={bundle.sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

