"""Bounded Clarity-OMR runtime probing and private transcription helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable
import json
import os
import re
import subprocess

from .candidate_safety import (
    CandidateSafetyError,
    CandidateSafetyHandoff,
    CandidateSafetyResult,
    validate_musicxml_bytes,
    verify_musicxml_handoff,
)
from .config import ServiceConfig

_RUNTIME_OUTPUT_REDACTED = "runtime_output_redacted"
_RUNTIME_ERROR_REDACTED = "runtime_error_redacted"
_MAX_MUSICXML_BYTES = 64 * 1024 * 1024
_MUSICXML_DOCTYPE_RE = re.compile(
    rb"""
    <!DOCTYPE\s+
    (?P<root>score-partwise|score-timewise)\s+
    PUBLIC\s+
    (?P<public_quote>["'])
    -//Recordare//DTD\s+MusicXML\s+\d+(?:\.\d+)?\s+
    (?P<form>Partwise|Timewise)//EN
    (?P=public_quote)\s+
    (?P<system_quote>["'])
    https?://(?:www\.)?musicxml\.org/dtds/
    (?P<dtd>partwise|timewise)\.dtd
    (?P=system_quote)\s*>
    """,
    re.IGNORECASE | re.VERBOSE,
)


class RuntimeExecutionError(RuntimeError):
    """Raised when a bounded Clarity command cannot complete safely."""


@dataclass(frozen=True, slots=True)
class ModelSpec:
    relative_path: str
    sha256: str


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        "info/yolo.pt",
        "94610a2749022edd6938146505812544fece2983740fe8523907d2c855e4da73",
    ),
    ModelSpec(
        "info/model.safetensors",
        "5138f11acd1b89d780e65fbb363dae992e8c6d3e514f0e2a01062b0ea99edb43",
    ),
)


@dataclass(frozen=True, slots=True)
class RuntimeProbe:
    ready: bool
    reason: str
    source_revision: str | None
    model_revision: str | None
    verified_models: int
    torch_version: str | None
    diagnostic: str = ""


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    return_code: int
    musicxml_artifacts: tuple[Path, ...]
    diagnostic: str
    candidate_handoffs: tuple[CandidateSafetyHandoff, ...] = ()


Runner = Callable[..., subprocess.CompletedProcess[str]]
Probe = Callable[[ServiceConfig], RuntimeProbe]


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
        "CUDA_VISIBLE_DEVICES",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
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
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "YOLO_CONFIG_DIR": str(home / ".config" / "Ultralytics"),
        }
    )
    return env


def _diagnostic(stdout: str | None, stderr: str | None) -> str:
    if any(part and part.strip() for part in (stdout, stderr)):
        return _RUNTIME_OUTPUT_REDACTED
    return ""


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_models(source_root: Path, specs: Iterable[ModelSpec]) -> tuple[int, str | None]:
    verified = 0
    for model in specs:
        path = source_root / model.relative_path
        if path.is_symlink() or not path.is_file():
            return verified, f"clarity_model_unavailable:{model.relative_path}"
        if _file_sha256(path) != model.sha256:
            return verified, f"clarity_model_checksum_mismatch:{model.relative_path}"
        verified += 1
    return verified, None


def probe_runtime(
    config: ServiceConfig,
    *,
    runner: Runner = subprocess.run,
    model_specs: Iterable[ModelSpec] = MODEL_SPECS,
) -> RuntimeProbe:
    """Verify the pinned source snapshot, CPU runtime, and model files."""

    if config.compute_mode != "cpu":
        return RuntimeProbe(False, "clarity_runtime_disabled", None, None, 0, None)
    if not config.python_command.is_file() or not os.access(config.python_command, os.X_OK):
        return RuntimeProbe(False, "clarity_python_unavailable", None, None, 0, None)
    if config.source_root.is_symlink() or not config.source_root.is_dir():
        return RuntimeProbe(False, "clarity_source_unavailable", None, None, 0, None)

    marker = config.source_root / ".scoremosaic-source-revision"
    try:
        installed_revision = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return RuntimeProbe(
            False,
            "clarity_source_revision_unavailable",
            None,
            config.model_revision,
            0,
            None,
            _RUNTIME_ERROR_REDACTED,
        )
    if installed_revision != config.source_revision:
        return RuntimeProbe(
            False,
            "clarity_source_revision_mismatch",
            installed_revision,
            config.model_revision,
            0,
            None,
        )

    omr_script = config.source_root / "omr.py"
    if omr_script.is_symlink() or not omr_script.is_file():
        return RuntimeProbe(
            False,
            "clarity_entrypoint_unavailable",
            installed_revision,
            config.model_revision,
            0,
            None,
        )

    verified, model_error = _verify_models(config.source_root, tuple(model_specs))
    if model_error is not None:
        return RuntimeProbe(
            False,
            model_error,
            installed_revision,
            config.model_revision,
            verified,
            None,
        )

    _prepare_runtime_directories(config)
    probe_code = (
        "import json, torch, torchvision; "
        "import fitz, timm, transformers, ultralytics, music21; "
        "print(json.dumps({"
        "'torch': torch.__version__, "
        "'torchvision': torchvision.__version__, "
        "'cuda': torch.cuda.is_available()"
        "}, sort_keys=True))"
    )
    try:
        completed = runner(
            [str(config.python_command), "-c", probe_code],
            cwd=config.workspace_root,
            env=_runtime_environment(config),
            capture_output=True,
            text=True,
            timeout=config.probe_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return RuntimeProbe(
            False,
            "clarity_probe_timed_out",
            installed_revision,
            config.model_revision,
            verified,
            None,
        )
    except OSError:
        return RuntimeProbe(
            False,
            "clarity_probe_failed",
            installed_revision,
            config.model_revision,
            verified,
            None,
            _RUNTIME_ERROR_REDACTED,
        )

    diagnostic = _diagnostic(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        return RuntimeProbe(
            False,
            "clarity_probe_nonzero_exit",
            installed_revision,
            config.model_revision,
            verified,
            None,
            diagnostic,
        )
    try:
        payload = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError, TypeError):
        return RuntimeProbe(
            False,
            "clarity_probe_invalid_output",
            installed_revision,
            config.model_revision,
            verified,
            None,
            diagnostic,
        )

    torch_version = str(payload.get("torch", "")) or None
    if torch_version != "2.13.0+cpu" or payload.get("torchvision") != "0.28.0+cpu":
        return RuntimeProbe(
            False,
            "clarity_torch_version_mismatch",
            installed_revision,
            config.model_revision,
            verified,
            torch_version,
            diagnostic,
        )
    if payload.get("cuda") is not False:
        return RuntimeProbe(
            False,
            "clarity_cpu_mode_not_enforced",
            installed_revision,
            config.model_revision,
            verified,
            torch_version,
            diagnostic,
        )

    return RuntimeProbe(
        True,
        "ready",
        installed_revision,
        config.model_revision,
        verified,
        torch_version,
        diagnostic,
    )


def _resolved_workspace(config: ServiceConfig) -> Path:
    _prepare_runtime_directories(config)
    return config.workspace_root.resolve(strict=True)


def _require_inside_workspace(path: Path, workspace: Path, *, strict: bool) -> Path:
    resolved = path.resolve(strict=strict)
    if not resolved.is_relative_to(workspace):
        raise RuntimeExecutionError("path escapes the Clarity workspace")
    return resolved


def build_transcription_command(
    input_path: Path,
    output_dir: Path,
    config: ServiceConfig,
) -> tuple[str, ...]:
    """Build a fixed CPU-only command with no client-controlled Clarity flags."""

    workspace = _resolved_workspace(config)
    if input_path.is_symlink():
        raise RuntimeExecutionError("symbolic-link input is not allowed")
    safe_input = _require_inside_workspace(input_path, workspace, strict=True)
    if not safe_input.is_file():
        raise RuntimeExecutionError("input is not a regular file")
    if safe_input.suffix.lower() != ".pdf":
        raise RuntimeExecutionError("unsupported Clarity input suffix")

    safe_output_dir = _require_inside_workspace(output_dir, workspace, strict=False)
    safe_output_dir.mkdir(parents=True, exist_ok=True)
    if safe_output_dir.is_symlink():
        raise RuntimeExecutionError("symbolic-link output is not allowed")

    output_path = safe_output_dir / "result.musicxml"
    work_dir = safe_output_dir / "work"
    if output_path.exists() or output_path.is_symlink():
        raise RuntimeExecutionError("pre-existing Clarity output is not allowed")
    if work_dir.exists() and work_dir.is_symlink():
        raise RuntimeExecutionError("symbolic-link work directory is not allowed")
    work_dir.mkdir(parents=True, exist_ok=True)

    return (
        str(config.python_command),
        str(config.source_root / "omr.py"),
        str(safe_input),
        "--output",
        str(output_path),
        "--device",
        "cpu",
        "--beam-width",
        str(config.beam_width),
        "--pdf-dpi",
        str(config.pdf_dpi),
        "--work-dir",
        str(work_dir),
    )


def _sanitize_musicxml_document(document: bytes) -> bytes:
    """Remove only a canonical MusicXML DTD without resolving external entities."""

    upper = document.upper()
    if b"<!ENTITY" in upper:
        raise RuntimeExecutionError("clarity_musicxml_unsafe_declaration")

    doctype_index = upper.find(b"<!DOCTYPE")
    if doctype_index < 0:
        return document
    if upper.find(b"<!DOCTYPE", doctype_index + 1) >= 0 or doctype_index > 8192:
        raise RuntimeExecutionError("clarity_musicxml_unsafe_declaration")

    match = _MUSICXML_DOCTYPE_RE.search(document)
    if match is None or match.start() != doctype_index:
        raise RuntimeExecutionError("clarity_musicxml_unsafe_declaration")

    root_name = match.group("root").lower()
    form = match.group("form").lower()
    dtd = match.group("dtd").lower()
    expected = b"partwise" if root_name == b"score-partwise" else b"timewise"
    if form != expected or dtd != expected:
        raise RuntimeExecutionError("clarity_musicxml_unsafe_declaration")

    sanitized = document[: match.start()] + document[match.end() :]
    sanitized_upper = sanitized.upper()
    if b"<!DOCTYPE" in sanitized_upper or b"<!ENTITY" in sanitized_upper:
        raise RuntimeExecutionError("clarity_musicxml_unsafe_declaration")
    return sanitized


def _validate_musicxml(path: Path) -> CandidateSafetyResult:
    if path.is_symlink() or not path.is_file():
        raise RuntimeExecutionError("clarity_musicxml_not_created")
    size = path.stat().st_size
    if size <= 0 or size > _MAX_MUSICXML_BYTES:
        raise RuntimeExecutionError("clarity_musicxml_size_invalid")
    try:
        document = path.read_bytes()
    except OSError as exc:
        raise RuntimeExecutionError("clarity_musicxml_read_failed") from exc

    _sanitize_musicxml_document(document)
    try:
        return validate_musicxml_bytes(document)
    except CandidateSafetyError as exc:
        if exc.code == "musicxml_invalid_xml":
            raise RuntimeExecutionError("clarity_musicxml_invalid_xml") from exc
        if exc.code == "musicxml_invalid_root":
            raise RuntimeExecutionError("clarity_musicxml_invalid_root") from exc
        raise RuntimeExecutionError(f"clarity_candidate_unsafe:{exc.code}") from exc


def transcribe_file(
    input_path: Path,
    output_dir: Path,
    config: ServiceConfig,
    *,
    runner: Runner = subprocess.run,
    probe: Probe = probe_runtime,
) -> TranscriptionResult:
    """Run one private CPU transcription and validate the generated MusicXML."""

    runtime_probe = probe(config)
    if not runtime_probe.ready:
        raise RuntimeExecutionError(runtime_probe.reason)

    command = build_transcription_command(input_path, output_dir, config)
    output_path = Path(command[command.index("--output") + 1])
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
    except subprocess.TimeoutExpired:
        raise RuntimeExecutionError("clarity_transcription_timed_out") from None
    except OSError:
        raise RuntimeExecutionError("clarity_transcription_failed_to_start") from None

    diagnostic = _diagnostic(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        raise RuntimeExecutionError("clarity_transcription_nonzero_exit")

    evidence = _validate_musicxml(output_path)
    try:
        handoff = verify_musicxml_handoff(output_path, evidence)
    except CandidateSafetyError as exc:
        raise RuntimeExecutionError(f"clarity_candidate_unsafe:{exc.code}") from exc
    return TranscriptionResult(
        completed.returncode,
        (output_path,),
        diagnostic,
        (handoff,),
    )
