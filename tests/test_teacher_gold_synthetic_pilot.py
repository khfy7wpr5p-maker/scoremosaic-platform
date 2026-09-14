from __future__ import annotations

import copy
import json
import unittest

from scripts.polyphonic_teacher_gold_synthetic_pilot import (
    ROOT,
    TeacherGoldSyntheticPilotError,
    build_report,
    validate_manifest,
)

MANIFEST_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "ossq-synthetic-v1.json"
REGISTRY_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"
SCHEMA_PATH = ROOT / "contracts" / "polyphonic-teacher-gold-synthetic-pilot-v1.schema.json"


class TeacherGoldSyntheticPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_real_hash_pilot_is_valid_but_non_counting(self) -> None:
        records = validate_manifest(self.manifest)
        self.assertEqual(len(records), 5)
        self.assertTrue(all(r["rightsStatus"] == "CLEAR_CC0" for r in records))
        self.assertTrue(all(r["teacherVerificationStatus"] == "DRAFT" for r in records))
        self.assertTrue(all(not r["countTowardTeacherGoldMinimum"] for r in records))

    def test_report_preserves_not_ready_boundary(self) -> None:
        report = build_report(MANIFEST_PATH)
        self.assertEqual(report["hashedPairCount"], 5)
        self.assertEqual(report["rightsClearPairCount"], 5)
        self.assertEqual(report["teacherVerifiedPairCount"], 0)
        self.assertEqual(report["countedTowardTeacherGoldMinimum"], 0)
        self.assertEqual(report["readiness"], "NOT_READY")
        self.assertFalse(report["fixtureAdmissionAuthorized"])
        self.assertFalse(report["automaticTrainingAuthorization"])
        self.assertFalse(report["productionDecisionAuthority"])

    def test_symbolic_hash_tamper_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["symbolicGold"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_render_hash_tamper_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["renderedEvidence"]["sha256"] = "1" * 64
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_source_commit_tamper_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["sourceCommitSha"] = "0" * 40
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "manifest_contract_invalid"):
            validate_manifest(mutated)

    def test_renderer_lineage_tamper_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["renderer"]["appImageSha256"] = "0" * 64
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "renderer_lineage_invalid"):
            validate_manifest(mutated)

    def test_discovery_artifact_tamper_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["discoveryEvidence"]["artifactZipSha256"] = "0" * 64
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "discovery_lineage_invalid"):
            validate_manifest(mutated)

    def test_teacher_verification_cannot_be_self_asserted(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["teacherVerificationStatus"] = "VERIFIED"
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_pilot_cannot_count_itself(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["countTowardTeacherGoldMinimum"] = True
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_authority_boundary_cannot_expand(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["boundaries"]["automaticFixtureAdmission"] = True
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "manifest_contract_invalid"):
            validate_manifest(mutated)

    def test_current_verified_registry_is_unchanged(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(registry["fixtureRecords"], [])
        self.assertEqual(registry["minimumVerifiedFixtures"], 500)
        self.assertEqual(registry["targetVerifiedFixtures"], 1000)

    def test_schema_keeps_pilot_non_counting(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        record = schema["properties"]["records"]["items"]["properties"]
        boundaries = schema["properties"]["boundaries"]["properties"]
        self.assertEqual(record["rightsStatus"]["const"], "CLEAR_CC0")
        self.assertEqual(record["teacherVerificationStatus"]["const"], "DRAFT")
        self.assertFalse(record["countTowardTeacherGoldMinimum"]["const"])
        self.assertFalse(boundaries["automaticFixtureAdmission"]["const"])
        self.assertFalse(boundaries["automaticTrainingAuthorization"]["const"])
        self.assertFalse(boundaries["productionDecisionAuthority"]["const"])


if __name__ == "__main__":
    unittest.main()
