"""Run GenomeTriage evidence-grounded V1 or verification-only V2."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from genometriage import SAFETY_DISCLAIMER
from genometriage.baseline.provider import ProviderError, create_provider
from genometriage.baseline.runner import load_system_run, write_system_run
from genometriage.benchmark.loader import DEFAULT_CASES_PATH, load_cases
from genometriage.config import load_project_environment
from genometriage.evidence import DEFAULT_EVIDENCE_PATH, DEFAULT_MANIFEST_PATH, EvidenceStore

from .runner import EvidenceGroundedSystem, VerificationSystem, validate_resume_run


DEFAULT_V1_MODEL = "gemini-3.5-flash-lite"
DEFAULT_V2_MODEL = "gemini-3.7-flash"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=["v1", "v2"], required=True)
    parser.add_argument("--provider", choices=["gemini", "openai"], default="gemini")
    parser.add_argument("--model", help="Override the version-specific verifier/prioritizer model")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--benchmark-version", default="benchmark_v1")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--evidence-manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--v1-predictions",
        type=Path,
        default=Path("predictions/evidence-grounded-v1.json"),
        help="Completed V1 run consumed by V2 without rerunning prioritization",
    )
    parser.add_argument(
        "--min-request-interval-seconds",
        type=float,
        help="Minimum time between request starts (default: provider-specific)",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    load_project_environment()
    cases = load_cases(args.cases)
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        cases = cases[: args.limit]
    model = args.model
    if args.provider == "gemini" and model is None:
        model = DEFAULT_V1_MODEL if args.system == "v1" else DEFAULT_V2_MODEL
    try:
        provider = create_provider(args.provider, model=model)
    except ProviderError as exc:
        raise SystemExit(str(exc)) from exc
    interval = (
        provider.default_min_request_interval_seconds
        if args.min_request_interval_seconds is None
        else args.min_request_interval_seconds
    )
    store = EvidenceStore.load(
        evidence_path=args.evidence,
        manifest_path=args.evidence_manifest,
        cases_path=args.cases,
    )
    if args.system == "v1":
        system = EvidenceGroundedSystem(
            provider,
            store,
            min_request_interval_seconds=interval,
            benchmark_version=args.benchmark_version,
        )
        output = args.output or Path(
            "predictions/evidence-grounded-v1.json"
            if args.benchmark_version == "benchmark_v1"
            else f"predictions/{args.benchmark_version}-evidence-grounded-v1.json"
        )
    else:
        if not args.v1_predictions.is_file():
            raise SystemExit(f"V1 predictions not found: {args.v1_predictions}")
        v1_run = load_system_run(args.v1_predictions)
        system = VerificationSystem(
            provider,
            store,
            v1_run,
            min_request_interval_seconds=interval,
        )
        output = args.output or Path("predictions/verified-v2.json")

    resume_run = None
    if args.resume and output.is_file():
        resume_run = load_system_run(output)
        try:
            validate_resume_run(
                resume_run,
                system=system.system_name,
                prompt_version=system.prompt_version,
                model=system.model,
                prompt_hash=system.prompt_hash,
                execution_config=system.execution_config,
                cases_path=args.cases,
                benchmark_version=system.benchmark_version,
            )
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
    completed = sum(record.status == "completed" for record in run.records)
    failed = len(run.records) - completed
    print(SAFETY_DISCLAIMER)
    print(
        f"{run.system} complete: {completed} completed, {failed} failed; "
        f"raw predictions: {output}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
