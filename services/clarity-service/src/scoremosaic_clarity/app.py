"""Private health, readiness, and authenticated receiver service for Clarity-OMR."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from typing import Any, Callable
from urllib.parse import urlsplit

from . import __version__
from .config import ConfigError, ServiceConfig, load_config
from .receiver_http import (
    ReceiverHttpContext,
    is_receiver_target,
    read_and_handle_receiver_http,
)
from .runtime import RuntimeProbe, probe_runtime

ACCEPTED_INPUT_FORMATS = ("application/pdf",)
Probe = Callable[[ServiceConfig], RuntimeProbe]
_PINNED_TORCH_VERSION = "2.13.0+cpu"
_EXPECTED_MODELS = 2
_SAFE_NOT_READY_REASONS = frozenset(
    {
        "clarity_runtime_disabled",
        "clarity_python_unavailable",
        "clarity_source_unavailable",
        "clarity_source_revision_unavailable",
        "clarity_source_revision_mismatch",
        "clarity_entrypoint_unavailable",
        "clarity_model_unavailable",
        "clarity_model_checksum_mismatch",
        "clarity_probe_timed_out",
        "clarity_probe_failed",
        "clarity_probe_nonzero_exit",
        "clarity_probe_invalid_output",
        "clarity_torch_version_mismatch",
        "clarity_cpu_mode_not_enforced",
    }
)


def _safe_not_ready_reason(reason: str) -> str:
    code = reason.partition(":")[0]
    if code in _SAFE_NOT_READY_REASONS:
        return code
    return "clarity_runtime_not_ready"


@dataclass(frozen=True, slots=True)
class RouteResponse:
    status: int
    payload: dict[str, Any]
    allow: str | None = None


def _capabilities(config: ServiceConfig) -> dict[str, Any]:
    return {
        "acceptedInputFormats": list(ACCEPTED_INPUT_FORMATS),
        "computeMode": config.compute_mode,
        "nativePdfOnly": True,
        "uploadEnabled": False,
        "conversionEnabled": False,
    }


def route_request(
    method: str,
    target: str,
    config: ServiceConfig,
    *,
    probe: Probe = probe_runtime,
) -> RouteResponse:
    """Return deterministic status responses without accepting public OMR input."""

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
                    "installed": config.compute_mode == "cpu",
                    "sourceRevision": config.source_revision,
                    "modelRevision": config.model_revision,
                    "expectedModels": 2,
                    "computeMode": config.compute_mode,
                },
                "capabilities": _capabilities(config),
            },
        )

    if method == "GET" and path == "/ready":
        runtime = probe(config)
        ready = (
            runtime.ready
            and runtime.reason == "ready"
            and runtime.source_revision == config.source_revision
            and runtime.model_revision == config.model_revision
            and runtime.verified_models == _EXPECTED_MODELS
            and runtime.torch_version == _PINNED_TORCH_VERSION
        )
        payload = {
            "service": "scoremosaic-clarity-service",
            "version": __version__,
            "status": "ready" if ready else "not_ready",
            "reason": (
                "ready" if ready else _safe_not_ready_reason(runtime.reason)
            ),
            "engine": {
                "sourceRevision": config.source_revision if ready else None,
                "modelRevision": config.model_revision if ready else None,
                "verifiedModels": _EXPECTED_MODELS if ready else 0,
                "torchVersion": _PINNED_TORCH_VERSION if ready else None,
                "computeMode": config.compute_mode,
            },
            "capabilities": _capabilities(config),
        }
        return RouteResponse(status=200 if ready else 503, payload=payload)

    if method != "GET":
        return RouteResponse(
            status=405,
            payload={"error": "method_not_allowed"},
            allow="GET",
        )

    return RouteResponse(status=404, payload={"error": "not_found"})


def make_handler(
    config: ServiceConfig,
    *,
    receiver_context: ReceiverHttpContext | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Create a handler with fail-closed authenticated internal receiver routes."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "ScoreMosaicClarity"
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
            if is_receiver_target(self.path):
                response = read_and_handle_receiver_http(
                    self,
                    context=receiver_context,
                )
                self.close_connection = True
            else:
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


def run(
    config: ServiceConfig | None = None,
    *,
    receiver_context: ReceiverHttpContext | None = None,
) -> None:
    service_config = load_config() if config is None else config
    server = ThreadingHTTPServer(
        (service_config.host, service_config.port),
        make_handler(service_config, receiver_context=receiver_context),
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
