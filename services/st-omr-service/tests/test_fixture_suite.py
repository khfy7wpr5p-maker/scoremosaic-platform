from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.fixture_suite import FixtureSuiteError, run_generated_fixture_suite


class GeneratedFixtureSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[3]
        self.fixture_root = self.repo_root / "services" / "st-omr-service" / "fixtures"
        self.registry = self.fixture_root / "generated-fixture-suite-v1.registry.json"

    def test_repository_suite_is_deterministic_and_closed(self) -> None:
        first = run_generated_fixture_suite(registry_path=self.registry, allowed_root=self.fixture_root)
        second = run_generated_fixture_suite(registry_path=self.registry, allowed_root=self.fixture_root)

        self.assertEqual(first, second)
        self.assertEqual(first.fixture_count, 3)
        self.assertEqual(
            first.fixture_ids,
            (
                "generated-chord-v1",
                "generated-rhythm-pattern-v1",
                "generated-single-staff",
            ),
        )
        evidence = first.as_dict()
        self.assertFalse(evidence["modelLoaded"])
        self.assertFalse(evidence["realOmrInference"])
        self.assertFalse(evidence["userInputAccepted"])
        self.assertFalse(evidence["networkUsed"])

    def test_duplicate_manifest_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "fixtures"
            shutil.copytree(self.fixture_root, root)
            payload = json.loads((root / self.registry.name).read_text(encoding="utf-8"))
            payload["fixtures"].append(payload["fixtures"][0])
            (root / self.registry.name).write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(FixtureSuiteError):
                run_generated_fixture_suite(registry_path=root / self.registry.name, allowed_root=root)

    def test_duplicate_fixture_id_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "fixtures"
            shutil.copytree(self.fixture_root, root)
            second_manifest = root / "generated-rhythm-pattern-v1.manifest.json"
            payload = json.loads(second_manifest.read_text(encoding="utf-8"))
            payload["fixtureId"] = "generated-single-staff"
            second_manifest.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(FixtureSuiteError):
                run_generated_fixture_suite(registry_path=root / self.registry.name, allowed_root=root)

    def test_tampered_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "fixtures"
            shutil.copytree(self.fixture_root, root)
            target = root / "generated-chord-v1.txt"
            target.write_text(target.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

            with self.assertRaises(FixtureSuiteError):
                run_generated_fixture_suite(registry_path=root / self.registry.name, allowed_root=root)

    def test_path_escape_and_empty_registry_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "fixtures"
            shutil.copytree(self.fixture_root, root)
            registry = root / self.registry.name
            payload = json.loads(registry.read_text(encoding="utf-8"))
            payload["fixtures"] = [{"manifestName": "../outside.manifest.json"}]
            registry.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(FixtureSuiteError):
                run_generated_fixture_suite(registry_path=registry, allowed_root=root)

            payload["fixtures"] = []
            registry.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(FixtureSuiteError):
                run_generated_fixture_suite(registry_path=registry, allowed_root=root)


if __name__ == "__main__":
    unittest.main()
