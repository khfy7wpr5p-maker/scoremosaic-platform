from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .json_schema_contract import JsonSchemaContractError, load_and_validate_json_schema_2020_12_subset
from .synthetic_symbol_membership import SyntheticSymbolMembershipError, verify_repository_synthetic_membership

CONTRACT_VERSION: Final = "synthetic-reading-order-v1"
MANIFEST_FIELDS: Final = {
    "manifestVersion", "artifactName", "artifactSha256", "canonicalSha256",
    "schemaName", "schemaSha256", "sourceArtifactName", "sourceManifestName",
    "sourceSchemaName", "sourceCanonicalSha256", "purpose",
}
PURPOSE: Final = "static_repository_synthetic_reading_order_sample"


class SyntheticReadingOrderError(ValueError):
    """Fail-closed error for the Phase 24 static reading-order contract."""


@dataclass(frozen=True)
class SyntheticReadingOrderEvidence:
    staff_ids: tuple[str, ...]
    measure_ids: tuple[str, ...]
    symbol_ids: tuple[str, ...]
    canonical_sha256: str
    canonical_bytes: bytes

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "validated_static_repository_synthetic_reading_order",
            "contractVersion": CONTRACT_VERSION,
            "staffOrderCount": len(self.staff_ids),
            "measureOrderCount": len(self.measure_ids),
            "symbolCount": len(self.symbol_ids),
            "canonicalSha256": self.canonical_sha256,
            "staticRepositorySampleOnly": True,
            "realOmr": False,
            "userInput": False,
            "musicalInterpretation": False,
            "productionEligible": False,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _closed_file(path: Path, root: Path, context: str) -> Path:
    if path.is_symlink():
        raise SyntheticReadingOrderError(f"{context} symlink is forbidden")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise SyntheticReadingOrderError(f"{context} is missing") from exc
    if not resolved.is_file() or resolved.parent != root:
        raise SyntheticReadingOrderError(f"{context} must be a direct file child of contracts")
    return resolved


