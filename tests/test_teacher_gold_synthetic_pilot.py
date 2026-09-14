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

MANIFEST_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "ossq-synthetic-v2.json"
V1_MANIFEST_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "ossq-synthetic-v1.json"
REGISTRY_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"
SCHEMA_PATH = ROOT / "contracts" / "polyphonic-teacher-gold-synthetic-pilot-v2.schema.json"


class TeacherGoldSyntheticPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_active_v2_real_hash_pilot_is_valid_but_non_counting(self) -> None:
        records = validate_manifest(self.manifest)
        self.assertEqual(len(records), 5)
        self.assertTrue(all(r["rightsStatus"] == "CLEAR_CC0" for r in records))
        self.assertTrue(all(r["teacherVerificationStatus"] == "DRAFT" for r in records))
        self.assertTrue(all(not r["countTowardTeacherGoldMinimum"] for r in records))

    def test_review_pngs_are_explicitly_opaque_white(self) -> None:
        records = validate_manifest(self.manifest)
        self.assertTrue(all(r["renderedEvidence"]["background"] == "#FFFFFF" for r in records))
        self.assertTrue(all(r["renderedEvidence"]["alphaChannel"] is False for r in records))
        self.assertTrue(self.manifest["reviewImageProcessing"]["alphaRemoved"])
        self.assertEqual(self.manifest["reviewImageProcessing"]["validationMethod"], "OPAQUE_NONEMPTY_PAGE_V1")

    def test_report_preserves_not_ready_boundary(self) -> None:
        report = build_report(MANIFEST_PATH)
        self.assertEqual(report["hashedPairCount"], 5)
        self.assertEqual(report["rightsClearPairCount"], 5)
        self.assertEqual(report["opaqueWhiteReviewPairCount"], 5)
        self.assertEqual(report["teacherVerifiedPairCount"], 0)
        self.assertEqual(report["countedTowardTeacherGoldMinimum"], 0)
        self.assertEqual(report["readiness"], "NOT_READY")
        self.assertFalse(report["supersededV1ReviewArtifactAuthorized"])
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

    def test_transparency_cannot_be_reintroduced(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["renderedEvidence"]["alphaChannel"] = True
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_non_white_review_background_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["renderedEvidence"]["background"] = "#000000"
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_review_processing_tamper_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["reviewImageProcessing"]["alphaRemoved"] = False
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "review_image_processing_invalid"):
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

    def test_superseded_v1_artifact_cannot_be_reauthorized(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["supersedes"]["reviewUseAuthorized"] = True
        with self.assertRaisesRegex(TeacherGoldSyntheticPilotError, "supersedes_invalid"):
            validate_manifest(mutated)

    def test_v2_explicitly_supersedes_v1_review_media(self) -> None:
        self.assertTrue(V1_MANIFEST_PATH.exists())
        self.assertEqual(self.manifest["supersedes"]["artifactId"], 10362957231)
        self.assertEqual(
            self.manifest["supersedes"]["reason"],
            "TRANSPARENT_REVIEW_RENDER_UNREADABLE_ON_DARK_PREVIEW",
        )
        self.assertFalse(self.manifest["supersedes"]["reviewUseAuthorized"])

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

    def test_pilot_remains_non_counting_after_separate_teacher_admission(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(registry["fixtureRecords"]), 5)
        self.assertTrue(all(not record["countTowardTeacherGoldMinimum"] for record in self.manifest["records"]))
        self.assertTrue(all(record["teacherVerificationStatus"] == "DRAFT" for record in self.manifest["records"]))
        self.assertEqual(registry["minimumVerifiedFixtures"], 500)
        self.assertEqual(registry["targetVerifiedFixtures"], 1000)

    def test_v2_schema_keeps_review_media_opaque_and_non_counting(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        record = schema["properties"]["records"]["items"]["properties"]
        rendered = schema["$defs"]["pngArtifact"]["properties"]
        boundaries = schema["properties"]["boundaries"]["properties"]
        supersedes = schema["properties"]["supersedes"]["properties"]
        self.assertEqual(record["rightsStatus"]["const"], "CLEAR_CC0")
        self.assertEqual(record["teacherVerificationStatus"]["const"], "DRAFT")
        self.assertFalse(record["countTowardTeacherGoldMinimum"]["const"])
        self.assertEqual(rendered["background"]["const"], "#FFFFFF")
        self.assertFalse(rendered["alphaChannel"]["const"])
        self.assertFalse(supersedes["reviewUseAuthorized"]["const"])
        self.assertFalse(boundaries["automaticFixtureAdmission"]["const"])
        self.assertFalse(boundaries["automaticTrainingAuthorization"]["const"])
        self.assertFalse(boundaries["productionDecisionAuthority"]["const"])


if __name__ == "__main__":
    unittest.main()
