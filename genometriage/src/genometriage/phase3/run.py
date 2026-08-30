"""Run or resume deterministic GenomeTriage V3 conflict arbitration."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from genometriage import SAFETY_DISCLAIMER
from genometriage.baseline.runner import load_system_run, write_system_run
from genometriage.benchmark.loader import DEFAULT_CASES_PATH, load_cases
from genometriage.evidence import DEFAULT_EVIDENCE_PATH, DEFAULT_MANIFEST_PATH, EvidenceStore

from .runner import ConflictArbitrationSystem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--evidence-manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--v1-predictions",
        type=Path,
        default=Path("predictions/evidence-grounded-v1.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("predictions/conflict-arbitrated-v3.json"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cases = load_cases(args.cases)
    v1_run = load_system_run(args.v1_predictions)
    store = EvidenceStore.load(
        evidence_path=args.evidence,
        manifest_path=args.evidence_manifest,
        cases_path=args.cases,
    )
    system = ConflictArbitrationSystem(store, v1_run)
    resume_run = None
    if args.resume and args.output.is_file():
        resume_run = load_system_run(args.output)
        system.validate_resume_run(resume_run, cases_path=args.cases)
    run = system.run(
        cases,
        cases_path=args.cases,
        fail_fast=args.fail_fast,
        initial_records=resume_run.records if resume_run else (),
        created_at_utc=resume_run.created_at_utc if resume_run else None,
        checkpoint_callback=lambda checkpoint: write_system_run(checkpoint, args.output),
    )
    completed = sum(record.status == "completed" for record in run.records)
    failed = len(run.records) - completed
    print(SAFETY_DISCLAIMER)
    print(
        f"{run.system} complete: {completed} completed, {failed} failed; "
        f"raw predictions: {args.output}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
