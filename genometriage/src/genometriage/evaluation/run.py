"""Run or replay a system on the sealed benchmark and write evaluation JSON."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional, Sequence

from genometriage.baseline.provider import ProviderError, create_provider
from genometriage.baseline.runner import (
    BaselineSystem,
    load_system_run,
    validate_resume_run,
    write_system_run,
)
from genometriage.benchmark.loader import (
    DEFAULT_CASES_PATH,
    DEFAULT_GROUND_TRUTH_PATH,
    load_benchmark,
)
from genometriage.config import load_project_environment
from genometriage.reporting import render_terminal_summary

from .evaluator import evaluate_run


def _parse_k_values(value: str) -> List[int]:
    try:
        values = sorted({int(item.strip()) for item in value.split(",")})
    except ValueError as exc:
        raise argparse.ArgumentTypeError("K values must be comma-separated integers") from exc
    if not values or any(item < 1 for item in values):
        raise argparse.ArgumentTypeError("K values must be positive")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--system",
        choices=["baseline", "v0-top3-control", "v1", "v2", "v3"],
        required=True,
    )
    parser.add_argument("--provider", choices=["gemini", "openai"], default="gemini")
    parser.add_argument(
        "--predictions",
        type=Path,
        help="Replay an existing raw SystemRun JSON instead of calling a model",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH_PATH)
    parser.add_argument("--model", help="Override the selected provider's model")
    parser.add_argument(
        "--min-request-interval-seconds",
        type=float,
        help="Minimum time between request starts (default: provider-specific)",
    )
    parser.add_argument("--k", type=_parse_k_values, default=[1, 3, 5])
    parser.add_argument("--primary-k", type=int, default=5)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume compatible completed cases from the raw output checkpoint",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    load_project_environment()
    if args.primary_k not in args.k:
        raise SystemExit("--primary-k must be included in --k")
    if args.predictions and args.resume:
        raise SystemExit("--resume cannot be combined with --predictions")
    bundle = load_benchmark(args.cases, args.ground_truth)

    if args.predictions:
        run = load_system_run(args.predictions)
    else:
        if args.system != "baseline":
            raise SystemExit(
                "non-baseline evaluation requires a retained --predictions artifact"
            )
        try:
            provider = create_provider(args.provider, model=args.model)
        except ProviderError as exc:
            raise SystemExit(str(exc)) from exc
        system_name = f"baseline-{args.provider}"
        raw_output = args.raw_output or Path(f"predictions/{system_name}.json")
        interval = (
            provider.default_min_request_interval_seconds
            if args.min_request_interval_seconds is None
            else args.min_request_interval_seconds
        )
        try:
            system = BaselineSystem(
                provider,
                system_name=system_name,
                min_request_interval_seconds=interval,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        resume_run = None
        if args.resume and raw_output.is_file():
            resume_run = load_system_run(raw_output)
            try:
                validate_resume_run(resume_run, system, cases_path=args.cases)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
        run = system.run(
            bundle.cases,
            cases_path=args.cases,
            fail_fast=args.fail_fast,
            initial_records=resume_run.records if resume_run else (),
            created_at_utc=resume_run.created_at_utc if resume_run else None,
            checkpoint_callback=lambda checkpoint: write_system_run(
                checkpoint, raw_output
            ),
        )

    allowed_systems = {
        "baseline": {"baseline", "baseline-gemini", "baseline-openai"},
        "v0-top3-control": {"v0-top3-control"},
        "v1": {"evidence-grounded-v1"},
        "v2": {"verified-v2"},
        "v3": {"conflict-arbitrated-v3"},
    }
    if run.system not in allowed_systems[args.system]:
        raise SystemExit(
            f"prediction system mismatch: requested {args.system!r}, file has {run.system!r}"
        )
    result = evaluate_run(
        bundle,
        run,
        k_values=args.k,
        primary_k=args.primary_k,
    )
    output = args.output or Path(f"results/{run.system}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.json(indent=2) + "\n", encoding="utf-8")
    print(render_terminal_summary(result, str(output)))
    return 1 if result.aggregate.failed_case_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
