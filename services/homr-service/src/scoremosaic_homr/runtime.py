"""Bounded HOMR runtime probing and private transcription helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib import metadata, util
from pathlib import Path
from typing import Callable, Iterable
import os
import subprocess
import xml.etree.ElementTree as ET

from .config import ServiceConfig

_SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}
_MAX_DIAGNOSTIC_CHARS = 16_384


class RuntimeExecutionError(RuntimeError):
    """Raised when a bounded HOMR command cannot complete safely."""


@dataclass(frozen=True, slots=True)
class ModelSpec:
    relative_path: str
    sha256: str


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        "segmentation/segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f.onnx",
        "6ed36640db4ef5d223098b6d5efe4eda97c66b24a2c72faab8a018c749003a8d",
    ),
    ModelSpec(
        "transformer/encoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644.onnx",
        "1513e83ae281ef06cdb8f08451b59f06c56536f13bd3418b4fd13227543dc4ff",
    ),
    ModelSpec(
        "transformer/decoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644.onnx",
        "8652b5c2e3129775ca9109eb180c16c3615413ce38005adc8ce5966c3c76737c",
    ),
)


@dataclass(frozen=True, slots=True)
class RuntimeProbe:
    ready: bool
    reason: str
    version: str | None
    verified_models: int
    diagnostic: str = ""


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    return_code: int
    musicxml_artifacts: tuple[Path, ...]
    diagnostic: str


Runner = Callable[..., subprocess.CompletedProcess[str]]
VersionReader = Callable[[str], str]
PackageRootResolver = Callable[[], Path]
Probe = Callable[[ServiceConfig], RuntimeProbe]


def _homr_package_root() -> Path:
    spec = util.find_spec("homr")
    if spec is None or spec.origin is None:
        raise RuntimeExecutionError("homr_package_unavailable")
    return Path(spec.origin).resolve(strict=True).parent


def _prepare_runtime_directories(config: ServiceConfig) -> None:
    workspace = config.workspace_root
    home = workspace / "home"
    for path in (
        workspace,
        home,
        home / ".cache",
        home / ".config",
        home / ".local" / "share",
        workspace / "tmp",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _runtime_environment(config: ServiceConfig) -> dict[str, str]:
    _prepare_runtime_directories(config)
    workspace = config.workspace_root
    home = workspace / "home"
    runtime_tmp = workspace / "tmp"
    env = dict(os.environ)
    for dangerous_name in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONINSPECT",
        "PYTHONSTARTUP",
        "LD_PRELOAD",
    ):
        env.pop(dangerous_name, None)
    env.update(
        {
            "HOME": str(home),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "TMPDIR": str(runtime_tmp),
            "TMP": str(runtime_tmp),
            "TEMP": str(runtime_tmp),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
            "MKL_NUM_THREADS": "2",
        }
    )
    return env


def _diagnostic(stdout: str | None, stderr: str | None) -> str:
    combined = "\n".join(
        part.strip() for part in (stdout or "", stderr or "") if part.strip()
    )
    return combined[:_MAX_DIAGNOSTIC_CHARS]


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_models(package_root: Path, specs: Iterable[ModelSpec]) -> tuple[int, str | None]:
    verified = 0
    for model in specs:
        path = package_root / model.relative_path
        if path.is_symlink() or not path.is_file():
            return verified, f"homr_model_unavailable:{model.relative_path}"
        if _file_sha256(path) != model.sha256:
            return verified, f"homr_model_checksum_mismatch:{model.relative_path}"
        verified += 1
    return verified, None


def probe_runtime(
    config: ServiceConfig,
    *,
    runner: Runner = subprocess.run,
    version_reader: VersionReader = metadata.version,
    package_root_resolver: PackageRootResolver = _homr_package_root,
    model_specs: Iterable[ModelSpec] = MODEL_SPECS,
) -> RuntimeProbe:
    """Verify the pinned package, model files, and fixed HOMR command."""

    if config.runtime_mode != "homr":
        return RuntimeProbe(False, "homr_runtime_disabled", None, 0)
    if not config.homr_command.is_file() or not os.access(config.homr_command, os.X_OK):
        return RuntimeProbe(False, "homr_command_unavailable", None, 0)

    try:
        version = version_reader("homr")
    except metadata.PackageNotFoundError:
        return RuntimeProbe(False, "homr_package_unavailable", None, 0)
    except Exception as exc:  # defensive isolation around package metadata
        return RuntimeProbe(
            False,
            "homr_package_probe_failed",
            None,
            0,
            str(exc)[:_MAX_DIAGNOSTIC_CHARS],
        )
    if version != config.homr_version:
        return RuntimeProbe(False, "homr_version_mismatch", version, 0)

    try:
        package_root = package_root_resolver().resolve(strict=True)
    except (OSError, RuntimeExecutionError) as exc:
        return RuntimeProbe(
            False,
            "homr_package_unavailable",
            version,
            0,
            str(exc)[:_MAX_DIAGNOSTIC_CHARS],
        )

    verified, model_error = _verify_models(package_root, tuple(model_specs))
    if model_error is not None:
        return RuntimeProbe(False, model_error, version, verified)

    _prepare_runtime_directories(config)
    try:
        completed = runner(
            [str(config.homr_command), "--help"],
            cwd=config.workspace_root,
            env=_runtime_environment(config),
            capture_output=True,
            text=True,
            timeout=config.probe_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return RuntimeProbe(False, "homr_probe_timed_out", version, verified)
    except OSError as exc:
        return RuntimeProbe(
            False,
            "homr_probe_failed",
            version,
            verified,
            str(exc)[:_MAX_DIAGNOSTIC_CHARS],
        )

    output = _diagnostic(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        return RuntimeProbe(
            False,
            "homr_probe_nonzero_exit",
            version,
            verified,
            output,
        )
    return RuntimeProbe(True, "ready", version, verified, output)


def _resolved_workspace(config: ServiceConfig) -> Path:
    _prepare_runtime_directories(config)
    return config.workspace_root.resolve(strict=True)


def _require_inside_workspace(path: Path, workspace: Path, *, strict: bool) -> Path:
    resolved = path.resolve(strict=strict)
    if not resolved.is_relative_to(workspace):
        raise RuntimeExecutionError("path escapes the HOMR workspace")
    return resolved


def build_transcription_command(
    input_path: Path,
    output_dir: Path,
    config: ServiceConfig,
) -> tuple[str, ...]:
    """Build a fixed CPU-only CLI command with no client-controlled options."""

    workspace = _resolved_workspace(config)
    if input_path.is_symlink():
        raise RuntimeExecutionError("symbolic-link input is not allowed")
    safe_input = _require_inside_workspace(input_path, workspace, strict=True)
    if not safe_input.is_file():
        raise RuntimeExecutionError("input is not a regular file")
    if safe_input.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise RuntimeExecutionError("unsupported HOMR input suffix")

    safe_output = _require_inside_workspace(output_dir, workspace, strict=False)
    safe_output.mkdir(parents=True, exist_ok=True)
    if safe_output.is_symlink():
        raise RuntimeExecutionError("symbolic-link output is not allowed")
    if safe_input.parent != safe_output:
        raise RuntimeExecutionError("HOMR input must be staged inside its output directory")

    expected_output = safe_input.with_suffix(".musicxml")
    if expected_output.exists():
        raise RuntimeExecutionError("pre-existing HOMR output is not allowed")

    return (
        str(config.homr_command),
        "--gpu",
        "no",
        "--no-title",
        str(safe_input),
    )


def transcribe_file(
    input_path: Path,
    output_dir: Path,
    config: ServiceConfig,
    *,
    runner: Runner = subprocess.run,
    probe: Probe = probe_runtime,
) -> TranscriptionResult:
    """Run one private CPU transcription and validate generated MusicXML."""

    runtime_probe = probe(config)
    if not runtime_probe.ready:
        raise RuntimeExecutionError(runtime_probe.reason)

    command = build_transcription_command(input_path, output_dir, config)
    expected_output = Path(command[-1]).with_suffix(".musicxml")
    try:
        completed = runner(
            list(command),
            cwd=output_dir.resolve(strict=True),
            env=_runtime_environment(config),
            capture_output=True,
            text=True,
            timeout=config.request_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeExecutionError("homr_transcription_timed_out") from exc
    except OSError as exc:
        raise RuntimeExecutionError("homr_transcription_failed_to_start") from exc

    diagnostic = _diagnostic(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        raise RuntimeExecutionError(
            f"homr_transcription_nonzero_exit:{completed.returncode}:{diagnostic}"
        )
    if expected_output.is_symlink() or not expected_output.is_file():
        raise RuntimeExecutionError(f"homr_musicxml_not_created:{diagnostic}")

    try:
        root = ET.parse(expected_output).getroot()
    except ET.ParseError as exc:
        raise RuntimeExecutionError("homr_musicxml_invalid_xml") from exc
    root_name = root.tag.rsplit("}", 1)[-1]
    if root_name not in {"score-partwise", "score-timewise"}:
        raise RuntimeExecutionError("homr_musicxml_invalid_root")

    return TranscriptionResult(completed.returncode, (expected_output,), diagnostic)