def _read_json(path: Path, context: str) -> tuple[dict[str, object], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SyntheticReadingOrderError(f"{context} is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise SyntheticReadingOrderError(f"{context} root must be an object")
    return payload, raw


def validate_synthetic_reading_order_contract(
    payload: dict[str, object], *, schema_path: Path,
    membership_payload: dict[str, object], membership_canonical_sha256: str,
) -> SyntheticReadingOrderEvidence:
    """Validate reusable reading-order schema and semantics without repository hash pinning."""
    try:
        load_and_validate_json_schema_2020_12_subset(payload, schema_path=schema_path)
        if payload["membershipArtifact"] != {
            "documentId": "synthetic-symbol-membership-v1",
            "canonicalSha256": membership_canonical_sha256,
        }:
            raise SyntheticReadingOrderError("membership provenance mismatch")

        memberships = membership_payload["memberships"]
        membership_by_symbol = {item["symbolId"]: item for item in memberships}
        if len(membership_by_symbol) != len(memberships):
            raise SyntheticReadingOrderError("duplicate membership symbol ID")
        staff_ids = {item["staffId"] for item in membership_payload["staffs"]}
        measure_to_staff = {item["measureId"]: item["staffId"] for item in membership_payload["measures"]}

        staff_orders = payload["staffOrders"]
        measure_orders = payload["measureOrders"]
        ordered_staff_ids = [item["staffId"] for item in staff_orders]
        ordered_measure_ids = [item["measureId"] for item in measure_orders]
        if ordered_staff_ids != sorted(ordered_staff_ids) or len(ordered_staff_ids) != len(set(ordered_staff_ids)):
            raise SyntheticReadingOrderError("staff orders must be unique and canonical")
        if ordered_measure_ids != sorted(ordered_measure_ids) or len(ordered_measure_ids) != len(set(ordered_measure_ids)):
            raise SyntheticReadingOrderError("measure orders must be unique and canonical")

        all_symbols: list[str] = []
        for order in staff_orders:
            if order["staffId"] not in staff_ids:
                raise SyntheticReadingOrderError("unknown staff order")
            symbols = order["symbolIds"]
            if len(symbols) != len(set(symbols)):
                raise SyntheticReadingOrderError("duplicate symbol in staff order")
            for symbol_id in symbols:
                membership = membership_by_symbol.get(symbol_id)
                if membership is None or membership["staffId"] != order["staffId"] or membership.get("measureId") is not None:
                    raise SyntheticReadingOrderError("staff order symbol violates membership")
            all_symbols.extend(symbols)

        for order in measure_orders:
            measure_id = order["measureId"]
            staff_id = order["staffId"]
            if measure_to_staff.get(measure_id) != staff_id:
                raise SyntheticReadingOrderError("measure order crosses staff boundary")
            symbols = order["symbolIds"]
            if len(symbols) != len(set(symbols)):
                raise SyntheticReadingOrderError("duplicate symbol in measure order")
            for symbol_id in symbols:
                membership = membership_by_symbol.get(symbol_id)
                if membership is None or membership["staffId"] != staff_id or membership.get("measureId") != measure_id:
                    raise SyntheticReadingOrderError("measure order symbol violates membership")
            all_symbols.extend(symbols)

        if len(all_symbols) != len(set(all_symbols)):
            raise SyntheticReadingOrderError("symbol appears in more than one reading-order record")
        if set(all_symbols) != set(membership_by_symbol):
            raise SyntheticReadingOrderError("reading order must cover every membership symbol exactly once")

        canonical = _canonical(payload)
        return SyntheticReadingOrderEvidence(
            tuple(ordered_staff_ids), tuple(ordered_measure_ids), tuple(all_symbols),
            _sha256(canonical), canonical,
        )
    except SyntheticReadingOrderError:
        raise
    except (JsonSchemaContractError, KeyError, TypeError, IndexError) as exc:
        raise SyntheticReadingOrderError("reading-order contract is malformed") from exc


def verify_repository_synthetic_reading_order(
    *, artifact_path: Path, manifest_path: Path, schema_path: Path,
    membership_artifact_path: Path, membership_manifest_path: Path, membership_schema_path: Path,
    structured_artifact_path: Path, structured_manifest_path: Path,
    allowed_contracts_root: Path,
) -> SyntheticReadingOrderEvidence:
    """Verify repository pins and the complete Phase 23 trust chain before accepting order."""
    try:
        if allowed_contracts_root.is_symlink() or allowed_contracts_root.name != "contracts" or not allowed_contracts_root.is_dir():
            raise SyntheticReadingOrderError("allowed root must be a real non-symlink contracts directory")
        root = allowed_contracts_root.resolve(strict=True)
        files = {
            "artifact": _closed_file(artifact_path, root, "reading-order artifact"),
            "manifest": _closed_file(manifest_path, root, "reading-order manifest"),
            "schema": _closed_file(schema_path, root, "reading-order schema"),
            "sourceArtifact": _closed_file(membership_artifact_path, root, "membership artifact"),
            "sourceManifest": _closed_file(membership_manifest_path, root, "membership manifest"),
            "sourceSchema": _closed_file(membership_schema_path, root, "membership schema"),
            "structuredArtifact": _closed_file(structured_artifact_path, root, "structured source artifact"),
            "structuredManifest": _closed_file(structured_manifest_path, root, "structured source manifest"),
        }
        manifest, _ = _read_json(files["manifest"], "reading-order manifest")
        if set(manifest) != MANIFEST_FIELDS or manifest.get("manifestVersion") != "1.0" or manifest.get("purpose") != PURPOSE:
            raise SyntheticReadingOrderError("reading-order manifest mismatch")
        expected_names = {
            "artifact": manifest["artifactName"], "schema": manifest["schemaName"],
            "sourceArtifact": manifest["sourceArtifactName"], "sourceManifest": manifest["sourceManifestName"],
            "sourceSchema": manifest["sourceSchemaName"],
        }
        for key, name in expected_names.items():
            if not isinstance(name, str) or Path(name).name != name or files[key].name != name:
                raise SyntheticReadingOrderError("manifest file name mismatch")
        if _sha256(files["schema"].read_bytes()) != manifest["schemaSha256"]:
            raise SyntheticReadingOrderError("reading-order schema hash mismatch")
        payload, raw = _read_json(files["artifact"], "reading-order artifact")
        if _sha256(raw) != manifest["artifactSha256"]:
            raise SyntheticReadingOrderError("reading-order artifact tampering detected")

        membership_evidence = verify_repository_synthetic_membership(
            artifact_path=files["sourceArtifact"], manifest_path=files["sourceManifest"],
            schema_path=files["sourceSchema"], source_symbol_artifact_path=files["structuredArtifact"],
            source_symbol_manifest_path=files["structuredManifest"], allowed_contracts_root=root,
        )
        if membership_evidence.canonical_sha256 != manifest["sourceCanonicalSha256"]:
            raise SyntheticReadingOrderError("membership canonical hash mismatch")
        membership_payload, _ = _read_json(files["sourceArtifact"], "verified membership artifact")
        evidence = validate_synthetic_reading_order_contract(
            payload, schema_path=files["schema"], membership_payload=membership_payload,
            membership_canonical_sha256=membership_evidence.canonical_sha256,
        )
        if evidence.canonical_sha256 != manifest["canonicalSha256"]:
            raise SyntheticReadingOrderError("reading-order canonical hash mismatch")
        return evidence
    except SyntheticReadingOrderError:
        raise
    except (SyntheticSymbolMembershipError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise SyntheticReadingOrderError("repository reading-order verification failed closed") from exc


def require_byte_identical_reading_orders(first: bytes, second: bytes) -> None:
    if first != second:
        raise SyntheticReadingOrderError("reading-order output is nondeterministic")


def disabled_synthetic_reading_order_evidence() -> dict[str, object]:
    return {
        "status": "synthetic_reading_order_not_requested",
        "contractVersion": CONTRACT_VERSION,
        "staticRepositorySampleOnly": True,
        "realOmr": False,
        "userInput": False,
        "productionEligible": False,
    }
