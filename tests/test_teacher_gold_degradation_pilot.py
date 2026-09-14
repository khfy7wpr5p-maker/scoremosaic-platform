from __future__ import annotations

import copy
import json
import unittest

from scripts.polyphonic_teacher_gold_degradation_pilot import (
    MANIFEST,
    REGISTRY,
    ROOT,
    TeacherGoldDegradationPilotError,
    build_report,
    validate_manifest,
)

SCHEMA = ROOT / "contracts" / "polyphonic-teacher-gold-degradation-pilot-v1.schema.json"


class TeacherGoldDegradationPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_five_real_degraded_pairs_are_valid_but_non_counting(self) -> None:
        records = validate_manifest(self.manifest)
        self.assertEqual(5, len(records))
        self.assertTrue(all(item["rightsStatus"] == "CLEAR_CC0" for item in records))
        self.assertTrue(all(item["teacherVerificationStatus"] == "DRAFT" for item in records))
        self.assertTrue(all(item["evaluationEligibility"] == "REVIEW_REQUIRED" for item in records))
        self.assertTrue(all(item["countTowardTeacherGoldMinimum"] is False for item in records))

    def test_scan_condition_coverage_is_exactly_five_new_conditions(self) -> None:
        records = validate_manifest(self.manifest)
        self.assertEqual(
            {"LOW_CONTRAST", "ROTATION", "SKEW", "PERSPECTIVE_DISTORTION", "LOW_QUALITY_SCAN"},
            {item["scanCondition"] for item in records},
        )

    def test_report_preserves_not_ready_and_authority_locks(self) -> None:
        report = build_report()
        self.assertEqual(5, report["hashedPairCount"])
        self.assertEqual(5, report["rightsClearPairCount"])
        self.assertEqual(5, report["degradedReviewPairCount"])
        self.assertEqual(0, report["teacherVerifiedPairCount"])
        self.assertEqual(0, report["countedTowardTeacherGoldMinimum"])
        self.assertGreaterEqual(report["verifiedRegistryFixtureCount"], 10)
        self.assertEqual("NOT_READY", report["readiness"])
        self.assertFalse(report["fixtureAdmissionAuthorized"])
        self.assertFalse(report["automaticTrainingAuthorization"])
        self.assertFalse(report["productionDecisionAuthority"])

    def test_degraded_hash_tamper_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["degradedRender"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(TeacherGoldDegradationPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_symbolic_hash_tamper_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["symbolicGold"]["sha256"] = "1" * 64
        with self.assertRaisesRegex(TeacherGoldDegradationPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_transform_or_condition_tamper_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][2]["degradationTransform"] = "OTHER_V1"
        with self.assertRaisesRegex(TeacherGoldDegradationPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][2]["scanCondition"] = "ROTATION"
        with self.assertRaisesRegex(TeacherGoldDegradationPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_teacher_verification_cannot_be_self_asserted(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["teacherVerificationStatus"] = "VERIFIED"
        with self.assertRaisesRegex(TeacherGoldDegradationPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_pilot_cannot_count_itself(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["records"][0]["countTowardTeacherGoldMinimum"] = True
        with self.assertRaisesRegex(TeacherGoldDegradationPilotError, "record_evidence_invalid"):
            validate_manifest(mutated)

    def test_authority_boundary_cannot_expand(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["boundaries"]["automaticFixtureAdmission"] = True
        with self.assertRaisesRegex(TeacherGoldDegradationPilotError, "manifest_contract_invalid"):
            validate_manifest(mutated)

    def test_discovery_artifact_lineage_is_pinned(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["discoveryEvidence"]["artifactZipSha256"] = "2" * 64
        with self.assertRaisesRegex(TeacherGoldDegradationPilotError, "discovery_lineage_invalid"):
            validate_manifest(mutated)

    def test_existing_verified_registry_is_not_reset(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(registry["fixtureRecords"]), 10)
        self.assertEqual(500, registry["minimumVerifiedFixtures"])
        self.assertEqual(1000, registry["targetVerifiedFixtures"])

    def test_schema_preserves_draft_non_counting_boundary(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertTrue(schema["$defs"])
        props = schema["$defs"]["record"]["properties"]
        boundaries = schema["properties"]["boundaries"]["properties"]
        self.assertEqual("DRAFT", props["teacherVerificationStatus"]["const"])
        self.assertEqual("REVIEW_REQUIRED", props["evaluationEligibility"]["const"])
        self.assertFalse(props["countTowardTeacherGoldMinimum"]["const"])
        self.assertFalse(boundaries["teacherVerifiedDegradedImages"]["const"])
        self.assertFalse(boundaries["automaticFixtureAdmission"]["const"])
        self.assertFalse(boundaries["automaticTrainingAuthorization"]["const"])
        self.assertFalse(boundaries["productionDecisionAuthority"]["const"])


if __name__ == "__main__":
    unittest.main()
