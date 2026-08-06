from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .json_schema_contract import JsonSchemaContractError, load_and_validate_json_schema_2020_12_subset
from .structured_symbol_output import StructuredSymbolOutputError, verify_repository_structured_artifact

CONTRACT_VERSION: Final = "synthetic-symbol-membership-v1"
MANIFEST_VERSION: Final = "1.0"
PURPOSE: Final = "static_repository_synthetic_membership_sample"
MANIFEST_FIELDS: Final = {
    "manifestVersion", "artifactName", "artifactSha256", "canonicalSha256",
    "schemaName", "schemaSha256", "sourceArtifactName", "sourceManifestName",
    "sourceCanonicalSha256", "purpose",
}


class SyntheticSymbolMembershipError(ValueError):
    """Fail-closed error for the Phase 23 static membership contract."""


@dataclass(frozen=True)
class SyntheticSymbolMembershipEvidence:
    staff_ids: tuple[str, ...]
    measure_ids: tuple[str, ...]
    symbol_ids: tuple[str, ...]
    canonical_sha256: str
    canonical_bytes: bytes

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "validated_static_repository_synthetic_membership",
            "contractVersion": CONTRACT_VERSION,
            "staffCount": len(self.staff_ids),
            "measureCount": len(self.measure_ids),
            "membershipCount": len(self.symbol_ids),
            "canonicalSha256": self.canonical_sha256,
            "staticRepositorySampleOnly": True,
            "symbolProducingModel": False,
            "realSymbolDetection": False,
            "musicalInterpretation": False,
            "pitchAssigned": False,
            "durationAssigned": False,
            "voiceAssigned": False,
            "attachmentRelations": False,
            "beamMembership": False,
            "readingOrderSemantics": False,
            "notationGraph": False,
            "musicXmlGenerated": False,
            "productionEligible": False,
        }


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bbox_inside(child: dict[str, int], parent: dict[str, int]) -> bool:
    return child["x"] >= parent["x"] and child["y"] >= parent["y"] and child["x"] + child["width"] <= parent["x"] + parent["width"] and child["y"] + child["height"] <= parent["y"] + parent["height"]


def _closed_file(path: Path, root: Path, context: str) -> Path:
    if path.is_symlink():
        raise SyntheticSymbolMembershipError(f"{context} symlink is forbidden")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise SyntheticSymbolMembershipError(f"{context} is missing") from exc
    if resolved.parent != root or not resolved.is_file():
        raise SyntheticSymbolMembershipError(f"{context} must be a direct file child of contracts")
    return resolved


