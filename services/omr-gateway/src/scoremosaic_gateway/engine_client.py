"""Bounded readiness probes for private OMR engine services."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import EngineEndpoint

MAX_PROBE_BODY_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class ProbeResult:
    engine: str
    status: str
    http_status: int | None
    reason: str


def _read_json_body(response: Any) -> dict[str, object]:
    body = response.read(MAX_PROBE_BODY_BYTES + 1)
    if len(body) > MAX_PROBE_BODY_BYTES:
        raise ValueError("probe response too large")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("probe response must be an object")
    return payload


def probe_engine(
    endpoint: EngineEndpoint,
    timeout_seconds: int,
    *,
    opener: Callable[..., Any] = urlopen,
) -> ProbeResult:
    """Probe one private engine readiness endpoint with a strict timeout."""

    request = Request(
        f"{endpoint.base_url}/ready",
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "ScoreMosaicGateway/0.1",
        },
    )

    try:
        response = opener(request, timeout=timeout_seconds)
        with response:
            status_code = int(getattr(response, "status", 200))
            _read_json_body(response)
    except HTTPError as exc:
        if exc.code == 503:
            return ProbeResult(endpoint.name, "not_ready", 503, "engine_not_ready")
        return ProbeResult(
            endpoint.name,
            "unavailable",
            exc.code,
            "unexpected_http_status",
        )
    except (URLError, TimeoutError, socket.timeout, OSError):
        return ProbeResult(endpoint.name, "unavailable", None, "connection_failed")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return ProbeResult(endpoint.name, "invalid_response", None, "invalid_response")

    if status_code == 200:
        return ProbeResult(endpoint.name, "ready", 200, "ready")
    return ProbeResult(
        endpoint.name,
        "unavailable",
        status_code,
        "unexpected_http_status",
    )


def probe_engines(
    endpoints: Iterable[EngineEndpoint],
    timeout_seconds: int,
    *,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, ProbeResult]:
    """Probe each engine independently so one failure is isolated."""

    return {
        endpoint.name: probe_engine(
            endpoint,
            timeout_seconds,
            opener=opener,
        )
        for endpoint in endpoints
    }
