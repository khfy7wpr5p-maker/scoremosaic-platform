from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final

from . import PHASE, SERVICE_NAME, __version__
from .model_guard import disabled_model_evidence
from .offline_fixture_inference import disabled_fixture_inference_evidence
from .runtime import runtime_evidence

HOST: Final = "0.0.0.0"
DEFAULT_PORT: Final = 8080


def health_payload() -> dict[str, object]:
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "phase": PHASE,
        "version": __version__,
        "runtime": runtime_evidence(),
        "modelValidation": disabled_model_evidence(),
        "offlineFixtureInference": disabled_fixture_inference_evidence(),
    }


def readiness_payload() -> dict[str, object]:
    return {
        "status": "not_ready",
        "service": SERVICE_NAME,
        "phase": PHASE,
        "modelLoaded": False,
        "inferenceEnabled": False,
        "reason": "production_inference_disabled",
    }


class HealthOnlyHandler(BaseHTTPRequestHandler):
    server_version = "ScoreMosaicSTOMR/0.4"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, health_payload())
            return
        if self.path == "/ready":
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, readiness_payload())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"status": "not_found", "service": SERVICE_NAME})

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _method_not_allowed(self) -> None:
        self._send_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"status": "method_not_allowed", "service": SERVICE_NAME, "allowedMethods": ["GET"]},
            extra_headers={"Allow": "GET"},
        )

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, object],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port_text = os.environ.get("ST_OMR_PORT", str(DEFAULT_PORT))
    try:
        port = int(port_text)
    except ValueError as exc:
        raise SystemExit("ST_OMR_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("ST_OMR_PORT must be between 1 and 65535")

    runtime_evidence()
    server = ThreadingHTTPServer((HOST, port), HealthOnlyHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
