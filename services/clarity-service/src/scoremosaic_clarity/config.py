"""Environment-backed configuration for the private Clarity-OMR adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os
import re


class ConfigError(ValueError):
    """Raised when service configuration is invalid."""


_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    host: str
    port: int
    log_level: str
    compute_mode: str
    python_command: Path
    source_root: Path
    source_revision: str
    model_revision: str
    probe_timeout_seconds: int
    max_request_bytes: int
    max_pages: int
    max_image_pixels: int
    request_timeout_seconds: int
    pdf_dpi: int
    beam_width: int
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


def _absolute_non_root(values: Mapping[str, str], name: str, default: str) -> Path:
    path = Path(values.get(name, default))
    if not path.is_absolute() or path == Path("/"):
        raise ConfigError(f"{name} must be an absolute non-root path")
    return path


def _revision(values: Mapping[str, str], name: str, default: str) -> str:
    revision = values.get(name, default).strip().lower()
    if not _REVISION_RE.fullmatch(revision):
        raise ConfigError(f"{name} must be a 40-character lowercase commit revision")
    return revision


def load_config(environ: Mapping[str, str] | None = None) -> ServiceConfig:
    """Load bounded configuration without enabling an HTTP conversion route."""

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
    if compute_mode not in {"disabled", "cpu"}:
        raise ConfigError("SCOREMOSAIC_CLARITY_COMPUTE_MODE must be disabled or cpu")

    python_command = Path(
        values.get("SCOREMOSAIC_CLARITY_PYTHON_COMMAND", "/usr/local/bin/python")
    )
    if not python_command.is_absolute():
        raise ConfigError("SCOREMOSAIC_CLARITY_PYTHON_COMMAND must be absolute")

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
        python_command=python_command,
        source_root=_absolute_non_root(
            values,
            "SCOREMOSAIC_CLARITY_SOURCE_ROOT",
            "/opt/clarity",
        ),
        source_revision=_revision(
            values,
            "SCOREMOSAIC_CLARITY_SOURCE_REVISION",
            "c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82",
        ),
        model_revision=_revision(
            values,
            "SCOREMOSAIC_CLARITY_MODEL_REVISION",
            "ee14c1e41ab371fe27bf8a2707ea588560077e73",
        ),
        probe_timeout_seconds=_read_int(
            values,
            "SCOREMOSAIC_CLARITY_PROBE_TIMEOUT_SECONDS",
            90,
            minimum=1,
            maximum=300,
        ),
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
            1200,
            minimum=60,
            maximum=3600,
        ),
        pdf_dpi=_read_int(
            values,
            "SCOREMOSAIC_CLARITY_PDF_DPI",
            300,
            minimum=150,
            maximum=400,
        ),
        beam_width=_read_int(
            values,
            "SCOREMOSAIC_CLARITY_BEAM_WIDTH",
            2,
            minimum=1,
            maximum=5,
        ),
        workspace_root=_absolute_non_root(
            values,
            "SCOREMOSAIC_CLARITY_WORKSPACE_ROOT",
            "/tmp/scoremosaic-clarity",
        ),
    )
