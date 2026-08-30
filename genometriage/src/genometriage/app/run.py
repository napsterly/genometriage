"""Launch or smoke-test the offline GenomeTriage judge application."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from genometriage import SAFETY_DISCLAIMER

from .repository import DemoRepository, REPLAY_LABEL
from .server import create_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Validate retained app artifacts and exit without starting a server",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repository = DemoRepository()
    if args.smoke_test:
        catalog = repository.catalog()
        case = repository.case_payload(catalog["default_track"], catalog["default_case"])
        dashboard = repository.dashboard()
        print(SAFETY_DISCLAIMER)
        print(REPLAY_LABEL)
        print(
            "Offline demo smoke test passed: "
            f"{len(catalog['tracks'])} tracks; default={case['case']['case_id']}; "
            f"V1 false positives={dashboard['systems']['v1']['false_positives']}"
        )
        return 0

    server = create_server(host=args.host, port=args.port, repository=repository)
    actual_host, actual_port = server.server_address[:2]
    print(SAFETY_DISCLAIMER)
    print(REPLAY_LABEL)
    print(f"GenomeTriage Judge Mode: http://{actual_host}:{actual_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
