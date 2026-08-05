from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.structured_symbol_output import (
    EXPECTED_ARTIFACT_SHA256,
    StructuredSymbolOutputError,
    require_byte_identical_outputs,
    validate_structured_symbol_output,
)


class StructuredSymbolOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service_root = Path(__file__).resolve().parents[1]
        cls.artifact = cls.service_root / "contracts" / "structured-symbol-output-v1.synthetic.json"
        cls.payload = json.loads(cls.artifact.read_text(encoding="utf-8"))

    def _write(self, payload: dict[str, object]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "artifact.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_artifact_is_deterministic(self) -> None:
        first = validate_structured_symbol_output(artifact_path=self.artifact)
        second = validate_structured_symbol_output(artifact_path=self.artifact)
        require_byte_identical_outputs(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first, second)
        self.assertEqual(first.symbol_count, 9)
        self.assertEqual(first.canonical_sha256, EXPECTED_ARTIFACT_SHA256)

    def test_duplicate_symbol_id_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["symbols"][1]["id"] = payload["symbols"][0]["id"]
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_unknown_symbol_type_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["symbols"][0]["type"] = "unknown"
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_invalid_coordinate_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["symbols"][0]["bbox"]["x"] = 4097
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_invalid_confidence_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["symbols"][0]["confidence"] = 1001
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_broken_fixture_provenance_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["fixture"]["fixtureId"] = "other"
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_broken_model_provenance_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["model"]["repositoryTestOnly"] = False
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_order_change_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["symbols"][0], payload["symbols"][1] = payload["symbols"][1], payload["symbols"][0]
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_schema_version_mismatch_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["schemaVersion"] = "2.0"
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_missing_required_field_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        del payload["symbols"][0]["confidence"]
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_artifact_tampering_fails_closed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["symbols"][0]["confidence"] = 999
        with self.assertRaises(StructuredSymbolOutputError):
            validate_structured_symbol_output(artifact_path=self._write(payload))

    def test_nondeterministic_output_fails_closed(self) -> None:
        with self.assertRaises(StructuredSymbolOutputError):
            require_byte_identical_outputs(b"first", b"second")


if __name__ == "__main__":
    unittest.main()
