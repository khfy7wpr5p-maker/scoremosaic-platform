"""Environment-backed configuration for the HOMR service foundation."""

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
    max_request_bytes: int
    max_pages: int
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
    """Load and validate non-secret configuration without logging raw values."""

    values = os.environ if environ is None else environ

    host = values.get("SCOREMOSAIC_HOMR_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "0.0.0.0", "::1", "::"}:
        raise ConfigError("SCOREMOSAIC_HOMR_HOST is not an approved bind address")

    log_level = values.get("SCOREMOSAIC_HOMR_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("SCOREMOSAIC_HOMR_LOG_LEVEL is invalid")

    workspace_root = Path(
        values.get("SCOREMOSAIC_HOMR_WORKSPACE_ROOT", "/tmp/scoremosaic-homr")
    )
    if not workspace_root.is_absolute():
        raise ConfigError("SCOREMOSAIC_HOMR_WORKSPACE_ROOT must be absolute")

    return ServiceConfig(
        host=host,
        port=_read_int(
            values,
            "SCOREMOSAIC_HOMR_PORT",
            8080,
            minimum=1024,
            maximum=65535,
        ),
        log_level=log_level,
        max_request_bytes=_read_int(
            values,
            "SCOREMOSAIC_HOMR_MAX_REQUEST_BYTES",
            20 * 1024 * 1024,
            minimum=1024,
            maximum=100 * 1024 * 1024,
        ),
        max_pages=_read_int(
            values,
            "SCOREMOSAIC_HOMR_MAX_PAGES",
            40,
            minimum=1,
            maximum=200,
        ),
        request_timeout_seconds=_read_int(
            values,
            "SCOREMOSAIC_HOMR_REQUEST_TIMEOUT_SECONDS",
            120,
            minimum=1,
            maximum=900,
        ),
        workspace_root=workspace_root,
    )
