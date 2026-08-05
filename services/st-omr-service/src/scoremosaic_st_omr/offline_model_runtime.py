from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .model_guard import ModelGuardError, validate_pinned_model
from .offline_fixture_inference import FixtureInferenceError, run_generated_fixture

RUNTIME_CORE_VERSION: Final = "pinned-offline-model-runtime-v1"
MODEL_MANIFEST_VERSION: Final = "1.0"
MODEL_FORMAT_VERSION: Final = "1.0"
RUNTIME_KIND: Final = "deterministic-integer-linear-v1"
MODEL_PURPOSE: Final = "repository_test_only"
INPUT_SCHEMA_VERSION: Final = "1.0"
OUTPUT_SCHEMA_VERSION: Final = "1.0"
ALLOWED_MODEL_ROOT_NAME: Final = "models"
ALLOWED_FIXTURE_ROOT_NAME: Final = "fixtures"
MAX_MODEL_BYTES: Final = 64 * 1024
MAX_PARAMETER_ABS: Final = 1_000_000
FEATURE_ORDER: Final = ("byteLength", "lineCount", "dashCount")
ALLOWED_LABELS: Final = ("repository_fixture_shape", "other")
EXPECTED_PROVENANCE: Final = {
    "creationMethod": "hand_authored_repository_test_fixture",
    "trainingDataUsed": False,
    "externalWeightsUsed": False,
}
EXPECTED_BOUNDARIES: Final = {
    "realOmrModel": False,
    "userInputAccepted": False,
    "httpInference": False,
    "gatewayIntegration": False,
    "ensembleIntegration": False,
    "productionEligible": False,
}


class OfflineModelRuntimeError(ValueError):
    """Fail-closed error for the repository-only offline test model runtime."""


@dataclass(frozen=True)
class LoadedOfflineTestModel:
    model_id: str
    model_version: str
    artifact_name: str
    artifact_sha256: str
    labels: tuple[str, ...]
    weights: tuple[tuple[int, ...], ...]
    biases: tuple[int, ...]

    def score(self, features: tuple[int, ...]) -> tuple[tuple[str, int], ...]:
        if len(features) != len(FEATURE_ORDER):
            raise OfflineModelRuntimeError("feature vector does not match the closed runtime schema")
        records: list[tuple[str, int]] = []
        for label, weights, bias in zip(self.labels, self.weights, self.biases, strict=True):
            score = sum(
                weight * feature
                for weight, feature in zip(weights, features, strict=True)
            ) + bias
            records.append((label, score))
        return tuple(records)


@dataclass(frozen=True)
class OfflineModelInferenceResult:
    model_id: str
    model_version: str
    model_sha256: str
    fixture_id: str
    fixture_version: str
    fixture_input_sha256: str
    features: tuple[tuple[str, int], ...]
    scores: tuple[tuple[str, int], ...]
    predicted_label: str
    output_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "completed_pinned_offline_test_model_only",
            "runtimeCoreVersion": RUNTIME_CORE_VERSION,
            "runtimeKind": RUNTIME_KIND,
            "modelId": self.model_id,
            "modelVersion": self.model_version,
            "modelSha256": self.model_sha256,
            "fixtureId": self.fixture_id,
            "fixtureVersion": self.fixture_version,
            "fixtureInputSha256": self.fixture_input_sha256,
            "features": {name: value for name, value in self.features},
            "scores": {label: score for label, score in self.scores},
            "predictedLabel": self.predicted_label,
            "outputSha256": self.output_sha256,
            "modelLoaded": True,
            "inferenceEnabled": True,
            "offlineOnly": True,
            "repositoryTestModelOnly": True,
            "realOmrInference": False,
            "realOmrAccuracyMeasured": False,
            "generalAccuracyClaim": False,
            "userInputAccepted": False,
            "httpInferenceEnabled": False,
            "networkUsed": False,
            "gatewayIntegration": False,
            "ensembleIntegration": False,
            "productionEligible": False,
        }


