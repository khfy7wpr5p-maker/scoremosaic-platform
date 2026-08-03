"""Environment-backed configuration for the private Audiveris adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os
import re


class ConfigError(ValueError):
    """Raised when service configuration is invalid."""


_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?$")


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    host: str
    port: int
    log_level: str
    runtime_mode: str
    audiveris_command: Path
    audiveris_version: str
    probe_timeout_seconds: int
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
    """Load bounded configuration without enabling an upload API."""

    values = os.environ if environ is None else environ

    host = values.get("SCOREMOSAIC_AUDIVERIS_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "0.0.0.0", "::1", "::"}:
        raise ConfigError(
            "SCOREMOSAIC_AUDIVERIS_HOST is not an approved bind address"
        )

    log_level = values.get(
        "SCOREMOSAIC_AUDIVERIS_LOG_LEVEL", "INFO"
    ).strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("SCOREMOSAIC_AUDIVERIS_LOG_LEVEL is invalid")

    runtime_mode = values.get(
        "SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE", "disabled"
    ).strip().lower()
    if runtime_mode not in {"disabled", "audiveris"}:
        raise ConfigError(
            "SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE must be disabled or audiveris"
        )

    command = Path(
        values.get("SCOREMOSAIC_AUDIVERIS_COMMAND", "/usr/bin/audiveris")
    )
    if not command.is_absolute():
        raise ConfigError("SCOREMOSAIC_AUDIVERIS_COMMAND must be absolute")

    audiveris_version = values.get(
        "SCOREMOSAIC_AUDIVERIS_VERSION", "5.11.0"
    ).strip()
    if not _VERSION_RE.fullmatch(audiveris_version):
        raise ConfigError("SCOREMOSAIC_AUDIVERIS_VERSION is invalid")

    workspace_root = Path(
        values.get(
            "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT",
            "/tmp/scoremosaic-audiveris",
        )
    )
    if not workspace_root.is_absolute() or workspace_root == Path("/"):
        raise ConfigError(
            "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT must be an absolute non-root path"
        )

    return ServiceConfig(
        host=host,
        port=_read_int(
            values,
            "SCOREMOSAIC_AUDIVERIS_PORT",
            8082,
            minimum=1024,
            maximum=65535,
        ),
        log_level=log_level,
        runtime_mode=runtime_mode,
        audiveris_command=command,
        audiveris_version=audiveris_version,
        probe_timeout_seconds=_read_int(
            values,
            "SCOREMOSAIC_AUDIVERIS_PROBE_TIMEOUT_SECONDS",
            20,
            minimum=1,
            maximum=120,
        ),
        max_request_bytes=_read_int(
            values,
            "SCOREMOSAIC_AUDIVERIS_MAX_REQUEST_BYTES",
            20 * 1024 * 1024,
            minimum=1024,
            maximum=100 * 1024 * 1024,
        ),
        max_pages=_read_int(
            values,
            "SCOREMOSAIC_AUDIVERIS_MAX_PAGES",
            40,
            minimum=1,
            maximum=200,
        ),
        max_image_pixels=_read_int(
            values,
            "SCOREMOSAIC_AUDIVERIS_MAX_IMAGE_PIXELS",
            80_000_000,
            minimum=1_000_000,
            maximum=200_000_000,
        ),
        request_timeout_seconds=_read_int(
            values,
            "SCOREMOSAIC_AUDIVERIS_REQUEST_TIMEOUT_SECONDS",
            600,
            minimum=30,
            maximum=1800,
        ),
        workspace_root=workspace_root,
    )
