from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

SCHEMA_VERSION: Final = "1.0"
CONTRACT_VERSION: Final = "structured-synthetic-symbol-output-v1"
MANIFEST_VERSION: Final = "1.0"
ALLOWED_CONTRACTS_ROOT_NAME: Final = "contracts"
ARTIFACT_PURPOSE: Final = "static_repository_synthetic_contract_sample"
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
ID_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SYMBOL_ID_PATTERN: Final = re.compile(r"^s[0-9]{3}$")
FIXTURE_VERSION_PATTERN: Final = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
MODEL_VERSION_PATTERN: Final = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ALLOWED_SYMBOL_TYPES: Final = (
    "staff",
    "measure",
    "clef",
    "time_signature",
    "notehead",
    "stem",
    "beam",
    "rest",
    "barline",
)
BOUNDARY_KEYS: Final = (
    "realOmrInference",
    "userInputAccepted",
    "httpInferenceEnabled",
    "musicXmlGenerated",
    "gatewayIntegration",
    "ensembleIntegration",
    "networkUsed",
    "gpuUsed",
    "persistentStorageUsed",
    "productionEligible",
)


class StructuredSymbolOutputError(ValueError):
    """Fail-closed error for the Phase 22 synthetic symbol contract."""


@dataclass(frozen=True)
class StructuredSymbolOutputEvidence:
    document_id: str
    symbol_count: int
    symbol_ids: tuple[str, ...]
    canonical_sha256: str
    artifact_sha256: str
    canonical_bytes: bytes

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "validated_static_repository_synthetic_contract_sample",
            "contractVersion": CONTRACT_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "documentId": self.document_id,
            "symbolCount": self.symbol_count,
            "symbolIds": list(self.symbol_ids),
            "canonicalSha256": self.canonical_sha256,
            "artifactSha256": self.artifact_sha256,
            "immutableOutputEvidence": True,
            "repeatedValidationAndCanonicalizationOnly": True,
            "symbolProducingModel": False,
            "realSymbolDetection": False,
            "musicalInterpretation": False,
            "inferenceAccuracyClaim": False,
            "realOmrInference": False,
            "userInputAccepted": False,
            "httpInferenceEnabled": False,
            "musicXmlGenerated": False,
            "gatewayIntegration": False,
            "ensembleIntegration": False,
            "networkUsed": False,
            "gpuUsed": False,
            "persistentStorageUsed": False,
            "productionEligible": False,
        }


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json_object(path: Path, *, context: str) -> tuple[dict[str, object], bytes]:
    if path.is_symlink() or not path.is_file():
        raise StructuredSymbolOutputError(f"{context} must be a real non-symlink file")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StructuredSymbolOutputError(f"{context} is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise StructuredSymbolOutputError(f"{context} root must be an object")
    return payload, raw


def _require_exact_keys(payload: dict[str, object], expected: set[str], context: str) -> None:
    if set(payload) != expected:
        raise StructuredSymbolOutputError(f"{context} fields do not match the closed schema")


def _require_pattern(value: object, pattern: re.Pattern[str], *, context: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or not pattern.fullmatch(value):
        raise StructuredSymbolOutputError(f"{context} does not match the closed string contract")
    return value


def _bounded_integer(value: object, *, minimum: int, maximum: int, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise StructuredSymbolOutputError(f"{context} must be an integer")
    if not minimum <= value <= maximum:
        raise StructuredSymbolOutputError(f"{context} is outside the closed range")
    return value


def _validate_root(root: Path) -> Path:
    if root.name != ALLOWED_CONTRACTS_ROOT_NAME:
        raise StructuredSymbolOutputError("allowed contracts root has an unexpected name")
    if root.is_symlink() or not root.is_dir():
        raise StructuredSymbolOutputError("allowed contracts root must be a real non-symlink directory")
    return root.resolve()


def _direct_child(path: Path, root: Path, *, context: str) -> Path:
    if path.is_symlink():
        raise StructuredSymbolOutputError(f"{context} symlinks are forbidden")
    resolved = path.resolve()
    if resolved.parent != root:
        raise StructuredSymbolOutputError(f"{context} must be a direct child of the allowed contracts root")
    if not resolved.is_file():
        raise StructuredSymbolOutputError(f"{context} is missing")
    return resolved


def validate_structured_symbol_contract(payload: dict[str, object]) -> tuple[str, tuple[str, ...], bytes, str]:
    """Validate the reusable closed schema and semantic rules without artifact pinning."""
    _require_exact_keys(
        payload,
        {"schemaVersion", "documentId", "fixture", "model", "coordinateSpace", "symbols", "boundaries"},
        "symbol contract",
    )
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise StructuredSymbolOutputError("unsupported symbol schema version")
    document_id = _require_pattern(payload.get("documentId"), ID_PATTERN, context="document ID", maximum=128)

    fixture = payload.get("fixture")
    if not isinstance(fixture, dict):
        raise StructuredSymbolOutputError("fixture provenance must be an object")
    _require_exact_keys(fixture, {"fixtureId", "fixtureVersion", "inputSha256"}, "fixture provenance")
    _require_pattern(fixture.get("fixtureId"), ID_PATTERN, context="fixture ID", maximum=128)
    _require_pattern(fixture.get("fixtureVersion"), FIXTURE_VERSION_PATTERN, context="fixture version", maximum=32)
    _require_pattern(fixture.get("inputSha256"), SHA256_PATTERN, context="fixture SHA-256", maximum=64)

    model = payload.get("model")
    if not isinstance(model, dict):
        raise StructuredSymbolOutputError("model provenance must be an object")
    _require_exact_keys(model, {"modelId", "modelVersion", "modelSha256", "repositoryTestOnly"}, "model provenance")
    _require_pattern(model.get("modelId"), ID_PATTERN, context="model ID", maximum=128)
    _require_pattern(model.get("modelVersion"), MODEL_VERSION_PATTERN, context="model version", maximum=32)
    _require_pattern(model.get("modelSha256"), SHA256_PATTERN, context="model SHA-256", maximum=64)
    if model.get("repositoryTestOnly") is not True:
        raise StructuredSymbolOutputError("model provenance must remain repository-test-only")

    coordinate_space = payload.get("coordinateSpace")
    if coordinate_space != {"unit": "integer-grid", "min": 0, "max": 4096}:
        raise StructuredSymbolOutputError("coordinate space does not match the closed contract")

    boundaries = payload.get("boundaries")
    if not isinstance(boundaries, dict):
        raise StructuredSymbolOutputError("boundaries must be an object")
    _require_exact_keys(boundaries, set(BOUNDARY_KEYS), "boundaries")
    if any(boundaries[key] is not False for key in BOUNDARY_KEYS):
        raise StructuredSymbolOutputError("all Phase 22 boundaries must remain false")

    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 256:
        raise StructuredSymbolOutputError("symbols must be a bounded non-empty array")

    ids: list[str] = []
    previous_id = ""
    for index, symbol in enumerate(symbols):
        if not isinstance(symbol, dict):
            raise StructuredSymbolOutputError("each symbol must be an object")
        _require_exact_keys(symbol, {"id", "type", "bbox", "confidence"}, f"symbol {index}")
        symbol_id = _require_pattern(symbol.get("id"), SYMBOL_ID_PATTERN, context="symbol ID", maximum=4)
        if symbol_id in ids:
            raise StructuredSymbolOutputError("duplicate symbol ID")
        if symbol_id <= previous_id:
            raise StructuredSymbolOutputError("symbols must use canonical ascending ID order")
        previous_id = symbol_id
        ids.append(symbol_id)

        if symbol.get("type") not in ALLOWED_SYMBOL_TYPES:
            raise StructuredSymbolOutputError("unknown symbol type")
        bbox = symbol.get("bbox")
        if not isinstance(bbox, dict):
            raise StructuredSymbolOutputError("symbol bbox must be an object")
        _require_exact_keys(bbox, {"x", "y", "width", "height"}, "symbol bbox")
        x = _bounded_integer(bbox.get("x"), minimum=0, maximum=4096, context="bbox x")
        y = _bounded_integer(bbox.get("y"), minimum=0, maximum=4096, context="bbox y")
        width = _bounded_integer(bbox.get("width"), minimum=1, maximum=4096, context="bbox width")
        height = _bounded_integer(bbox.get("height"), minimum=1, maximum=4096, context="bbox height")
        if x + width > 4096 or y + height > 4096:
            raise StructuredSymbolOutputError("symbol bbox exceeds the coordinate space")
        _bounded_integer(symbol.get("confidence"), minimum=0, maximum=1000, context="confidence")

    canonical = _canonical_bytes(payload)
    return document_id, tuple(ids), canonical, _sha256(canonical)


def verify_repository_structured_artifact(
    *,
    artifact_path: Path,
    manifest_path: Path,
    allowed_contracts_root: Path,
) -> StructuredSymbolOutputEvidence:
    """Verify repository ownership/pinning, then run the reusable contract validator."""
    root = _validate_root(allowed_contracts_root)
    resolved_manifest = _direct_child(manifest_path, root, context="artifact manifest")
    resolved_artifact = _direct_child(artifact_path, root, context="structured symbol artifact")

    manifest, _ = _read_json_object(resolved_manifest, context="artifact manifest")
    _require_exact_keys(
        manifest,
        {"manifestVersion", "artifactName", "artifactSha256", "canonicalSha256", "purpose"},
        "artifact manifest",
    )
    if manifest.get("manifestVersion") != MANIFEST_VERSION:
        raise StructuredSymbolOutputError("unsupported artifact manifest version")
    if manifest.get("purpose") != ARTIFACT_PURPOSE:
        raise StructuredSymbolOutputError("artifact purpose is not the static repository sample")
    artifact_name = manifest.get("artifactName")
    if not isinstance(artifact_name, str) or Path(artifact_name).name != artifact_name:
        raise StructuredSymbolOutputError("artifact name must be a direct-child file name")
    if artifact_name != resolved_artifact.name:
        raise StructuredSymbolOutputError("artifact path does not match the pinned manifest")
    artifact_sha256 = _require_pattern(
        manifest.get("artifactSha256"), SHA256_PATTERN, context="artifact SHA-256", maximum=64
    )
    canonical_sha256 = _require_pattern(
        manifest.get("canonicalSha256"), SHA256_PATTERN, context="canonical SHA-256", maximum=64
    )

    payload, raw = _read_json_object(resolved_artifact, context="structured symbol artifact")
    if _sha256(raw) != artifact_sha256:
        raise StructuredSymbolOutputError("repository structured artifact tampering detected")
    document_id, symbol_ids, canonical, actual_canonical_sha256 = validate_structured_symbol_contract(payload)
    if actual_canonical_sha256 != canonical_sha256:
        raise StructuredSymbolOutputError("repository canonical artifact hash mismatch")

    return StructuredSymbolOutputEvidence(
        document_id=document_id,
        symbol_count=len(symbol_ids),
        symbol_ids=symbol_ids,
        canonical_sha256=actual_canonical_sha256,
        artifact_sha256=artifact_sha256,
        canonical_bytes=canonical,
    )


def require_byte_identical_outputs(first: bytes, second: bytes) -> None:
    if first != second:
        raise StructuredSymbolOutputError("nondeterministic structured symbol output")


def disabled_structured_symbol_output_evidence() -> dict[str, object]:
    return {
        "status": "static_repository_synthetic_contract_sample_not_requested",
        "contractVersion": CONTRACT_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "repositorySyntheticOnly": True,
        "repeatedValidationAndCanonicalizationOnly": True,
        "symbolProducingModel": False,
        "realSymbolDetection": False,
        "musicalInterpretation": False,
        "inferenceAccuracyClaim": False,
        "realOmrInference": False,
        "userInputAccepted": False,
        "httpInferenceEnabled": False,
        "musicXmlGenerated": False,
        "gatewayIntegration": False,
        "ensembleIntegration": False,
        "productionEligible": False,
    }
