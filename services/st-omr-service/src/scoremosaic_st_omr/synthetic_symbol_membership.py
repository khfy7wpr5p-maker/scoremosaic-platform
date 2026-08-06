from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .json_schema_contract import JsonSchemaContractError, load_and_validate_json_schema_2020_12_subset

CONTRACT_VERSION: Final = "synthetic-symbol-membership-v1"
EXPECTED_SYMBOL_ARTIFACT_SHA256: Final = "78136ad2dda8addf74835a43b2071acc6d8fb093b0c8ded21ac61d8a7417a1e1"


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
    return (
        child["x"] >= parent["x"]
        and child["y"] >= parent["y"]
        and child["x"] + child["width"] <= parent["x"] + parent["width"]
        and child["y"] + child["height"] <= parent["y"] + parent["height"]
    )


def validate_synthetic_symbol_membership_contract(
    payload: dict[str, object], *, schema_path: Path, source_symbol_ids: set[str]
) -> SyntheticSymbolMembershipEvidence:
    try:
        load_and_validate_json_schema_2020_12_subset(payload, schema_path=schema_path)
    except JsonSchemaContractError as exc:
        raise SyntheticSymbolMembershipError(str(exc)) from exc

    if payload["symbolArtifact"] != {
        "documentId": "synthetic-symbol-output-v1",
        "canonicalSha256": EXPECTED_SYMBOL_ARTIFACT_SHA256,
    }:
        raise SyntheticSymbolMembershipError("symbol artifact provenance mismatch")

    staffs = payload["staffs"]
    measures = payload["measures"]
    memberships = payload["memberships"]
    staff_ids = [item["staffId"] for item in staffs]
    measure_ids = [item["measureId"] for item in measures]
    membership_symbol_ids = [item["symbolId"] for item in memberships]
    if staff_ids != sorted(staff_ids) or len(staff_ids) != len(set(staff_ids)):
        raise SyntheticSymbolMembershipError("staff IDs must be unique and canonically ordered")
    if measure_ids != sorted(measure_ids) or len(measure_ids) != len(set(measure_ids)):
        raise SyntheticSymbolMembershipError("measure IDs must be unique and canonically ordered")
    if membership_symbol_ids != sorted(membership_symbol_ids) or len(membership_symbol_ids) != len(set(membership_symbol_ids)):
        raise SyntheticSymbolMembershipError("membership symbol IDs must be unique and canonically ordered")
    if set(membership_symbol_ids) != source_symbol_ids:
        raise SyntheticSymbolMembershipError("membership set must exactly cover source symbols")

    staff_by_id = {item["staffId"]: item for item in staffs}
    measure_by_id = {item["measureId"]: item for item in measures}
    for measure in measures:
        staff = staff_by_id.get(measure["staffId"])
        if staff is None or not _bbox_inside(measure["bbox"], staff["bbox"]):
            raise SyntheticSymbolMembershipError("measure must reference and fit within its staff")
    for membership in memberships:
        if membership["staffId"] not in staff_by_id:
            raise SyntheticSymbolMembershipError("membership references unknown staff")
        measure_id = membership.get("measureId")
        if measure_id is not None:
            measure = measure_by_id.get(measure_id)
            if measure is None or measure["staffId"] != membership["staffId"]:
                raise SyntheticSymbolMembershipError("membership references inconsistent measure")

    canonical = _canonical(payload)
    return SyntheticSymbolMembershipEvidence(
        staff_ids=tuple(staff_ids),
        measure_ids=tuple(measure_ids),
        symbol_ids=tuple(membership_symbol_ids),
        canonical_sha256=_sha256(canonical),
        canonical_bytes=canonical,
    )


def verify_repository_synthetic_membership(
    *, artifact_path: Path, manifest_path: Path, schema_path: Path,
    source_symbol_artifact_path: Path, allowed_contracts_root: Path,
) -> SyntheticSymbolMembershipEvidence:
    root = allowed_contracts_root.resolve(strict=True)
    if root.name != "contracts":
        raise SyntheticSymbolMembershipError("allowed root must be named contracts")
    for path in (artifact_path, manifest_path, schema_path, source_symbol_artifact_path):
        if path.is_symlink() or path.parent.resolve(strict=True) != root:
            raise SyntheticSymbolMembershipError("contract files must be direct non-symlink children of allowed root")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != {
        "manifestVersion": "1.0",
        "artifactName": "synthetic-symbol-membership-v1.synthetic.json",
        "artifactSha256": "8a623a3e6f9cb65bc554baee62bc27be19cbd14afcf998c6ddb33feff7812abc",
        "canonicalSha256": "40265a4a65808dd1f41396e8b72fde2f35358ed1a00073c298a056e9ee956f2c",
        "schemaName": "synthetic-symbol-membership-v1.schema.json",
        "purpose": "static_repository_synthetic_membership_sample",
    }:
        raise SyntheticSymbolMembershipError("membership manifest mismatch")
    raw = artifact_path.read_bytes()
    if _sha256(raw) != manifest["artifactSha256"]:
        raise SyntheticSymbolMembershipError("membership artifact tampering detected")
    payload = json.loads(raw)
    source_payload = json.loads(source_symbol_artifact_path.read_text(encoding="utf-8"))
    source_ids = {item["id"] for item in source_payload["symbols"]}
    evidence = validate_synthetic_symbol_membership_contract(payload, schema_path=schema_path, source_symbol_ids=source_ids)
    if evidence.canonical_sha256 != manifest["canonicalSha256"]:
        raise SyntheticSymbolMembershipError("membership canonical hash mismatch")
    return evidence


def disabled_synthetic_membership_evidence() -> dict[str, object]:
    return {
        "status": "synthetic_membership_not_requested",
        "contractVersion": CONTRACT_VERSION,
        "staticRepositorySampleOnly": True,
        "realSymbolDetection": False,
        "musicalInterpretation": False,
        "productionEligible": False,
    }
