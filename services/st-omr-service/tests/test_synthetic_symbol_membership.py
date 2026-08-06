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
        cls.source_manifest = cls.contracts / "structured-symbol-output-v1.manifest.json"
        cls.payload = json.loads(cls.artifact.read_text())
        source = json.loads(cls.source.read_text())
        cls.source_hash = "78136ad2dda8addf74835a43b2071acc6d8fb093b0c8ded21ac61d8a7417a1e1"
        cls.source_symbols = {s["id"]: {"type": s["type"], "bbox": s["bbox"]} for s in source["symbols"]}

    def kwargs(self, **changes: Path) -> dict[str, Path]:
        values = dict(artifact_path=self.artifact, manifest_path=self.manifest, schema_path=self.schema,
                      source_symbol_artifact_path=self.source, source_symbol_manifest_path=self.source_manifest,
                      allowed_contracts_root=self.contracts)
        values.update(changes)
        return values

    def reject_payload(self, payload: dict[str, object], symbols: dict[str, dict[str, object]] | None = None) -> None:
        with self.assertRaises(SyntheticSymbolMembershipError):
            validate_synthetic_symbol_membership_contract(payload, schema_path=self.schema,
                source_symbols=symbols or self.source_symbols, source_canonical_sha256=self.source_hash)

    def test_repository_membership_is_pinned_and_deterministic(self) -> None:
        first = verify_repository_synthetic_membership(**self.kwargs())
        second = verify_repository_synthetic_membership(**self.kwargs())
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_sha256, "fdc9ad24a5e9997af30b1c6bfe2fcd201f3255e203c37fa8ba5083e1b0f08f1b")
        self.assertEqual(len(first.symbol_ids), 9)

    def test_duplicate_order_missing_and_unknown_references_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["memberships"][1]["symbolId"] = "s001"; self.reject_payload(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"].reverse(); self.reject_payload(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"].pop(); self.reject_payload(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"][0]["staffId"] = "staff999"; self.reject_payload(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"][1]["measureId"] = "measure999"; self.reject_payload(payload)

    def test_lineage_type_bbox_and_duplicate_source_fail_closed(self) -> None:
        symbols = copy.deepcopy(self.source_symbols); symbols["s001"]["type"] = "measure"; self.reject_payload(self.payload, symbols)
        symbols = copy.deepcopy(self.source_symbols); symbols["s002"]["type"] = "staff"; self.reject_payload(self.payload, symbols)
        payload = copy.deepcopy(self.payload); payload["staffs"][0]["bbox"]["x"] += 1; self.reject_payload(payload)
        payload = copy.deepcopy(self.payload); payload["measures"][0]["bbox"]["x"] += 1; self.reject_payload(payload)
        payload = copy.deepcopy(self.payload); payload["measures"][0]["sourceSymbolId"] = "s001"; self.reject_payload(payload)

    def test_spatial_membership_fails_closed(self) -> None:
        symbols = copy.deepcopy(self.source_symbols); symbols["s005"]["bbox"]["x"] = 1400; self.reject_payload(self.payload, symbols)
        symbols = copy.deepcopy(self.source_symbols); symbols["s005"]["bbox"]["x"] = 700; self.reject_payload(self.payload, symbols)
        payload = copy.deepcopy(self.payload); payload["measures"][0]["bbox"]["width"] = 1200; self.reject_payload(payload)

    def test_schema_and_closed_boundaries_fail_closed(self) -> None:
        payload = copy.deepcopy(self.payload); payload["staffs"][0]["extra"] = False; self.reject_payload(payload)
        payload = copy.deepcopy(self.payload); payload["boundaries"]["pitchAssigned"] = True; self.reject_payload(payload)
        payload = copy.deepcopy(self.payload); payload["memberships"][0]["pitch"] = 60; self.reject_payload(payload)

    def test_repository_chain_tampering_and_path_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "contracts"; root.mkdir()
            for original in (self.artifact, self.manifest, self.schema, self.source, self.source_manifest):
                (root / original.name).write_bytes(original.read_bytes())
            def verify(**changes: Path) -> None:
                args = dict(artifact_path=root / self.artifact.name, manifest_path=root / self.manifest.name,
                    schema_path=root / self.schema.name, source_symbol_artifact_path=root / self.source.name,
                    source_symbol_manifest_path=root / self.source_manifest.name, allowed_contracts_root=root)
                args.update(changes)
                with self.assertRaises(SyntheticSymbolMembershipError): verify_repository_synthetic_membership(**args)
            (root / self.source.name).write_text((root / self.source.name).read_text().replace('"confidence": 930', '"confidence": 931'))
            verify()
            (root / self.source.name).write_bytes(self.source.read_bytes())
            source_manifest = json.loads((root / self.source_manifest.name).read_text()); source_manifest["canonicalSha256"] = "0" * 64
            (root / self.source_manifest.name).write_text(json.dumps(source_manifest)); verify()
            (root / self.source_manifest.name).write_bytes(self.source_manifest.read_bytes())
            schema = root / self.schema.name; schema.write_text(schema.read_text() + " "); verify()
            schema.write_bytes(self.schema.read_bytes())
            wrong = root / "wrong.json"; wrong.write_bytes((root / self.artifact.name).read_bytes()); verify(artifact_path=wrong)
            missing = root / "missing.json"; verify(artifact_path=missing)
            outside = Path(directory) / self.artifact.name; outside.write_bytes(self.artifact.read_bytes()); verify(artifact_path=outside)

    def test_symlink_root_and_file_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); real = base / "contracts"; real.mkdir(); link_root = base / "linked"; link_root.symlink_to(real, target_is_directory=True)
            with self.assertRaises(SyntheticSymbolMembershipError):
                verify_repository_synthetic_membership(**self.kwargs(allowed_contracts_root=link_root))
            link = self.contracts / "membership-source-link.json"
            try:
                link.symlink_to(self.source.name)
                with self.assertRaises(SyntheticSymbolMembershipError):
                    verify_repository_synthetic_membership(**self.kwargs(source_symbol_artifact_path=link))
            finally:
                link.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
