"""Health-only HTTP foundation for the private ScoreMosaic OMR Gateway."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from typing import Any, Callable
from urllib.parse import urlsplit

from . import __version__
from .config import ConfigError, ServiceConfig, load_config
from .engine_client import ProbeResult, probe_engines
from .safe_intake import SAFE_INTAKE_MEDIA_TYPES

ACCEPTED_INPUT_FORMATS = SAFE_INTAKE_MEDIA_TYPES


@dataclass(frozen=True, slots=True)
class RouteResponse:
    status: int
    payload: dict[str, Any]
    allow: str | None = None


def _capabilities(config: ServiceConfig) -> dict[str, Any]:
    return {
        "acceptedInputFormats": list(ACCEPTED_INPUT_FORMATS),
        "uploadEnabled": False,
        "orchestrationEnabled": False,
        "orchestrationMode": config.orchestration_mode,
        "candidateIsolation": True,
    }


def _default_engine_states(config: ServiceConfig) -> dict[str, str]:
    return {endpoint.name: "not_ready" for endpoint in config.engine_endpoints}


def route_request(
    method: str,
    target: str,
    config: ServiceConfig,
    *,
    engine_states: dict[str, str] | None = None,
) -> RouteResponse:
    """Return deterministic status without accepting OMR input."""

    path = urlsplit(target).path
    states = (
        _default_engine_states(config)
        if engine_states is None
        else dict(engine_states)
    )

    if method == "GET" and path == "/health":
        return RouteResponse(
            status=200,
            payload={
                "service": "scoremosaic-omr-gateway",
                "version": __version__,
                "status": "ok",
                "gateway": "running",
                "capabilities": _capabilities(config),
                "engines": states,
            },
        )

    if method == "GET" and path == "/ready":
        return RouteResponse(
            status=503,
            payload={
                "service": "scoremosaic-omr-gateway",
                "version": __version__,
                "status": "not_ready",
                "reason": "orchestration_disabled",
                "capabilities": _capabilities(config),
                "engines": states,
            },
        )

    if method != "GET":
        return RouteResponse(
            status=405,
            payload={"error": "method_not_allowed"},
            allow="GET",
        )

    return RouteResponse(status=404, payload={"error": "not_found"})


ProbeFunction = Callable[
    [tuple[Any, ...], int],
    dict[str, ProbeResult],
]


def make_handler(
    config: ServiceConfig,
    probe: ProbeFunction = probe_engines,
) -> type[BaseHTTPRequestHandler]:
    """Create a handler bound to immutable private configuration."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "ScoreMosaicGateway"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802
            self._respond()

        def do_POST(self) -> None:  # noqa: N802
            self._respond()

        def do_PUT(self) -> None:  # noqa: N802
            self._respond()

        def do_PATCH(self) -> None:  # noqa: N802
            self._respond()

        def do_DELETE(self) -> None:  # noqa: N802
            self._respond()

        def _respond(self) -> None:
            safe_path = urlsplit(self.path).path
            states: dict[str, str] | None = None

            if self.command == "GET" and safe_path == "/ready":
                results = probe(
                    config.engine_endpoints,
                    config.probe_timeout_seconds,
                )
                states = {
                    name: result.status
                    for name, result in results.items()
                }

            response = route_request(
                self.command,
                self.path,
                config,
                engine_states=states,
            )
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
            # Avoid logging raw request targets or query strings.
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
                "service": "scoremosaic-omr-gateway",
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
