"""Minimal local HTTP server for the GenomeTriage judge application."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Type
from urllib.parse import parse_qs, urlparse

from genometriage import SAFETY_DISCLAIMER

from .repository import DemoRepository, DemoRepositoryError


STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 256 * 1024
STATIC_FILES: Dict[str, tuple[str, str]] = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class JudgeAppHandler(BaseHTTPRequestHandler):
    repository: DemoRepository
    server_version = "GenomeTriageJudge/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path in STATIC_FILES:
            self._serve_static(parsed.path)
            return
        if parsed.path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "default_system": "evidence-grounded-v1",
                    "execution_mode": "recorded_replay",
                    "safety_disclaimer": SAFETY_DISCLAIMER,
                },
            )
            return
        if parsed.path == "/api/catalog":
            self._send_json(HTTPStatus.OK, self.repository.catalog())
            return
        if parsed.path == "/api/dashboard":
            self._send_json(HTTPStatus.OK, self.repository.dashboard())
            return
        if parsed.path == "/api/journey":
            self._send_json(HTTPStatus.OK, self.repository.journey())
            return
        if parsed.path == "/api/case":
            query = parse_qs(parsed.query)
            track = query.get("track", [""])[0]
            case_id = query.get("case_id", [""])[0]
            try:
                payload = self.repository.case_payload(track, case_id)
            except DemoRepositoryError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "route not found")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path != "/api/inspect":
            self._send_error_json(HTTPStatus.NOT_FOUND, "route not found")
            return
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
            return
        if length < 1 or length > MAX_REQUEST_BYTES:
            self._send_error_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"request must contain 1–{MAX_REQUEST_BYTES} bytes",
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            input_format = payload.get("format")
            content = payload.get("content")
            if input_format == "case_json":
                result = self.repository.inspect_case(content)
            elif input_format == "vcf":
                result = self.repository.inspect_vcf(
                    content, genome_build=str(payload.get("genome_build", "GRCh38"))
                )
            else:
                raise DemoRepositoryError("format must be 'case_json' or 'vcf'")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, f"malformed request JSON: {exc}")
            return
        except DemoRepositoryError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json(HTTPStatus.OK, result)

    def _serve_static(self, route: str) -> None:
        filename, content_type = STATIC_FILES[route]
        try:
            content = (STATIC_DIR / filename).read_bytes()
        except OSError:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "static asset missing")
            return
        self.send_response(HTTPStatus.OK)
        self._security_headers(content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: HTTPStatus, payload: object) -> None:
        content = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self._security_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json(
            status,
            {"error": message, "safety_disclaimer": SAFETY_DISCLAIMER},
        )

    def _security_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def make_handler(repository: DemoRepository) -> Type[JudgeAppHandler]:
    class BoundJudgeAppHandler(JudgeAppHandler):
        pass

    BoundJudgeAppHandler.repository = repository
    return BoundJudgeAppHandler


def create_server(
    *, host: str = "127.0.0.1", port: int = 8765, repository: Optional[DemoRepository] = None
) -> ThreadingHTTPServer:
    repo = repository or DemoRepository()
    return ThreadingHTTPServer((host, port), make_handler(repo))
