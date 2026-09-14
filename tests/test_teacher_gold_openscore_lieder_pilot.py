from __future__ import annotations

import copy
import json
import unittest

from scripts.polyphonic_teacher_gold_openscore_lieder_pilot import (
    MANIFEST,
    ROOT,
    TeacherGoldOpenScoreLiederError,
    build_report,
    validate_manifest,
)

SCHEMA = ROOT / "contracts" / "polyphonic-teacher-gold-openscore-lieder-pilot-v1.schema.json"
REGISTRY = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"


class TeacherGoldOpenScoreLiederPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_five_real_pairs_are_valid_but_non_counting(self) -> None:
        records = validate_manifest(self.manifest)
        self.assertEqual(5, len(records))
        self.assertTrue(all(item["rightsStatus"] == "CLEAR_CC0" for item in records))
        self.assertTrue(all(item["teacherVerificationStatus"] == "DRAFT" for item in records))
        self.assertTrue(all(item["evaluationEligibility"] == "REVIEW_REQUIRED" for item in records))
        self.assertTrue(all(item["countTowardTeacherGoldMinimum"] is False for item in records))

    def test_report_is_explicitly_not_ready(self) -> None:
        report = build_report()
        self.assertEqual(5, report["hashedPairCount"])
        self.assertEqual(5, report["rightsClearPairCount"])
        self.assertEqual(5, report["opaqueWhiteReviewPairCount"])
        self.assertEqual(5, report["structuralObservationPairCount"])
        self.assertEqual(2, report["observedTupletPairCount"])
        self.assertEqual(2, report["observedGracePairCount"])
        self.assertEqual(0, report["teacherVerifiedPairCount"])
        self.assertEqual(0, report["countedTowardTeacherGoldMinimum"])
        self.assertEqual("NOT_READY", report["readiness"])
        self.assertFalse(report["fixtureAdmissionAuthorized"])
        self.assertFalse(report["automaticTrainingAuthorization"])
        self.assertFalse(report["productionDecisionAuthority"])

    def test_review_images_are_white_and_opaque(self) -> None:
        for record in validate_manifest(self.manifest):
            self.assertEqual("#FFFFFF", record["renderedEvidence"]["background"])
            self.assertIs(record["renderedEvidence"]["alphaChannel"], False)

    def test_artifact_lineage_tamper_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["discoveryEvidence"]["artifactZipSha256"] = "0" * 64
        with self.assertRaisesRegex(TeacherGoldOpenScoreLiederError, "discovery_lineage_invalid"):
            validate_manifest(mutated)

    def test_teacher_verification_cannot_be_self_asserted(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["teacherVerificationStatus"] = "VERIFIED"
        with self.assertRaisesRegex(TeacherGoldOpenScoreLiederError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_pilot_cannot_count_itself(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["countTowardTeacherGoldMinimum"] = True
        with self.assertRaisesRegex(TeacherGoldOpenScoreLiederError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_transparency_cannot_be_reintroduced(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["renderedEvidence"]["alphaChannel"] = True
        with self.assertRaisesRegex(TeacherGoldOpenScoreLiederError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_structural_observation_tamper_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][2]["structuralObservation"]["hasTuplet"] = False
        with self.assertRaisesRegex(TeacherGoldOpenScoreLiederError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_schema_preserves_non_counting_boundary(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertTrue(schema["$defs"])
        props = schema["properties"]["records"]["items"]["properties"]
        self.assertEqual("DRAFT", props["teacherVerificationStatus"]["const"])
        self.assertEqual("REVIEW_REQUIRED", props["evaluationEligibility"]["const"])
        self.assertFalse(props["countTowardTeacherGoldMinimum"]["const"])
        self.assertFalse(schema["properties"]["boundaries"]["properties"]["automaticTrainingAuthorization"]["const"])

    def test_existing_verified_registry_is_not_reset(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(registry["fixtureRecords"]), 5)
        self.assertEqual(500, registry["minimumVerifiedFixtures"])
        self.assertEqual(1000, registry["targetVerifiedFixtures"])


if __name__ == "__main__":
    unittest.main()
