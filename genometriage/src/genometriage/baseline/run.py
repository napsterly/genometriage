"""Run the single-call LLM baseline and save raw predictions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from genometriage.benchmark.loader import DEFAULT_CASES_PATH, load_cases
from genometriage.config import load_project_environment

from .provider import ProviderError, create_provider
from .runner import (
    BaselineSystem,
    load_system_run,
    validate_resume_run,
    write_system_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--provider", choices=["gemini", "openai"], default="gemini")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", help="Override the selected provider's model")
    parser.add_argument(
        "--min-request-interval-seconds",
        type=float,
        help="Minimum time between request starts (default: provider-specific)",
    )
    parser.add_argument("--limit", type=int, help="Run only the first N cases")
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
    cases = load_cases(args.cases)
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        cases = cases[: args.limit]
    try:
        provider = create_provider(args.provider, model=args.model)
    except ProviderError as exc:
        raise SystemExit(str(exc)) from exc
    system_name = f"baseline-{args.provider}"
    output = args.output or Path(f"predictions/{system_name}.json")
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
    if args.resume and output.is_file():
        resume_run = load_system_run(output)
        try:
            validate_resume_run(resume_run, system, cases_path=args.cases)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    run = system.run(
        cases,
        cases_path=args.cases,
        fail_fast=args.fail_fast,
        initial_records=resume_run.records if resume_run else (),
        created_at_utc=resume_run.created_at_utc if resume_run else None,
        checkpoint_callback=lambda checkpoint: write_system_run(checkpoint, output),
    )
    write_system_run(run, output)
    completed = sum(record.status == "completed" for record in run.records)
    failed = len(run.records) - completed
    print(
        f"Baseline complete: {completed} completed, {failed} failed; "
        f"raw predictions: {output}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
