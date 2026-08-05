from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.offline_fixture_inference import (
    FixtureInferenceError,
    run_generated_fixture,
)


class OfflineGeneratedFixtureInferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_root = Path(__file__).resolve().parents[1] / "fixtures"
        self.manifest = self.fixture_root / "generated-single-staff-v1.manifest.json"

    def test_repository_fixture_is_deterministic_and_closed(self) -> None:
        first = run_generated_fixture(manifest_path=self.manifest, allowed_root=self.fixture_root)
        second = run_generated_fixture(manifest_path=self.manifest, allowed_root=self.fixture_root)
        self.assertEqual(first, second)
        evidence = first.as_dict()
        self.assertEqual(evidence["status"], "completed_offline_fixture_only")
        self.assertEqual(evidence["outputSha256"], "24d660964458829601db48bc6dd494ad496b90f46753871cfb399e5e0941e85f")
        self.assertIs(evidence["modelLoaded"], False)
        self.assertIs(evidence["realOmrInference"], False)
        self.assertIs(evidence["userInputAccepted"], False)
        self.assertIs(evidence["networkUsed"], False)

    def test_tampered_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "fixtures"
            root.mkdir()
            (root / "fixture.txt").write_text("tampered", encoding="utf-8")
            manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
            manifest["inputName"] = "fixture.txt"
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(FixtureInferenceError, "checksum mismatch"):
                run_generated_fixture(manifest_path=manifest_path, allowed_root=root)

    def test_golden_output_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "fixtures"
            root.mkdir()
            source = self.fixture_root / "generated-single-staff-v1.txt"
            (root / source.name).write_bytes(source.read_bytes())
            manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
            manifest["expectedOutputSha256"] = "0" * 64
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(FixtureInferenceError, "golden output mismatch"):
                run_generated_fixture(manifest_path=manifest_path, allowed_root=root)

    def test_outside_root_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "fixtures"
            root.mkdir()
            outside = Path(temp_dir) / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(FixtureInferenceError, "direct child"):
                run_generated_fixture(manifest_path=outside, allowed_root=root)


if __name__ == "__main__":
    unittest.main()
