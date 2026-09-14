from __future__ import annotations

import copy
import json
import unittest

from scripts.polyphonic_teacher_gold_storage import (
    ROOT,
    ROOT_ENV_NAME,
    TeacherGoldStorageError,
    build_report,
    resolve_root_folder_id,
    validate_manifest,
)


MANIFEST_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "storage-manifest.json"
REGISTRY_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"
SCHEMA_PATH = ROOT / "contracts" / "polyphonic-teacher-gold-storage-manifest-v1.schema.json"


class TeacherGoldExternalStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_matches_drive_folder_tree(self) -> None:
        folders = validate_manifest(self.manifest)
        self.assertEqual(
            folders,
            {
                "registry": "00_registry",
                "imslp": "01_imslp",
                "openscore": "02_openscore",
                "mutopia": "03_mutopia",
                "kernscores": "04_kernscores",
                "mei": "05_mei",
                "cpdl": "06_cpdl",
                "teacherVerified": "07_teacher_verified",
                "benchmarkOutputs": "08_benchmark_outputs",
            },
        )

    def test_manifest_schema_locks_environment_only_root_binding(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        root_props = schema["properties"]["rootFolderRef"]["properties"]
        self.assertEqual(root_props["mode"]["const"], "ENVIRONMENT_VARIABLE")
        self.assertEqual(root_props["name"]["const"], ROOT_ENV_NAME)
        self.assertTrue(
            schema["properties"]["boundaries"]["properties"]["noDriveFolderIdsInRepository"]["const"]
        )

    def test_runtime_root_binding_is_resolved_without_publishing_it(self) -> None:
        private_folder_id = "privateTeacherGoldRoot_123456789"
        self.assertEqual(
            resolve_root_folder_id(self.manifest, {ROOT_ENV_NAME: private_folder_id}),
            private_folder_id,
        )
        report = build_report(MANIFEST_PATH)
        self.assertFalse(report["rootBindingConfigured"])
        self.assertFalse(report["driveFolderIdentifiersPublished"])
        self.assertNotIn(private_folder_id, json.dumps(report, sort_keys=True))

    def test_missing_or_invalid_root_binding_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            TeacherGoldStorageError, "drive_root_binding_missing_or_invalid"
        ):
            resolve_root_folder_id(self.manifest, {})
        with self.assertRaisesRegex(
            TeacherGoldStorageError, "drive_root_binding_missing_or_invalid"
        ):
            resolve_root_folder_id(self.manifest, {ROOT_ENV_NAME: "bad/id"})

    def test_raw_drive_locator_cannot_replace_environment_reference(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["rootFolderRef"]["name"] = "https://drive.google.com/drive/folders/private-id"
        with self.assertRaisesRegex(TeacherGoldStorageError, "root_reference_invalid"):
            validate_manifest(mutated)

    def test_storage_boundary_does_not_authorize_transfer_or_production(self) -> None:
        boundaries = self.manifest["boundaries"]
        self.assertTrue(boundaries["researchEvaluationOnly"])
        self.assertTrue(boundaries["externalAssetsRemainExternal"])
        self.assertTrue(boundaries["githubIsNotCorpusBlobStore"])
        self.assertFalse(boundaries["automaticDownload"])
        self.assertFalse(boundaries["automaticUpload"])
        self.assertFalse(boundaries["productionDecisionAuthority"])

    def test_public_registry_has_five_admitted_records_without_storage_authority_change(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(registry["fixtureRecords"]), 5)
        self.assertEqual(registry["minimumVerifiedFixtures"], 500)
        self.assertEqual(registry["targetVerifiedFixtures"], 1000)
        self.assertTrue(registry["boundaries"]["privateAssetsRemainExternal"])
        self.assertFalse(registry["boundaries"]["productionDecisionAuthority"])


if __name__ == "__main__":
    unittest.main()