def _read_json_object(path: Path, *, context: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OfflineModelRuntimeError(f"{context} is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise OfflineModelRuntimeError(f"{context} root must be an object")
    return payload


def _require_text(payload: dict[str, object], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise OfflineModelRuntimeError(f"{context} field {key!r} must be a non-empty string")
    return value


def _require_bounded_integer(value: object, *, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise OfflineModelRuntimeError(f"{context} must be an integer")
    if abs(value) > MAX_PARAMETER_ABS:
        raise OfflineModelRuntimeError(f"{context} exceeds the bounded parameter range")
    return value


def _validate_root(root: Path, *, expected_name: str, context: str) -> Path:
    if root.name != expected_name:
        raise OfflineModelRuntimeError(f"{context} must be named {expected_name!r}")
    if root.is_symlink() or not root.is_dir():
        raise OfflineModelRuntimeError(f"{context} must be a real non-symlink directory")
    return root.resolve()


def _direct_child(root: Path, name: str, *, context: str) -> Path:
    if not name or Path(name).name != name:
        raise OfflineModelRuntimeError(f"{context} must be a direct child name")
    raw_candidate = root / name
    if raw_candidate.is_symlink():
        raise OfflineModelRuntimeError(f"{context} symlinks are forbidden")
    candidate = raw_candidate.resolve()
    if candidate.parent != root.resolve():
        raise OfflineModelRuntimeError(f"{context} must be a direct child of its allowed root")
    return candidate


def _direct_manifest(path: Path, root: Path, *, context: str) -> Path:
    if path.is_symlink():
        raise OfflineModelRuntimeError(f"{context} symlinks are forbidden")
    resolved = path.resolve()
    if resolved.parent != root.resolve():
        raise OfflineModelRuntimeError(f"{context} must be a direct child of its allowed root")
    if not resolved.is_file():
        raise OfflineModelRuntimeError(f"{context} is missing")
    return resolved


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(canonical)


def load_pinned_offline_test_model(
    *,
    manifest_path: Path,
    allowed_model_root: Path,
) -> LoadedOfflineTestModel:
    model_root = _validate_root(
        allowed_model_root,
        expected_name=ALLOWED_MODEL_ROOT_NAME,
        context="allowed model root",
    )
    resolved_manifest = _direct_manifest(
        manifest_path,
        model_root,
        context="model manifest",
    )
    manifest = _read_json_object(resolved_manifest, context="model manifest")
    required_manifest_keys = {
        "manifestVersion",
        "modelId",
        "modelVersion",
        "artifactName",
        "sha256",
        "runtimeKind",
        "purpose",
        "inputSchemaVersion",
        "outputSchemaVersion",
        "provenance",
        "boundaries",
    }
    if set(manifest) != required_manifest_keys:
        raise OfflineModelRuntimeError(
            "model manifest fields must match the closed Phase 21 schema"
        )

    manifest_version = _require_text(
        manifest,
        "manifestVersion",
        context="model manifest",
    )
    if manifest_version != MODEL_MANIFEST_VERSION:
        raise OfflineModelRuntimeError("unsupported model manifest version")
    model_id = _require_text(manifest, "modelId", context="model manifest")
    model_version = _require_text(manifest, "modelVersion", context="model manifest")
    artifact_name = _require_text(manifest, "artifactName", context="model manifest")
    if _require_text(manifest, "runtimeKind", context="model manifest") != RUNTIME_KIND:
        raise OfflineModelRuntimeError("unsupported offline model runtime kind")
    if _require_text(manifest, "purpose", context="model manifest") != MODEL_PURPOSE:
        raise OfflineModelRuntimeError("model purpose must remain repository_test_only")
    if (
        _require_text(manifest, "inputSchemaVersion", context="model manifest")
        != INPUT_SCHEMA_VERSION
    ):
        raise OfflineModelRuntimeError("unsupported model input schema version")
    if (
        _require_text(manifest, "outputSchemaVersion", context="model manifest")
        != OUTPUT_SCHEMA_VERSION
    ):
        raise OfflineModelRuntimeError("unsupported model output schema version")
    if manifest.get("provenance") != EXPECTED_PROVENANCE:
        raise OfflineModelRuntimeError(
            "model provenance does not match the closed repository-test policy"
        )
    if manifest.get("boundaries") != EXPECTED_BOUNDARIES:
        raise OfflineModelRuntimeError(
            "model boundaries do not match the closed Phase 21 policy"
        )

    artifact_path = _direct_child(model_root, artifact_name, context="model artifact")
    if not artifact_path.is_file():
        raise OfflineModelRuntimeError("model artifact is missing")
    if artifact_path.stat().st_size > MAX_MODEL_BYTES:
        raise OfflineModelRuntimeError("model artifact exceeds the Phase 21 size limit")

    try:
        evidence = validate_pinned_model(resolved_manifest, allowed_root=model_root)
    except ModelGuardError as exc:
        raise OfflineModelRuntimeError("pinned model validation failed closed") from exc
    if (
        evidence.model_id != model_id
        or evidence.model_version != model_version
        or evidence.artifact_name != artifact_name
        or evidence.status != "verified_not_loaded"
        or not evidence.artifact_verified
        or evidence.model_loaded
        or evidence.inference_enabled
    ):
        raise OfflineModelRuntimeError("model guard evidence is inconsistent")

    model = _read_json_object(artifact_path, context="model artifact")
    required_model_keys = {
        "formatVersion",
        "runtimeKind",
        "featureOrder",
        "labels",
        "weights",
        "bias",
    }
    if set(model) != required_model_keys:
        raise OfflineModelRuntimeError(
            "model artifact fields must match the closed runtime schema"
        )
    if _require_text(model, "formatVersion", context="model artifact") != MODEL_FORMAT_VERSION:
        raise OfflineModelRuntimeError("unsupported model format version")
    if _require_text(model, "runtimeKind", context="model artifact") != RUNTIME_KIND:
        raise OfflineModelRuntimeError("model artifact runtime kind mismatch")
    if model.get("featureOrder") != list(FEATURE_ORDER):
        raise OfflineModelRuntimeError(
            "model feature order does not match the closed runtime schema"
        )
    if model.get("labels") != list(ALLOWED_LABELS):
        raise OfflineModelRuntimeError(
            "model labels do not match the closed runtime schema"
        )

    raw_weights = model.get("weights")
    raw_bias = model.get("bias")
    if not isinstance(raw_weights, dict) or set(raw_weights) != set(ALLOWED_LABELS):
        raise OfflineModelRuntimeError("model weights must match the closed label set")
    if not isinstance(raw_bias, dict) or set(raw_bias) != set(ALLOWED_LABELS):
        raise OfflineModelRuntimeError("model bias must match the closed label set")

    weights: list[tuple[int, ...]] = []
    biases: list[int] = []
    for label in ALLOWED_LABELS:
        label_weights = raw_weights.get(label)
        if not isinstance(label_weights, list) or len(label_weights) != len(FEATURE_ORDER):
            raise OfflineModelRuntimeError("model weight vector length is invalid")
        weights.append(
            tuple(
                _require_bounded_integer(value, context=f"weight {label}[{index}]")
                for index, value in enumerate(label_weights)
            )
        )
        biases.append(
            _require_bounded_integer(raw_bias.get(label), context=f"bias {label}")
        )

    return LoadedOfflineTestModel(
        model_id=model_id,
        model_version=model_version,
        artifact_name=artifact_name,
        artifact_sha256=evidence.sha256,
        labels=ALLOWED_LABELS,
        weights=tuple(weights),
        biases=tuple(biases),
    )


def run_pinned_offline_test_model(
    *,
    model_manifest_path: Path,
    model_root: Path,
    fixture_manifest_path: Path,
    fixture_root: Path,
) -> OfflineModelInferenceResult:
    loaded_model = load_pinned_offline_test_model(
        manifest_path=model_manifest_path,
        allowed_model_root=model_root,
    )

    resolved_fixture_root = _validate_root(
        fixture_root,
        expected_name=ALLOWED_FIXTURE_ROOT_NAME,
        context="allowed fixture root",
    )
    resolved_fixture_manifest = _direct_manifest(
        fixture_manifest_path,
        resolved_fixture_root,
        context="fixture manifest",
    )
    try:
        fixture_result = run_generated_fixture(
            manifest_path=resolved_fixture_manifest,
            allowed_root=resolved_fixture_root,
        )
    except FixtureInferenceError as exc:
        raise OfflineModelRuntimeError(
            "repository fixture validation failed closed"
        ) from exc

    fixture_manifest = _read_json_object(
        resolved_fixture_manifest,
        context="fixture manifest",
    )
    input_name = _require_text(
        fixture_manifest,
        "inputName",
        context="fixture manifest",
    )
    fixture_input_path = _direct_child(
        resolved_fixture_root,
        input_name,
        context="fixture input",
    )
    if not fixture_input_path.is_file():
        raise OfflineModelRuntimeError("fixture input is missing")
    fixture_payload = fixture_input_path.read_bytes()
    if _sha256_bytes(fixture_payload) != fixture_result.input_sha256:
        raise OfflineModelRuntimeError("fixture input changed after validation")

    feature_values = (
        fixture_result.byte_length,
        fixture_result.line_count,
        fixture_payload.count(b"-"),
    )
    scores = loaded_model.score(feature_values)
    max_score = max(score for _, score in scores)
    winners = [label for label, score in scores if score == max_score]
    if len(winners) != 1:
        raise OfflineModelRuntimeError("offline test model produced an ambiguous tie")
    predicted_label = winners[0]

    features = tuple(zip(FEATURE_ORDER, feature_values, strict=True))
    canonical_payload = {
        "runtimeCoreVersion": RUNTIME_CORE_VERSION,
        "runtimeKind": RUNTIME_KIND,
        "modelId": loaded_model.model_id,
        "modelVersion": loaded_model.model_version,
        "modelSha256": loaded_model.artifact_sha256,
        "fixtureId": fixture_result.fixture_id,
        "fixtureVersion": fixture_result.fixture_version,
        "fixtureInputSha256": fixture_result.input_sha256,
        "features": {name: value for name, value in features},
        "scores": {label: score for label, score in scores},
        "predictedLabel": predicted_label,
    }

    return OfflineModelInferenceResult(
        model_id=loaded_model.model_id,
        model_version=loaded_model.model_version,
        model_sha256=loaded_model.artifact_sha256,
        fixture_id=fixture_result.fixture_id,
        fixture_version=fixture_result.fixture_version,
        fixture_input_sha256=fixture_result.input_sha256,
        features=features,
        scores=scores,
        predicted_label=predicted_label,
        output_sha256=_canonical_sha256(canonical_payload),
    )


def disabled_offline_model_runtime_evidence() -> dict[str, object]:
    return {
        "status": "pinned_offline_test_model_not_requested",
        "runtimeCoreVersion": RUNTIME_CORE_VERSION,
        "runtimeKind": RUNTIME_KIND,
        "offlineModelRuntimeEnabled": True,
        "repositoryTestModelOnly": True,
        "modelLoaded": False,
        "inferenceEnabled": False,
        "realOmrInference": False,
        "realOmrAccuracyMeasured": False,
        "generalAccuracyClaim": False,
        "userInputAccepted": False,
        "httpInferenceEnabled": False,
        "networkUsed": False,
        "gatewayIntegration": False,
        "ensembleIntegration": False,
        "productionEligible": False,
    }
