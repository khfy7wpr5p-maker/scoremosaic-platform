from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.synthetic_reading_order import (
    SyntheticReadingOrderError,
    require_byte_identical_reading_orders,
    validate_synthetic_reading_order_contract,
    verify_repository_synthetic_reading_order,
)


class SyntheticReadingOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.contracts = cls.root / "contracts"
        cls.schema = cls.contracts / "synthetic-reading-order-v1.schema.json"
        cls.artifact = cls.contracts / "synthetic-reading-order-v1.synthetic.json"
        cls.manifest = cls.contracts / "synthetic-reading-order-v1.manifest.json"
        cls.membership_artifact = cls.contracts / "synthetic-symbol-membership-v1.synthetic.json"
        cls.membership_manifest = cls.contracts / "synthetic-symbol-membership-v1.manifest.json"
        cls.membership_schema = cls.contracts / "synthetic-symbol-membership-v1.schema.json"
        cls.structured_artifact = cls.contracts / "structured-symbol-output-v1.synthetic.json"
        cls.structured_manifest = cls.contracts / "structured-symbol-output-v1.manifest.json"
        cls.payload = json.loads(cls.artifact.read_text())
        cls.membership_payload = json.loads(cls.membership_artifact.read_text())
        cls.membership_sha = "fdc9ad24a5e9997af30b1c6bfe2fcd201f3255e203c37fa8ba5083e1b0f08f1b"

    def kwargs(self, root: Path | None = None) -> dict[str, Path]:
        root = root or self.contracts
        return {
            "artifact_path": root / self.artifact.name,
            "manifest_path": root / self.manifest.name,
            "schema_path": root / self.schema.name,
            "membership_artifact_path": root / self.membership_artifact.name,
            "membership_manifest_path": root / self.membership_manifest.name,
            "membership_schema_path": root / self.membership_schema.name,
            "structured_artifact_path": root / self.structured_artifact.name,
            "structured_manifest_path": root / self.structured_manifest.name,
            "allowed_contracts_root": root,
        }

    def reject(self, payload: dict[str, object]) -> None:
        with self.assertRaises(SyntheticReadingOrderError):
            validate_synthetic_reading_order_contract(
                payload, schema_path=self.schema, membership_payload=self.membership_payload,
                membership_canonical_sha256=self.membership_sha,
            )

    def test_repository_order_is_pinned_and_byte_identical(self) -> None:
        first = verify_repository_synthetic_reading_order(**self.kwargs())
        second = verify_repository_synthetic_reading_order(**self.kwargs())
        require_byte_identical_reading_orders(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_sha256, "2229fbf124bdfbc045776e74fa064ce68498c0cbbb8f00a65ef0b5416185178d")
        self.assertEqual(set(first.symbol_ids), {f"s{i:03d}" for i in range(1, 10)})

    def test_duplicate_unknown_and_missing_symbols_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["measureOrders"][0]["symbolIds"].append("s002"); self.reject(payload)
        payload = copy.deepcopy(self.payload); payload["measureOrders"][0]["symbolIds"][0] = "s999"; self.reject(payload)
        payload = copy.deepcopy(self.payload); payload["measureOrders"][0]["symbolIds"].pop(); self.reject(payload)

    def test_staff_and_measure_membership_violations_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["staffOrders"][0]["symbolIds"] = ["s003"]; self.reject(payload)
        payload = copy.deepcopy(self.payload); payload["measureOrders"][0]["staffId"] = "staff999"; self.reject(payload)
        payload = copy.deepcopy(self.payload); payload["measureOrders"][0]["measureId"] = "measure999"; self.reject(payload)

    def test_noncanonical_records_and_closed_schema_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["staffOrders"].append(copy.deepcopy(payload["staffOrders"][0])); self.reject(payload)
        payload = copy.deepcopy(self.payload); payload["measureOrders"][0]["extra"] = False; self.reject(payload)
        payload = copy.deepcopy(self.payload); payload["boundaries"]["musicXml"] = True; self.reject(payload)
        payload = copy.deepcopy(self.payload); payload["membershipArtifact"]["canonicalSha256"] = "0" * 64; self.reject(payload)

    def _copy_contracts(self, target: Path) -> None:
        target.mkdir()
        for path in (
            self.schema, self.artifact, self.manifest, self.membership_artifact,
            self.membership_manifest, self.membership_schema,
            self.structured_artifact, self.structured_manifest,
        ):
            shutil.copy2(path, target / path.name)

    def test_artifact_schema_and_membership_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "contracts"; self._copy_contracts(root)
            (root / self.artifact.name).write_text((root / self.artifact.name).read_text().replace('"s009"', '"s008"'))
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**self.kwargs(root))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "contracts"; self._copy_contracts(root)
            (root / self.schema.name).write_text((root / self.schema.name).read_text() + " ")
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**self.kwargs(root))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "contracts"; self._copy_contracts(root)
            (root / self.membership_artifact.name).write_text((root / self.membership_artifact.name).read_text().replace('"s009"', '"s099"'))
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**self.kwargs(root))

    def test_wrong_name_missing_file_and_malformed_json_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "contracts"; self._copy_contracts(root)
            wrong = root / "wrong.json"; shutil.copy2(root / self.artifact.name, wrong)
            kwargs = self.kwargs(root); kwargs["artifact_path"] = wrong
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**kwargs)
            (root / self.schema.name).unlink()
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**self.kwargs(root))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "contracts"; self._copy_contracts(root)
            (root / self.manifest.name).write_text("{")
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**self.kwargs(root))

    def test_symlink_root_file_and_path_escape_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base / "contracts"; self._copy_contracts(root)
            link_root = base / "linked-contracts"; link_root.symlink_to(root, target_is_directory=True)
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**self.kwargs(link_root))
            link = root / "reading-link.json"; link.symlink_to(root / self.artifact.name)
            kwargs = self.kwargs(root); kwargs["artifact_path"] = link
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**kwargs)
            outside = base / self.artifact.name; shutil.copy2(root / self.artifact.name, outside)
            kwargs = self.kwargs(root); kwargs["artifact_path"] = outside
            with self.assertRaises(SyntheticReadingOrderError): verify_repository_synthetic_reading_order(**kwargs)

    def test_nondeterministic_output_fails_closed(self) -> None:
        with self.assertRaises(SyntheticReadingOrderError):
            require_byte_identical_reading_orders(b"one", b"two")


if __name__ == "__main__":
    unittest.main()
