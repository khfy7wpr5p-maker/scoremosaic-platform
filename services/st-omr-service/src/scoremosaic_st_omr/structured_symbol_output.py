from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

SCHEMA_VERSION: Final = "1.0"
CONTRACT_VERSION: Final = "structured-synthetic-symbol-output-v1"
EXPECTED_DOCUMENT_ID: Final = "synthetic-symbol-output-v1"
EXPECTED_ARTIFACT_SHA256: Final = "78136ad2dda8addf74835a43b2071acc6d8fb093b0c8ded21ac61d8a7417a1e1"
ALLOWED_SYMBOL_TYPES: Final = (
    "staff", "measure", "clef", "time_signature", "notehead",
    "stem", "beam", "rest", "barline",
)
EXPECTED_FIXTURE: Final = {
    "fixtureId": "generated-single-staff",
    "fixtureVersion": "1.0.0",
    "inputSha256": "4c33aa3211217ddaa48da3eef4e9763a1ada0278699a35a2b939820e46036f5e",
}
EXPECTED_MODEL: Final = {
    "modelId": "st-omr-repository-test-linear",
    "modelVersion": "0.0.1",
    "modelSha256": "cb72738ab6f5d2ccf7b435b9aa99f4e2b82bf32da46df97424ccbae74211aaca",
    "repositoryTestOnly": True,
}
EXPECTED_BOUNDARIES: Final = {
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


class StructuredSymbolOutputError(ValueError):
    """Fail-closed error for the Phase 22 synthetic symbol contract."""


@dataclass(frozen=True)
class StructuredSymbolOutputEvidence:
    document_id: str
    symbol_count: int
    symbol_ids: tuple[str, ...]
    canonical_sha256: str
    canonical_bytes: bytes

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "validated_repository_synthetic_symbol_output",
            "contractVersion": CONTRACT_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "documentId": self.document_id,
            "symbolCount": self.symbol_count,
            "symbolIds": list(self.symbol_ids),
            "canonicalSha256": self.canonical_sha256,
            "immutableOutputEvidence": True,
            "byteIdenticalRepeatRequired": True,
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


def _read_object(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise StructuredSymbolOutputError("symbol artifact must be a real non-symlink file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StructuredSymbolOutputError("symbol artifact is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise StructuredSymbolOutputError("symbol artifact root must be an object")
    return payload


def _require_exact_keys(payload: dict[str, object], expected: set[str], context: str) -> None:
    if set(payload) != expected:
        raise StructuredSymbolOutputError(f"{context} fields do not match the closed schema")


def _bounded_integer(value: object, *, minimum: int, maximum: int, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise StructuredSymbolOutputError(f"{context} must be an integer")
    if not minimum <= value <= maximum:
        raise StructuredSymbolOutputError(f"{context} is outside the closed range")
    return value


def validate_structured_symbol_output(*, artifact_path: Path) -> StructuredSymbolOutputEvidence:
    payload = _read_object(artifact_path)
    _require_exact_keys(
        payload,
        {"schemaVersion", "documentId", "fixture", "model", "coordinateSpace", "symbols", "boundaries"},
        "symbol artifact",
    )
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise StructuredSymbolOutputError("unsupported symbol schema version")
    if payload.get("documentId") != EXPECTED_DOCUMENT_ID:
        raise StructuredSymbolOutputError("unexpected symbol document ID")
    if payload.get("fixture") != EXPECTED_FIXTURE:
        raise StructuredSymbolOutputError("fixture provenance is malformed")
    if payload.get("model") != EXPECTED_MODEL:
        raise StructuredSymbolOutputError("model provenance is malformed")
    if payload.get("boundaries") != EXPECTED_BOUNDARIES:
        raise StructuredSymbolOutputError("closed boundaries were changed")
    if payload.get("coordinateSpace") != {"unit": "integer-grid", "min": 0, "max": 4096}:
        raise StructuredSymbolOutputError("coordinate space does not match the closed contract")

    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 256:
        raise StructuredSymbolOutputError("symbols must be a bounded non-empty array")

    ids: list[str] = []
    previous_id = ""
    for index, symbol in enumerate(symbols):
        if not isinstance(symbol, dict):
            raise StructuredSymbolOutputError("each symbol must be an object")
        _require_exact_keys(symbol, {"id", "type", "bbox", "confidence"}, f"symbol {index}")
        symbol_id = symbol.get("id")
        if not isinstance(symbol_id, str) or not symbol_id:
            raise StructuredSymbolOutputError("symbol ID must be a non-empty string")
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
    digest = _sha256(canonical)
    if digest != EXPECTED_ARTIFACT_SHA256:
        raise StructuredSymbolOutputError("structured symbol artifact tampering detected")
    return StructuredSymbolOutputEvidence(
        document_id=EXPECTED_DOCUMENT_ID,
        symbol_count=len(ids),
        symbol_ids=tuple(ids),
        canonical_sha256=digest,
        canonical_bytes=canonical,
    )


def require_byte_identical_outputs(first: bytes, second: bytes) -> None:
    if first != second:
        raise StructuredSymbolOutputError("nondeterministic structured symbol output")


def disabled_structured_symbol_output_evidence() -> dict[str, object]:
    return {
        "status": "structured_synthetic_symbol_output_not_requested",
        "contractVersion": CONTRACT_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "repositorySyntheticOnly": True,
        "realOmrInference": False,
        "userInputAccepted": False,
        "httpInferenceEnabled": False,
        "musicXmlGenerated": False,
        "gatewayIntegration": False,
        "ensembleIntegration": False,
        "productionEligible": False,
    }
