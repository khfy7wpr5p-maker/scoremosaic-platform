"""Environment-backed configuration for the Clarity service foundation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os


class ConfigError(ValueError):
    """Raised when service configuration is invalid."""


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    host: str
    port: int
    log_level: str
    compute_mode: str
    max_request_bytes: int
    max_pages: int
    max_image_pixels: int
    request_timeout_seconds: int
    workspace_root: Path


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


def load_config(environ: Mapping[str, str] | None = None) -> ServiceConfig:
    """Load bounded non-secret configuration without enabling inference."""

    values = os.environ if environ is None else environ

    host = values.get("SCOREMOSAIC_CLARITY_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "0.0.0.0", "::1", "::"}:
        raise ConfigError("SCOREMOSAIC_CLARITY_HOST is not an approved bind address")

    log_level = values.get("SCOREMOSAIC_CLARITY_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("SCOREMOSAIC_CLARITY_LOG_LEVEL is invalid")

    compute_mode = values.get(
        "SCOREMOSAIC_CLARITY_COMPUTE_MODE", "disabled"
    ).strip().lower()
    if compute_mode != "disabled":
        raise ConfigError(
            "SCOREMOSAIC_CLARITY_COMPUTE_MODE must remain disabled in the foundation"
        )

    workspace_root = Path(
        values.get("SCOREMOSAIC_CLARITY_WORKSPACE_ROOT", "/tmp/scoremosaic-clarity")
    )
    if not workspace_root.is_absolute():
        raise ConfigError("SCOREMOSAIC_CLARITY_WORKSPACE_ROOT must be absolute")

    return ServiceConfig(
        host=host,
        port=_read_int(
            values,
            "SCOREMOSAIC_CLARITY_PORT",
            8081,
            minimum=1024,
            maximum=65535,
        ),
        log_level=log_level,
        compute_mode=compute_mode,
        max_request_bytes=_read_int(
            values,
            "SCOREMOSAIC_CLARITY_MAX_REQUEST_BYTES",
            20 * 1024 * 1024,
            minimum=1024,
            maximum=100 * 1024 * 1024,
        ),
        max_pages=_read_int(
            values,
            "SCOREMOSAIC_CLARITY_MAX_PAGES",
            40,
            minimum=1,
            maximum=200,
        ),
        max_image_pixels=_read_int(
            values,
            "SCOREMOSAIC_CLARITY_MAX_IMAGE_PIXELS",
            80_000_000,
            minimum=1_000_000,
            maximum=200_000_000,
        ),
        request_timeout_seconds=_read_int(
            values,
            "SCOREMOSAIC_CLARITY_REQUEST_TIMEOUT_SECONDS",
            180,
            minimum=1,
            maximum=900,
        ),
        workspace_root=workspace_root,
    )
