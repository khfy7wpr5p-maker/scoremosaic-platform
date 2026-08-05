from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.json_schema_contract import (
    JsonSchemaContractError,
    load_and_validate_json_schema_2020_12_subset,
)
from scoremosaic_st_omr.structured_symbol_output import (
    StructuredSymbolOutputError,
    require_byte_identical_outputs,
    validate_structured_symbol_contract,
    verify_repository_structured_artifact,
)


class StructuredSymbolOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service_root = Path(__file__).resolve().parents[1]
        cls.contracts = cls.service_root / "contracts"
        cls.artifact = cls.contracts / "structured-symbol-output-v1.synthetic.json"
        cls.manifest = cls.contracts / "structured-symbol-output-v1.manifest.json"
        cls.schema = cls.contracts / "structured-symbol-output-v1.schema.json"
        cls.payload = json.loads(cls.artifact.read_text(encoding="utf-8"))

    def _payload(self) -> dict[str, object]:
        return copy.deepcopy(self.payload)

    def _validate_payload(self, payload: dict[str, object]) -> None:
        validate_structured_symbol_contract(payload)

    def _schema_validate(self, payload: dict[str, object]) -> None:
        load_and_validate_json_schema_2020_12_subset(payload, schema_path=self.schema)

    def _temporary_contracts(self) -> tuple[Path, Path, Path]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name) / "contracts"
        root.mkdir()
        artifact = root / self.artifact.name
        manifest = root / self.manifest.name
        artifact.write_bytes(self.artifact.read_bytes())
        manifest.write_bytes(self.manifest.read_bytes())
        return root, artifact, manifest

    def test_repository_artifact_is_pinned_and_deterministic(self) -> None:
        kwargs = {
            "artifact_path": self.artifact,
            "manifest_path": self.manifest,
            "allowed_contracts_root": self.contracts,
        }
        first = verify_repository_structured_artifact(**kwargs)
        second = verify_repository_structured_artifact(**kwargs)
        require_byte_identical_outputs(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first, second)
        self.assertEqual(first.symbol_count, 9)
        self.assertEqual(first.canonical_sha256, "78136ad2dda8addf74835a43b2071acc6d8fb093b0c8ded21ac61d8a7417a1e1")
        self.assertEqual(first.artifact_sha256, "7bf31d00787a07fac099f244591ec7eb2798c9c56ee73b0f53de165e02266476")

    def test_general_contract_validator_is_not_bound_to_sample_hash(self) -> None:
        payload = self._payload()
        payload["documentId"] = "another-static-sample"
        document_id, symbol_ids, canonical, digest = validate_structured_symbol_contract(payload)
        self.assertEqual(document_id, "another-static-sample")
        self.assertEqual(len(symbol_ids), 9)
        self.assertEqual(len(digest), 64)
        self.assertTrue(canonical)

    def test_duplicate_symbol_id_fails_closed(self) -> None:
        payload = self._payload()
        payload["symbols"][1]["id"] = payload["symbols"][0]["id"]
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_unknown_symbol_type_fails_closed(self) -> None:
        payload = self._payload()
        payload["symbols"][0]["type"] = "unknown"
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_invalid_coordinate_fails_closed(self) -> None:
        payload = self._payload()
        payload["symbols"][0]["bbox"]["x"] = 4097
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_invalid_confidence_fails_closed(self) -> None:
        payload = self._payload()
        payload["symbols"][0]["confidence"] = 1001
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_broken_fixture_provenance_fails_closed(self) -> None:
        payload = self._payload()
        payload["fixture"]["inputSha256"] = "not-a-sha"
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_broken_model_provenance_fails_closed(self) -> None:
        payload = self._payload()
        payload["model"]["repositoryTestOnly"] = False
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_order_change_fails_closed(self) -> None:
        payload = self._payload()
        payload["symbols"][0], payload["symbols"][1] = payload["symbols"][1], payload["symbols"][0]
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_schema_version_mismatch_fails_closed(self) -> None:
        payload = self._payload()
        payload["schemaVersion"] = "2.0"
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_missing_required_field_fails_closed(self) -> None:
        payload = self._payload()
        del payload["symbols"][0]["confidence"]
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_nested_additional_property_fails_closed(self) -> None:
        payload = self._payload()
        payload["fixture"]["extra"] = False
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_malformed_symbol_object_fails_closed(self) -> None:
        payload = self._payload()
        payload["symbols"][0]["unexpected"] = 1
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_malformed_bbox_object_fails_closed(self) -> None:
        payload = self._payload()
        payload["symbols"][0]["bbox"]["unexpected"] = 1
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_malformed_boundaries_object_fails_closed(self) -> None:
        payload = self._payload()
        payload["boundaries"]["networkUsed"] = True
        with self.assertRaises(StructuredSymbolOutputError):
            self._validate_payload(payload)

    def test_artifact_tampering_fails_closed(self) -> None:
        root, artifact, manifest = self._temporary_contracts()
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        payload["symbols"][0]["confidence"] = 999
        artifact.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(StructuredSymbolOutputError):
            verify_repository_structured_artifact(
                artifact_path=artifact,
                manifest_path=manifest,
                allowed_contracts_root=root,
            )

    def test_artifact_outside_allowed_root_fails_closed(self) -> None:
        root, _, manifest = self._temporary_contracts()
        outside = root.parent / "outside.json"
        outside.write_bytes(self.artifact.read_bytes())
        with self.assertRaises(StructuredSymbolOutputError):
            verify_repository_structured_artifact(
                artifact_path=outside,
                manifest_path=manifest,
                allowed_contracts_root=root,
            )

    def test_path_escape_fails_closed(self) -> None:
        root, artifact, manifest = self._temporary_contracts()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["artifactName"] = "../structured-symbol-output-v1.synthetic.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(StructuredSymbolOutputError):
            verify_repository_structured_artifact(
                artifact_path=artifact,
                manifest_path=manifest,
                allowed_contracts_root=root,
            )

    def test_symlink_artifact_fails_closed(self) -> None:
        root, artifact, manifest = self._temporary_contracts()
        target = root / "target.json"
        artifact.rename(target)
        os.symlink(target, artifact)
        with self.assertRaises(StructuredSymbolOutputError):
            verify_repository_structured_artifact(
                artifact_path=artifact,
                manifest_path=manifest,
                allowed_contracts_root=root,
            )

    def test_wrong_root_name_fails_closed(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name) / "wrong-root"
        root.mkdir()
        artifact = root / self.artifact.name
        manifest = root / self.manifest.name
        artifact.write_bytes(self.artifact.read_bytes())
        manifest.write_bytes(self.manifest.read_bytes())
        with self.assertRaises(StructuredSymbolOutputError):
            verify_repository_structured_artifact(
                artifact_path=artifact,
                manifest_path=manifest,
                allowed_contracts_root=root,
            )

    def test_nondeterministic_output_fails_closed(self) -> None:
        with self.assertRaises(StructuredSymbolOutputError):
            require_byte_identical_outputs(b"first", b"second")

    def test_canonical_artifact_passes_executed_schema(self) -> None:
        self._schema_validate(self._payload())

    def test_schema_rejects_nested_extra_field(self) -> None:
        payload = self._payload()
        payload["model"]["extra"] = False
        with self.assertRaises(JsonSchemaContractError):
            self._schema_validate(payload)

    def test_schema_rejects_unknown_symbol(self) -> None:
        payload = self._payload()
        payload["symbols"][0]["type"] = "unknown"
        with self.assertRaises(JsonSchemaContractError):
            self._schema_validate(payload)

    def test_schema_rejects_invalid_coordinate(self) -> None:
        payload = self._payload()
        payload["symbols"][0]["bbox"]["x"] = -1
        with self.assertRaises(JsonSchemaContractError):
            self._schema_validate(payload)

    def test_schema_rejects_invalid_confidence(self) -> None:
        payload = self._payload()
        payload["symbols"][0]["confidence"] = 1001
        with self.assertRaises(JsonSchemaContractError):
            self._schema_validate(payload)

    def test_schema_rejects_missing_field(self) -> None:
        payload = self._payload()
        del payload["fixture"]["fixtureVersion"]
        with self.assertRaises(JsonSchemaContractError):
            self._schema_validate(payload)


if __name__ == "__main__":
    unittest.main()
