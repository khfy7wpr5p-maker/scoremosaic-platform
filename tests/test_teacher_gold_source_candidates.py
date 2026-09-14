from __future__ import annotations

import copy
import json
import unittest

from scripts.polyphonic_teacher_gold_source_candidates import (
    ROOT,
    TeacherGoldSourceCandidateError,
    build_report,
    validate_catalogue,
)


CATALOGUE_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "source-candidates.json"
REGISTRY_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"
SCHEMA_PATH = ROOT / "contracts" / "polyphonic-teacher-gold-source-candidates-v1.schema.json"


class TeacherGoldSourceCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))

    def test_catalogue_is_non_counting_and_deterministic(self) -> None:
        candidates = validate_catalogue(self.catalogue)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(
            [item["candidateId"] for item in candidates],
            sorted(item["candidateId"] for item in candidates),
        )
        self.assertTrue(all(not item["teacherVerified"] for item in candidates))
        self.assertTrue(all(not item["contentHashesVerified"] for item in candidates))
        self.assertTrue(all(not item["countTowardTeacherGoldMinimum"] for item in candidates))

    def test_report_never_promotes_candidates_to_teacher_gold(self) -> None:
        report = build_report(CATALOGUE_PATH)
        self.assertEqual(report["candidateCount"], 3)
        self.assertEqual(report["teacherVerifiedCandidateCount"], 0)
        self.assertEqual(report["countedTowardTeacherGoldMinimum"], 0)
        self.assertFalse(report["fixtureAdmissionAuthorized"])
        self.assertFalse(report["productionDecisionAuthority"])

    def test_only_explicitly_clear_candidate_is_cc0_at_catalogue_stage(self) -> None:
        candidates = validate_catalogue(self.catalogue)
        states = {item["candidateId"]: item["licenseState"] for item in candidates}
        self.assertEqual(
            states["tg_source_openscore_lieder_staendchen_d889"], "CLEAR_CC0"
        )
        self.assertEqual(states["tg_source_doremi_v1"], "REVIEW_REQUIRED")
        self.assertEqual(states["tg_source_ossq_omr_2026"], "REVIEW_REQUIRED")

    def test_candidate_cannot_claim_teacher_verification(self) -> None:
        mutated = copy.deepcopy(self.catalogue)
        mutated["candidates"][0]["teacherVerified"] = True
        with self.assertRaisesRegex(TeacherGoldSourceCandidateError, "candidate_invalid"):
            validate_catalogue(mutated)

    def test_candidate_cannot_count_toward_minimum(self) -> None:
        mutated = copy.deepcopy(self.catalogue)
        mutated["candidates"][0]["countTowardTeacherGoldMinimum"] = True
        with self.assertRaisesRegex(TeacherGoldSourceCandidateError, "candidate_invalid"):
            validate_catalogue(mutated)

    def test_candidate_cannot_auto_authorize_fixture_admission(self) -> None:
        mutated = copy.deepcopy(self.catalogue)
        mutated["boundaries"]["automaticFixtureAdmission"] = True
        with self.assertRaisesRegex(
            TeacherGoldSourceCandidateError, "catalogue_contract_invalid"
        ):
            validate_catalogue(mutated)

    def test_duplicate_source_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.catalogue)
        duplicate = copy.deepcopy(mutated["candidates"][0])
        duplicate["candidateId"] = "tg_source_duplicate_doremi"
        mutated["candidates"].append(duplicate)
        mutated["candidates"].sort(key=lambda item: item["candidateId"])
        with self.assertRaisesRegex(TeacherGoldSourceCandidateError, "candidate_duplicate"):
            validate_catalogue(mutated)

    def test_verified_registry_remains_truthfully_empty(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(registry["fixtureRecords"], [])
        self.assertEqual(registry["minimumVerifiedFixtures"], 500)
        self.assertEqual(registry["targetVerifiedFixtures"], 1000)

    def test_schema_preserves_non_counting_boundary(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        candidate_props = schema["properties"]["candidates"]["items"]["properties"]
        boundaries = schema["properties"]["boundaries"]["properties"]
        self.assertFalse(candidate_props["teacherVerified"]["const"])
        self.assertFalse(candidate_props["contentHashesVerified"]["const"])
        self.assertFalse(candidate_props["countTowardTeacherGoldMinimum"]["const"])
        self.assertFalse(boundaries["automaticFixtureAdmission"]["const"])
        self.assertFalse(boundaries["automaticTrainingAuthorization"]["const"])
        self.assertFalse(boundaries["productionDecisionAuthority"]["const"])


if __name__ == "__main__":
    unittest.main()
