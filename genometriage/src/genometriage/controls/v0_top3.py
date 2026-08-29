"""Create a no-model V0 control by truncating retained rankings to top three."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from genometriage import SAFETY_DISCLAIMER
from genometriage.baseline.runner import load_system_run, write_system_run
from genometriage.benchmark.loader import file_sha256
from genometriage.models.schema import (
    CaseRunRecord,
    Prediction,
    RankedVariant,
    SystemRun,
)


CONTROL_SYSTEM = "v0-top3-control"
CONTROL_VERSION = "deterministic_v0_top3_control_v1"
DEFAULT_SOURCE = Path("predictions/baseline-gemini.json")
DEFAULT_OUTPUT = Path("predictions/v0-top3-control.json")
FROZEN_V0_SHA256 = "2fb210d21adcda3e2377a79ab0f8a238ab29469fa3fc6da5fe991d5e636d116e"


def _truncate_prediction(prediction: Prediction) -> Prediction:
    ranked = [
        RankedVariant.parse_obj({**item.dict(), "rank": index})
        for index, item in enumerate(prediction.ranked_variants[:3], start=1)
    ]
    notes = (
        "Deterministic top-3 control derived from the retained frozen V0 prediction. "
        "No model call was made."
    )
    if prediction.notes:
        notes = f"{notes} Source notes: {prediction.notes}"
    payload = prediction.dict()
    payload.update(
        {
            "system": CONTROL_SYSTEM,
            "prompt_version": CONTROL_VERSION,
            "ranked_variants": [item.dict() for item in ranked],
            "notes": notes,
        }
    )
    return Prediction.parse_obj(payload)


def build_v0_top3_control(
    source_run: SystemRun,
    *,
    source_sha256: str,
    source_artifact: str = "predictions/baseline-gemini.json",
) -> SystemRun:
    """Transform a completed frozen V0 run without mutating or resampling it."""

    if source_sha256 != FROZEN_V0_SHA256:
        raise ValueError("source prediction hash does not match frozen V0")
    if source_run.run_status != "completed":
        raise ValueError("V0 top-3 control requires a completed source run")
    if source_run.system != "baseline-gemini":
        raise ValueError("V0 top-3 control requires the frozen baseline-gemini run")

    records = []
    for record in source_run.records:
        if record.status == "completed" and record.prediction is not None:
            records.append(
                CaseRunRecord(
                    case_id=record.case_id,
                    status="completed",
                    prediction=_truncate_prediction(record.prediction),
                )
            )
        else:
            records.append(record.copy(deep=True))
    return SystemRun(
        run_status="completed",
        system=CONTROL_SYSTEM,
        benchmark_version=source_run.benchmark_version,
        prompt_version=CONTROL_VERSION,
        model=source_run.model,
        created_at_utc=source_run.created_at_utc,
        benchmark_sha256=source_run.benchmark_sha256,
        prompt_sha256=source_run.prompt_sha256,
        execution_config={
            "control": CONTROL_VERSION,
            "max_ranked_variants": 3,
            "no_model_calls": True,
            "source_artifact": source_artifact,
            "source_run_sha256": source_sha256,
            "source_execution_config": source_run.execution_config,
        },
        records=records,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    source_hash = file_sha256(args.source)
    control = build_v0_top3_control(
        load_system_run(args.source),
        source_sha256=source_hash,
        source_artifact=args.source.as_posix(),
    )
    write_system_run(control, args.output)
    print(SAFETY_DISCLAIMER)
    print(
        f"V0 top-3 control created from frozen sha256={source_hash}; "
        f"no model calls; output: {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
