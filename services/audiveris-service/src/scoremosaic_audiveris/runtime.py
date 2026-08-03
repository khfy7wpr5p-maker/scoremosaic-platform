"""Bounded Audiveris runtime probing and internal transcription helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import os
import re
import subprocess

from .config import ServiceConfig

_SUPPORTED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}
_AUDIVERIS_VERSION_RE = re.compile(
    r"(?im)^\s*-\s*Version:\s*"
    r"([0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?)\s*$"
)
_MAX_DIAGNOSTIC_CHARS = 16_384


class RuntimeExecutionError(RuntimeError):
    """Raised when a bounded Audiveris command cannot complete safely."""


@dataclass(frozen=True, slots=True)
class RuntimeProbe:
    ready: bool
    reason: str
    version: str | None
    java_runtime_enabled: bool
    diagnostic: str = ""


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    return_code: int
    musicxml_artifacts: tuple[Path, ...]
    omr_artifacts: tuple[Path, ...]
    diagnostic: str


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _runtime_environment(config: ServiceConfig) -> dict[str, str]:
    workspace = config.workspace_root
    home = workspace / "home"
    env = dict(os.environ)
    for dangerous_name in (
        "CLASSPATH",
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "_JAVA_OPTIONS",
    ):
        env.pop(dangerous_name, None)
    env.update(
        {
            "HOME": str(home),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TMPDIR": str(workspace / "tmp"),
            "TMP": str(workspace / "tmp"),
            "TEMP": str(workspace / "tmp"),
        }
    )
    return env


def _prepare_runtime_directories(config: ServiceConfig) -> None:
    workspace = config.workspace_root
    workspace.mkdir(parents=True, exist_ok=True)
    home = workspace / "home"
    for path in (
        home,
        home / ".cache",
        home / ".config",
        home / ".local" / "share",
        workspace / "tmp",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _diagnostic(stdout: str | None, stderr: str | None) -> str:
    combined = "\n".join(
        part.strip() for part in (stdout or "", stderr or "") if part.strip()
    )
    return combined[:_MAX_DIAGNOSTIC_CHARS]


def probe_runtime(
    config: ServiceConfig,
    *,
    runner: Runner = subprocess.run,
) -> RuntimeProbe:
    """Run the pinned version command without client-controlled arguments."""

    if config.runtime_mode != "audiveris":
        return RuntimeProbe(False, "audiveris_runtime_disabled", None, False)
    if not config.audiveris_command.is_file() or not os.access(
        config.audiveris_command, os.X_OK
    ):
        return RuntimeProbe(False, "audiveris_command_unavailable", None, False)

    _prepare_runtime_directories(config)
    try:
        completed = runner(
            [str(config.audiveris_command), "-version"],
            cwd=config.workspace_root,
            env=_runtime_environment(config),
            capture_output=True,
            text=True,
            timeout=config.probe_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return RuntimeProbe(False, "audiveris_probe_timed_out", None, False)
    except OSError as exc:
        return RuntimeProbe(
            False,
            "audiveris_probe_failed",
            None,
            False,
            str(exc)[:_MAX_DIAGNOSTIC_CHARS],
        )

    output = _diagnostic(completed.stdout, completed.stderr)
    match = _AUDIVERIS_VERSION_RE.search(output)
    version = match.group(1) if match else None
    if completed.returncode != 0:
        return RuntimeProbe(
            False,
            "audiveris_probe_nonzero_exit",
            version,
            False,
            output,
        )
    if version != config.audiveris_version:
        return RuntimeProbe(
            False,
            "audiveris_version_mismatch",
            version,
            False,
            output,
        )
    return RuntimeProbe(True, "ready", version, True, output)


def _resolved_workspace(config: ServiceConfig) -> Path:
    _prepare_runtime_directories(config)
    return config.workspace_root.resolve(strict=True)


def _require_inside_workspace(path: Path, workspace: Path, *, strict: bool) -> Path:
    resolved = path.resolve(strict=strict)
    if not resolved.is_relative_to(workspace):
        raise RuntimeExecutionError("path escapes the Audiveris workspace")
    return resolved


def build_transcription_command(
    input_path: Path,
    output_dir: Path,
    config: ServiceConfig,
) -> tuple[str, ...]:
    """Build a fixed CLI command with no client-supplied Audiveris options."""

    workspace = _resolved_workspace(config)
    if input_path.is_symlink():
        raise RuntimeExecutionError("symbolic-link input is not allowed")
    safe_input = _require_inside_workspace(input_path, workspace, strict=True)
    if not safe_input.is_file():
        raise RuntimeExecutionError("input is not a regular file")
    if safe_input.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise RuntimeExecutionError("unsupported Audiveris input suffix")

    safe_output = _require_inside_workspace(output_dir, workspace, strict=False)
    safe_output.mkdir(parents=True, exist_ok=True)
    if safe_output.is_symlink():
        raise RuntimeExecutionError("symbolic-link output is not allowed")

    return (
        str(config.audiveris_command),
        "-batch",
        "-transcribe",
        "-export",
        "-save",
        "-swap",
        "-output",
        str(safe_output),
        "--",
        str(safe_input),
    )


def transcribe_file(
    input_path: Path,
    output_dir: Path,
    config: ServiceConfig,
    *,
    runner: Runner = subprocess.run,
) -> TranscriptionResult:
    """Execute one private, bounded transcription inside the workspace."""

    probe = probe_runtime(config, runner=runner)
    if not probe.ready:
        raise RuntimeExecutionError(
            f"{probe.reason}:{probe.diagnostic}" if probe.diagnostic else probe.reason
        )

    command = build_transcription_command(input_path, output_dir, config)
    try:
        completed = runner(
            list(command),
            cwd=config.workspace_root,
            env=_runtime_environment(config),
            capture_output=True,
            text=True,
            timeout=config.request_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeExecutionError("audiveris_transcription_timed_out") from exc
    except OSError as exc:
        raise RuntimeExecutionError("audiveris_transcription_failed_to_start") from exc

    diagnostic = _diagnostic(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        raise RuntimeExecutionError(
            f"audiveris_transcription_nonzero_exit:{completed.returncode}:{diagnostic}"
        )

    output_root = Path(command[command.index("-output") + 1])
    musicxml = tuple(sorted(output_root.rglob("*.mxl")))
    omr = tuple(sorted(output_root.rglob("*.omr")))
    if not musicxml:
        raise RuntimeExecutionError(f"audiveris_musicxml_not_created:{diagnostic}")
    return TranscriptionResult(completed.returncode, musicxml, omr, diagnostic)
