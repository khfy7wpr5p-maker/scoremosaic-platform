"""Private HTTP health and readiness adapter for the HOMR runtime."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from typing import Any, Callable
from urllib.parse import urlsplit

from . import __version__
from .config import ConfigError, ServiceConfig, load_config
from .runtime import MODEL_SPECS, RuntimeProbe, probe_runtime


@dataclass(frozen=True, slots=True)
class RouteResponse:
    status: int
    payload: dict[str, Any]
    allow: str | None = None


RuntimeProbeCallable = Callable[[ServiceConfig], RuntimeProbe]
_SAFE_NOT_READY_REASONS = frozenset(
    {
        "homr_runtime_disabled",
        "homr_command_unavailable",
        "homr_package_unavailable",
        "homr_package_probe_failed",
        "homr_version_mismatch",
        "homr_model_unavailable",
        "homr_model_checksum_mismatch",
        "homr_probe_timed_out",
        "homr_probe_failed",
        "homr_probe_nonzero_exit",
    }
)


def _safe_not_ready_reason(reason: str) -> str:
    code = reason.partition(":")[0]
    if code in _SAFE_NOT_READY_REASONS:
        return code
    return "homr_runtime_not_ready"


def _capabilities(config: ServiceConfig) -> dict[str, Any]:
    return {
        "acceptedInputFormats": ["image/jpeg", "image/png"],
        "runtimeMode": config.runtime_mode,
        "internalRuntimeEnabled": config.runtime_mode == "homr",
        "uploadEnabled": False,
        "conversionEnabled": False,
    }


def route_request(
    method: str,
    target: str,
    config: ServiceConfig,
    *,
    runtime_probe: RuntimeProbeCallable = probe_runtime,
) -> RouteResponse:
    """Return deterministic private status responses without accepting OMR input."""

    path = urlsplit(target).path
    if method == "GET" and path == "/health":
        return RouteResponse(
            status=200,
            payload={
                "service": "scoremosaic-homr-service",
                "version": __version__,
                "status": "ok",
                "engine": {
                    "name": "homr",
                    "installed": config.runtime_mode == "homr",
                    "expectedVersion": config.homr_version,
                    "expectedModels": len(MODEL_SPECS),
                    "computeMode": "cpu",
                },
                "capabilities": _capabilities(config),
            },
        )

    if method == "GET" and path == "/ready":
        probe = runtime_probe(config)
        ready = (
            probe.ready
            and probe.reason == "ready"
            and probe.version == config.homr_version
            and probe.verified_models == len(MODEL_SPECS)
        )
        return RouteResponse(
            status=200 if ready else 503,
            payload={
                "service": "scoremosaic-homr-service",
                "version": __version__,
                "status": "ready" if ready else "not_ready",
                "reason": (
                    "ready" if ready else _safe_not_ready_reason(probe.reason)
                ),
                "engine": {
                    "name": "homr",
                    "version": config.homr_version if ready else None,
                    "verifiedModels": len(MODEL_SPECS) if ready else 0,
                    "computeMode": "cpu",
                },
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
        server_version = "ScoreMosaicHOMR"
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
                "service": "scoremosaic-homr-service",
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
