"""Environment-backed configuration for the OMR Gateway foundation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit
import os


class ConfigError(ValueError):
    """Raised when gateway configuration is invalid."""


@dataclass(frozen=True, slots=True)
class EngineEndpoint:
    name: str
    base_url: str


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    host: str
    port: int
    log_level: str
    orchestration_mode: str
    probe_timeout_seconds: int
    max_request_bytes: int
    max_pages: int
    max_image_pixels: int
    workspace_root: Path
    engine_endpoints: tuple[EngineEndpoint, ...]


def _read_int(
    environ: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = environ.get(name, str(default)).strip()
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return value


def _read_fixed_int(
    environ: Mapping[str, str],
    name: str,
    required: int,
) -> int:
    raw = environ.get(name, str(required)).strip()
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value != required:
        raise ConfigError(f"{name} must equal {required}")
    return value


def _read_base_url(
    environ: Mapping[str, str],
    name: str,
    default: str,
) -> str:
    raw = environ.get(name, default).strip()
    parsed = urlsplit(raw)

    if parsed.scheme not in {"http", "https"}:
        raise ConfigError(f"{name} must use http or https")
    if not parsed.hostname:
        raise ConfigError(f"{name} must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError(f"{name} must not include credentials")
    if parsed.query or parsed.fragment:
        raise ConfigError(f"{name} must not include a query or fragment")
    if parsed.path not in {"", "/"}:
        raise ConfigError(f"{name} must not include a path")
    try:
        parsed.port
    except ValueError as exc:
        raise ConfigError(f"{name} contains an invalid port") from exc

    return raw.rstrip("/")


def load_config(environ: Mapping[str, str] | None = None) -> ServiceConfig:
    """Load bounded private configuration without enabling orchestration."""

    values = os.environ if environ is None else environ

    host = values.get("SCOREMOSAIC_GATEWAY_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "0.0.0.0", "::1", "::"}:
        raise ConfigError("SCOREMOSAIC_GATEWAY_HOST is not an approved bind address")

    log_level = values.get("SCOREMOSAIC_GATEWAY_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("SCOREMOSAIC_GATEWAY_LOG_LEVEL is invalid")

    orchestration_mode = values.get(
        "SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE", "disabled"
    ).strip().lower()
    if orchestration_mode != "disabled":
        raise ConfigError(
            "SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE must remain disabled "
            "in the foundation"
        )

    workspace_root = Path(
        values.get(
            "SCOREMOSAIC_GATEWAY_WORKSPACE_ROOT",
            "/tmp/scoremosaic-gateway",
        )
    )
    if not workspace_root.is_absolute():
        raise ConfigError("SCOREMOSAIC_GATEWAY_WORKSPACE_ROOT must be absolute")

    endpoints = (
        EngineEndpoint(
            "audiveris",
            _read_base_url(
                values,
                "SCOREMOSAIC_GATEWAY_AUDIVERIS_BASE_URL",
                "http://audiveris-foundation:8082",
            ),
        ),
        EngineEndpoint(
            "homr",
            _read_base_url(
                values,
                "SCOREMOSAIC_GATEWAY_HOMR_BASE_URL",
                "http://homr-foundation:8080",
            ),
        ),
        EngineEndpoint(
            "clarity",
            _read_base_url(
                values,
                "SCOREMOSAIC_GATEWAY_CLARITY_BASE_URL",
                "http://clarity-foundation:8081",
            ),
        ),
    )

    return ServiceConfig(
        host=host,
        port=_read_int(
            values,
            "SCOREMOSAIC_GATEWAY_PORT",
            8090,
            minimum=1024,
            maximum=65535,
        ),
        log_level=log_level,
        orchestration_mode=orchestration_mode,
        probe_timeout_seconds=_read_int(
            values,
            "SCOREMOSAIC_GATEWAY_PROBE_TIMEOUT_SECONDS",
            1,
            minimum=1,
            maximum=10,
        ),
        max_request_bytes=_read_int(
            values,
            "SCOREMOSAIC_GATEWAY_MAX_REQUEST_BYTES",
            20 * 1024 * 1024,
            minimum=1024,
            maximum=100 * 1024 * 1024,
        ),
        max_pages=_read_int(
            values,
            "SCOREMOSAIC_GATEWAY_MAX_PAGES",
            40,
            minimum=1,
            maximum=200,
        ),
        max_image_pixels=_read_fixed_int(
            values,
            "SCOREMOSAIC_GATEWAY_MAX_IMAGE_PIXELS",
            40_000_000,
        ),
        workspace_root=workspace_root,
        engine_endpoints=endpoints,
    )
