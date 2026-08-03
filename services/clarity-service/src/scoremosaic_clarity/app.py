"""Health-only HTTP foundation for the private Clarity-OMR adapter service."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from typing import Any
from urllib.parse import urlsplit

from . import __version__
from .config import ConfigError, ServiceConfig, load_config

ACCEPTED_INPUT_FORMATS = (
    "application/pdf",
    "image/jpeg",
    "image/png",
)


@dataclass(frozen=True, slots=True)
class RouteResponse:
    status: int
    payload: dict[str, Any]
    allow: str | None = None


def _capabilities(config: ServiceConfig) -> dict[str, Any]:
    return {
        "acceptedInputFormats": list(ACCEPTED_INPUT_FORMATS),
        "computeMode": config.compute_mode,
        "uploadEnabled": False,
        "conversionEnabled": False,
    }


def route_request(method: str, target: str, config: ServiceConfig) -> RouteResponse:
    """Return deterministic status responses without accepting OMR input."""

    path = urlsplit(target).path
    if method == "GET" and path == "/health":
        return RouteResponse(
            status=200,
            payload={
                "service": "scoremosaic-clarity-service",
                "version": __version__,
                "status": "ok",
                "engine": {
                    "name": "clarity-omr",
                    "installed": False,
                    "modelInstalled": False,
                },
                "capabilities": _capabilities(config),
            },
        )

    if method == "GET" and path == "/ready":
        return RouteResponse(
            status=503,
            payload={
                "service": "scoremosaic-clarity-service",
                "version": __version__,
                "status": "not_ready",
                "reason": "clarity_engine_not_installed",
                "capabilities": _capabilities(config),
            },
        )

    if method != "GET":
        return RouteResponse(
            status=405,
            payload={"error": "method_not_allowed"},
            allow="GET",
        )

    return RouteResponse(status=404, payload={"error": "not_found"})


def make_handler(config: ServiceConfig) -> type[BaseHTTPRequestHandler]:
    """Create a request handler bound to validated immutable configuration."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "ScoreMosaicClarity"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            self._respond()

        def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            self._respond()

        def do_PUT(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            self._respond()

        def do_PATCH(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            self._respond()

        def do_DELETE(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            self._respond()

        def _respond(self) -> None:
            response = route_request(self.command, self.path, config)
            body = json.dumps(
                response.payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")

            self.send_response(response.status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if response.allow is not None:
                self.send_header("Allow", response.allow)
            self.end_headers()
            self.wfile.write(body)

            safe_path = urlsplit(self.path).path
            print(
                json.dumps(
                    {
                        "event": "http_access",
                        "method": self.command,
                        "path": safe_path,
                        "status": response.status,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )

        def log_message(self, format: str, *args: object) -> None:
            # Avoid BaseHTTPRequestHandler logging raw request targets or queries.
            return

    return Handler


def run(config: ServiceConfig | None = None) -> None:
    service_config = load_config() if config is None else config
    server = ThreadingHTTPServer(
        (service_config.host, service_config.port),
        make_handler(service_config),
    )
    print(
        json.dumps(
            {
                "event": "service_started",
                "host": service_config.host,
                "port": service_config.port,
                "service": "scoremosaic-clarity-service",
                "version": __version__,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )
    server.serve_forever()


def main() -> int:
    try:
        run()
    except ConfigError as exc:
        print(f"configuration_error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
