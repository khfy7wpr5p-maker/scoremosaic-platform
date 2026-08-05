from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

FIXTURE_MANIFEST_VERSION: Final = "1.0"
CORE_VERSION: Final = "closed-fixture-core-v1"
ALLOWED_FIXTURE_ROOT_NAME: Final = "fixtures"


class FixtureInferenceError(ValueError):
    """Fail-closed error for offline generated-fixture execution."""


@dataclass(frozen=True)
class FixtureInferenceResult:
    fixture_id: str
    fixture_version: str
    input_sha256: str
    output_sha256: str
    byte_length: int
    line_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "completed_offline_fixture_only",
            "coreVersion": CORE_VERSION,
            "fixtureId": self.fixture_id,
            "fixtureVersion": self.fixture_version,
            "inputSha256": self.input_sha256,
            "outputSha256": self.output_sha256,
            "byteLength": self.byte_length,
            "lineCount": self.line_count,
            "modelLoaded": False,
            "realOmrInference": False,
            "userInputAccepted": False,
            "networkUsed": False,
        }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FixtureInferenceError(f"fixture manifest field {key!r} must be a non-empty string")
    return value


def _direct_child(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    if candidate.parent != root.resolve():
        raise FixtureInferenceError("fixture files must be direct children of the allowed fixture root")
    if candidate.is_symlink():
        raise FixtureInferenceError("fixture symlinks are forbidden")
    return candidate


def run_generated_fixture(*, manifest_path: Path, allowed_root: Path) -> FixtureInferenceResult:
    root = allowed_root.resolve()
    if root.name != ALLOWED_FIXTURE_ROOT_NAME:
        raise FixtureInferenceError("allowed fixture root must be named 'fixtures'")
    if not root.is_dir() or root.is_symlink():
        raise FixtureInferenceError("allowed fixture root must be a real directory")

    resolved_manifest = manifest_path.resolve()
    if resolved_manifest.parent != root or resolved_manifest.is_symlink():
        raise FixtureInferenceError("fixture manifest must be a non-symlink direct child of the fixture root")

    try:
        manifest = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FixtureInferenceError("fixture manifest is unreadable or invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise FixtureInferenceError("fixture manifest root must be an object")

    if _require_text(manifest, "manifestVersion") != FIXTURE_MANIFEST_VERSION:
        raise FixtureInferenceError("unsupported fixture manifest version")
    fixture_id = _require_text(manifest, "fixtureId")
    fixture_version = _require_text(manifest, "fixtureVersion")
    input_name = _require_text(manifest, "inputName")
    expected_input_sha256 = _require_text(manifest, "inputSha256").lower()
    expected_output_sha256 = _require_text(manifest, "expectedOutputSha256").lower()

    for label, value in (("inputSha256", expected_input_sha256), ("expectedOutputSha256", expected_output_sha256)):
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise FixtureInferenceError(f"{label} must be 64 lowercase hexadecimal characters")

    input_path = _direct_child(root, input_name)
    if not input_path.is_file():
        raise FixtureInferenceError("generated fixture input is missing")
    payload = input_path.read_bytes()
    actual_input_sha256 = _sha256_bytes(payload)
    if actual_input_sha256 != expected_input_sha256:
        raise FixtureInferenceError("generated fixture checksum mismatch")

    output_sha256 = _sha256_bytes(b"scoremosaic-closed-core-v1\0" + payload)
    if output_sha256 != expected_output_sha256:
        raise FixtureInferenceError("deterministic golden output mismatch")

    return FixtureInferenceResult(
        fixture_id=fixture_id,
        fixture_version=fixture_version,
        input_sha256=actual_input_sha256,
        output_sha256=output_sha256,
        byte_length=len(payload),
        line_count=payload.count(b"\n"),
    )


def disabled_fixture_inference_evidence() -> dict[str, object]:
    return {
        "status": "offline_fixture_execution_not_requested",
        "coreVersion": CORE_VERSION,
        "fixtureExecutionEnabled": True,
        "realOmrInference": False,
        "userInputAccepted": False,
        "networkUsed": False,
    }
