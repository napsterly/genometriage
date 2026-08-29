"""CLI for reproducibly rebuilding the frozen synthetic evidence snapshot."""

from __future__ import annotations

from genometriage.evidence.store import build_evidence_snapshot


def main() -> int:
    manifest = build_evidence_snapshot()
    print(
        f"Built {manifest.snapshot_version}: {manifest.record_count} records; "
        f"sha256={manifest.evidence_file_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
