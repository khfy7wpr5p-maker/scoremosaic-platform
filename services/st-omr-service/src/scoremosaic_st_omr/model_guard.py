from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

MANIFEST_VERSION: Final = "1.0"
ALLOWED_MODEL_ROOT_NAME: Final = "models"


class ModelGuardError(ValueError):
    """Fail-closed model artifact validation error."""


@dataclass(frozen=True)
class ModelEvidence:
    status: str
    manifest_version: str
    model_id: str
    model_version: str
    artifact_name: str
    sha256: str
    artifact_verified: bool
    model_loaded: bool = False
    inference_enabled: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "manifestVersion": self.manifest_version,
            "modelId": self.model_id,
            "modelVersion": self.model_version,
            "artifactName": self.artifact_name,
            "sha256": self.sha256,
            "artifactVerified": self.artifact_verified,
            "modelLoaded": self.model_loaded,
            "inferenceEnabled": self.inference_enabled,
        }


def _require_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModelGuardError(f"manifest field {key!r} must be a non-empty string")
    return value


def _safe_child(root: Path, relative_name: str) -> Path:
    candidate = (root / relative_name).resolve()
    resolved_root = root.resolve()
    if candidate.parent != resolved_root:
        raise ModelGuardError("model artifact must be a direct child of the allowed model root")
    if candidate.is_symlink():
        raise ModelGuardError("model artifact symlinks are forbidden")
    return candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_pinned_model(manifest_path: Path, *, allowed_root: Path) -> ModelEvidence:
    root = allowed_root.resolve()
    if root.name != ALLOWED_MODEL_ROOT_NAME:
        raise ModelGuardError("allowed model root must be named 'models'")
    if not root.is_dir() or root.is_symlink():
        raise ModelGuardError("allowed model root must be a real directory")

    resolved_manifest = manifest_path.resolve()
    if resolved_manifest.parent != root or resolved_manifest.is_symlink():
        raise ModelGuardError("manifest must be a non-symlink direct child of the allowed model root")

    try:
        payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelGuardError("manifest is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelGuardError("manifest root must be an object")

    manifest_version = _require_text(payload, "manifestVersion")
    if manifest_version != MANIFEST_VERSION:
        raise ModelGuardError("unsupported manifest version")

    model_id = _require_text(payload, "modelId")
    model_version = _require_text(payload, "modelVersion")
    artifact_name = _require_text(payload, "artifactName")
    expected_sha256 = _require_text(payload, "sha256").lower()
    if len(expected_sha256) != 64 or any(char not in "0123456789abcdef" for char in expected_sha256):
        raise ModelGuardError("sha256 must be exactly 64 lowercase hexadecimal characters")

    artifact_path = _safe_child(root, artifact_name)
    if not artifact_path.is_file():
        raise ModelGuardError("pinned model artifact is missing")

    actual_sha256 = sha256_file(artifact_path)
    if actual_sha256 != expected_sha256:
        raise ModelGuardError("pinned model checksum mismatch")

    return ModelEvidence(
        status="verified_not_loaded",
        manifest_version=manifest_version,
        model_id=model_id,
        model_version=model_version,
        artifact_name=artifact_name,
        sha256=actual_sha256,
        artifact_verified=True,
    )


def disabled_model_evidence() -> dict[str, object]:
    return {
        "status": "validation_not_requested",
        "artifactVerified": False,
        "modelLoaded": False,
        "inferenceEnabled": False,
    }
