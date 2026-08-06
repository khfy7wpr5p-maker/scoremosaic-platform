from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.synthetic_symbol_membership import (
    SyntheticSymbolMembershipError,
    validate_synthetic_symbol_membership_contract,
    verify_repository_synthetic_membership,
)


class SyntheticSymbolMembershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.contracts = cls.root / "contracts"
        cls.schema = cls.contracts / "synthetic-symbol-membership-v1.schema.json"
        cls.artifact = cls.contracts / "synthetic-symbol-membership-v1.synthetic.json"
        cls.manifest = cls.contracts / "synthetic-symbol-membership-v1.manifest.json"
        cls.source = cls.contracts / "structured-symbol-output-v1.synthetic.json"
        cls.payload = json.loads(cls.artifact.read_text(encoding="utf-8"))
        cls.source_ids = {item["id"] for item in json.loads(cls.source.read_text())["symbols"]}

    def test_repository_membership_is_pinned_and_deterministic(self) -> None:
        kwargs = dict(artifact_path=self.artifact, manifest_path=self.manifest, schema_path=self.schema,
                      source_symbol_artifact_path=self.source, allowed_contracts_root=self.contracts)
        first = verify_repository_synthetic_membership(**kwargs)
        second = verify_repository_synthetic_membership(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.canonical_sha256, "40265a4a65808dd1f41396e8b72fde2f35358ed1a00073c298a056e9ee956f2c")
        self.assertEqual(len(first.symbol_ids), 9)

    def _reject(self, payload: dict[str, object]) -> None:
        with self.assertRaises(SyntheticSymbolMembershipError):
            validate_synthetic_symbol_membership_contract(payload, schema_path=self.schema, source_symbol_ids=self.source_ids)

    def test_duplicate_and_order_changes_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["memberships"][1]["symbolId"] = "s001"; self._reject(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"][0], payload["memberships"][1] = payload["memberships"][1], payload["memberships"][0]; self._reject(payload)

    def test_unknown_references_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["memberships"][0]["staffId"] = "staff999"; self._reject(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"][1]["measureId"] = "measure999"; self._reject(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"].pop(); self._reject(payload)

    def test_geometry_and_nested_schema_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["measures"][0]["bbox"]["x"] = 4097; self._reject(payload)
        payload = copy.deepcopy(self.payload); payload["measures"][0]["bbox"]["width"] = 1200; self._reject(payload)
        payload = copy.deepcopy(self.payload); payload["staffs"][0]["extra"] = False; self._reject(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"][0]["pitch"] = 60; self._reject(payload)

    def test_closed_boundaries_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["boundaries"]["pitchAssigned"] = True; self._reject(payload)
        payload = copy.deepcopy(self.payload); payload["boundaries"]["notationGraph"] = True; self._reject(payload)

    def test_outside_root_wrong_root_symlink_and_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            copied = outside / self.artifact.name
            copied.write_bytes(self.artifact.read_bytes())
            with self.assertRaises(SyntheticSymbolMembershipError):
                verify_repository_synthetic_membership(artifact_path=copied, manifest_path=self.manifest,
                    schema_path=self.schema, source_symbol_artifact_path=self.source, allowed_contracts_root=self.contracts)
            wrong = outside / "not-contracts"; wrong.mkdir()
            with self.assertRaises(SyntheticSymbolMembershipError):
                verify_repository_synthetic_membership(artifact_path=self.artifact, manifest_path=self.manifest,
                    schema_path=self.schema, source_symbol_artifact_path=self.source, allowed_contracts_root=wrong)
            link = self.contracts / "membership-test-link.json"
            try:
                link.symlink_to(self.artifact.name)
                with self.assertRaises(SyntheticSymbolMembershipError):
                    verify_repository_synthetic_membership(artifact_path=link, manifest_path=self.manifest,
                        schema_path=self.schema, source_symbol_artifact_path=self.source, allowed_contracts_root=self.contracts)
            finally:
                link.unlink(missing_ok=True)
            tampered = self.contracts / "membership-test-tampered.json"
            try:
                tampered.write_text(self.artifact.read_text().replace('"s009"', '"s099"'), encoding="utf-8")
                with self.assertRaises(SyntheticSymbolMembershipError):
                    verify_repository_synthetic_membership(artifact_path=tampered, manifest_path=self.manifest,
                        schema_path=self.schema, source_symbol_artifact_path=self.source, allowed_contracts_root=self.contracts)
            finally:
                tampered.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