def _read_json(path: Path, context: str) -> tuple[dict[str, object], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SyntheticSymbolMembershipError(f"{context} is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise SyntheticSymbolMembershipError(f"{context} root must be an object")
    return payload, raw


def validate_synthetic_symbol_membership_contract(
    payload: dict[str, object], *, schema_path: Path,
    source_symbols: dict[str, dict[str, object]], source_canonical_sha256: str,
) -> SyntheticSymbolMembershipEvidence:
    """Validate reusable membership schema/semantics without repository hash pinning."""
    try:
        load_and_validate_json_schema_2020_12_subset(payload, schema_path=schema_path)
        if payload["symbolArtifact"] != {"documentId": "synthetic-symbol-output-v1", "canonicalSha256": source_canonical_sha256}:
            raise SyntheticSymbolMembershipError("source artifact provenance mismatch")
        staffs = payload["staffs"]
        measures = payload["measures"]
        memberships = payload["memberships"]
        staff_ids = [item["staffId"] for item in staffs]
        measure_ids = [item["measureId"] for item in measures]
        symbol_ids = [item["symbolId"] for item in memberships]
        if staff_ids != sorted(staff_ids) or len(staff_ids) != len(set(staff_ids)):
            raise SyntheticSymbolMembershipError("staff IDs must be unique and ordered")
        if measure_ids != sorted(measure_ids) or len(measure_ids) != len(set(measure_ids)):
            raise SyntheticSymbolMembershipError("measure IDs must be unique and ordered")
        if symbol_ids != sorted(symbol_ids) or len(symbol_ids) != len(set(symbol_ids)):
            raise SyntheticSymbolMembershipError("membership symbols must be unique and ordered")
        if set(symbol_ids) != set(source_symbols):
            raise SyntheticSymbolMembershipError("memberships must cover every source symbol exactly once")
        lineage = [item["sourceSymbolId"] for item in staffs] + [item["sourceSymbolId"] for item in measures]
        if len(lineage) != len(set(lineage)):
            raise SyntheticSymbolMembershipError("staff/measure sourceSymbolId values must be unique")
        staff_by_id = {item["staffId"]: item for item in staffs}
        measure_by_id = {item["measureId"]: item for item in measures}
        for staff in staffs:
            source = source_symbols.get(staff["sourceSymbolId"])
            if source is None or source["type"] != "staff" or source["bbox"] != staff["bbox"]:
                raise SyntheticSymbolMembershipError("staff lineage type or bbox mismatch")
        for measure in measures:
            source = source_symbols.get(measure["sourceSymbolId"])
            staff = staff_by_id.get(measure["staffId"])
            if source is None or source["type"] != "measure" or source["bbox"] != measure["bbox"]:
                raise SyntheticSymbolMembershipError("measure lineage type or bbox mismatch")
            if staff is None or not _bbox_inside(measure["bbox"], staff["bbox"]):
                raise SyntheticSymbolMembershipError("measure must fit within its staff")
        for membership in memberships:
            source = source_symbols[membership["symbolId"]]
            staff = staff_by_id.get(membership["staffId"])
            if staff is None or not _bbox_inside(source["bbox"], staff["bbox"]):
                raise SyntheticSymbolMembershipError("symbol must fit within assigned staff")
            measure_id = membership.get("measureId")
            if measure_id is not None:
                measure = measure_by_id.get(measure_id)
                if measure is None or measure["staffId"] != membership["staffId"] or not _bbox_inside(source["bbox"], measure["bbox"]):
                    raise SyntheticSymbolMembershipError("symbol must fit within referenced measure")
        canonical = _canonical(payload)
        return SyntheticSymbolMembershipEvidence(tuple(staff_ids), tuple(measure_ids), tuple(symbol_ids), _sha256(canonical), canonical)
    except SyntheticSymbolMembershipError:
        raise
    except (JsonSchemaContractError, KeyError, TypeError, IndexError) as exc:
        raise SyntheticSymbolMembershipError("membership contract is malformed") from exc


def verify_repository_synthetic_membership(
    *, artifact_path: Path, manifest_path: Path, schema_path: Path,
    source_symbol_artifact_path: Path, source_symbol_manifest_path: Path,
    allowed_contracts_root: Path,
) -> SyntheticSymbolMembershipEvidence:
    """Verify repository pinning and the Phase 22 source chain, then validate membership."""
    try:
        if allowed_contracts_root.is_symlink() or allowed_contracts_root.name != "contracts" or not allowed_contracts_root.is_dir():
            raise SyntheticSymbolMembershipError("allowed root must be a real non-symlink contracts directory")
        root = allowed_contracts_root.resolve(strict=True)
        artifact = _closed_file(artifact_path, root, "membership artifact")
        manifest_file = _closed_file(manifest_path, root, "membership manifest")
        schema = _closed_file(schema_path, root, "membership schema")
        source_artifact = _closed_file(source_symbol_artifact_path, root, "source artifact")
        source_manifest = _closed_file(source_symbol_manifest_path, root, "source manifest")
        manifest, _ = _read_json(manifest_file, "membership manifest")
        if set(manifest) != MANIFEST_FIELDS or manifest.get("manifestVersion") != MANIFEST_VERSION or manifest.get("purpose") != PURPOSE:
            raise SyntheticSymbolMembershipError("membership manifest mismatch")
        names = {
            artifact: manifest["artifactName"], schema: manifest["schemaName"],
            source_artifact: manifest["sourceArtifactName"], source_manifest: manifest["sourceManifestName"],
        }
        if any(not isinstance(name, str) or Path(name).name != name or path.name != name for path, name in names.items()):
            raise SyntheticSymbolMembershipError("manifest file name mismatch")
        if _sha256(schema.read_bytes()) != manifest["schemaSha256"]:
            raise SyntheticSymbolMembershipError("membership schema hash mismatch")
        payload, raw = _read_json(artifact, "membership artifact")
        if _sha256(raw) != manifest["artifactSha256"]:
            raise SyntheticSymbolMembershipError("membership artifact tampering detected")
        source_evidence = verify_repository_structured_artifact(
            artifact_path=source_artifact, manifest_path=source_manifest, allowed_contracts_root=root
        )
        if source_evidence.canonical_sha256 != manifest["sourceCanonicalSha256"]:
            raise SyntheticSymbolMembershipError("source canonical hash mismatch")
        source_payload, _ = _read_json(source_artifact, "verified source artifact")
        source_symbols = {item["id"]: {"type": item["type"], "bbox": item["bbox"]} for item in source_payload["symbols"]}
        if len(source_symbols) != len(source_payload["symbols"]):
            raise SyntheticSymbolMembershipError("duplicate source symbol ID")
        evidence = validate_synthetic_symbol_membership_contract(
            payload, schema_path=schema, source_symbols=source_symbols,
            source_canonical_sha256=source_evidence.canonical_sha256,
        )
        if evidence.canonical_sha256 != manifest["canonicalSha256"]:
            raise SyntheticSymbolMembershipError("membership canonical hash mismatch")
        return evidence
    except SyntheticSymbolMembershipError:
        raise
    except (StructuredSymbolOutputError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise SyntheticSymbolMembershipError("repository membership verification failed closed") from exc


def disabled_synthetic_membership_evidence() -> dict[str, object]:
    return {"status": "synthetic_membership_not_requested", "contractVersion": CONTRACT_VERSION, "staticRepositorySampleOnly": True, "realSymbolDetection": False, "musicalInterpretation": False, "productionEligible": False}
