from __future__ import annotations

from hashlib import sha256
import json
import unittest

from scripts.polyphonic_teacher_gold_harness import ROOT, build_report


REGISTRY = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"
PILOT = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "openscore-lieder-v1.json"
FIXTURE_DIR = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "fixtures"


class TeacherGoldOpenScoreLiederAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.pilot = json.loads(PILOT.read_text(encoding="utf-8"))
        self.pilot_by_id = {record["pilotId"]: record for record in self.pilot["records"]}

    def test_five_verified_openscore_fixtures_are_admitted(self) -> None:
        expected_ids = {f"poly_fixture_openscore_osl_0{i}_p1" for i in range(1, 6)}
        registry_ids = {record["fixtureId"] for record in self.registry["fixtureRecords"]}
        self.assertTrue(expected_ids.issubset(registry_ids))
        self.assertEqual(10, len(self.registry["fixtureRecords"]))

    def test_registry_hashes_bind_exact_fixture_bytes(self) -> None:
        for record in self.registry["fixtureRecords"]:
            if not record["fixtureId"].startswith("poly_fixture_openscore_"):
                continue
            path = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / record["metadataRef"]
            self.assertEqual(record["metadataSha256"], sha256(path.read_bytes()).hexdigest())

    def test_admission_binds_reviewed_png_and_mxl_hashes(self) -> None:
        for i in range(1, 6):
            pilot_id = f"osl_0{i}"
            fixture_id = f"poly_fixture_openscore_{pilot_id}_p1"
            fixture = json.loads((FIXTURE_DIR / f"{fixture_id}.json").read_text(encoding="utf-8"))
            pilot = self.pilot_by_id[pilot_id]
            self.assertEqual(pilot["renderedEvidence"]["sha256"], fixture["source"]["sourceSha256"])
            self.assertEqual(pilot["symbolicGold"]["sha256"], fixture["gold"]["goldArtifactSha256"])
            self.assertEqual("VERIFIED", fixture["gold"]["verificationStatus"])
            self.assertEqual("TEACHER", fixture["gold"]["verifiedByRole"])
            self.assertEqual("NOT_AUTHORIZED", fixture["gold"]["trainingAuthorization"])
            self.assertEqual("CC0-1.0", fixture["source"]["licenseMetadata"]["license"])
            self.assertEqual("YES", fixture["source"]["licenseMetadata"]["evaluationAllowed"])

    def test_classification_is_conservative_and_traceable_to_symbolic_observation(self) -> None:
        mapping = {
            "hasTieOrTied": "TIES",
            "hasSlur": "SLURS",
            "hasTuplet": "TUPLETS",
            "hasGrace": "GRACE_NOTES",
            "hasAccidental": "ACCIDENTALS",
        }
        for i in range(1, 6):
            pilot_id = f"osl_0{i}"
            fixture_id = f"poly_fixture_openscore_{pilot_id}_p1"
            fixture = json.loads((FIXTURE_DIR / f"{fixture_id}.json").read_text(encoding="utf-8"))
            observation = self.pilot_by_id[pilot_id]["structuralObservation"]
            expected_features = {label for key, label in mapping.items() if observation[key]}
            self.assertEqual(["PIANO_GRAND_STAFF"], fixture["classification"]["notationClasses"])
            self.assertEqual(expected_features, set(fixture["classification"]["notationFeatures"]))
            self.assertEqual(["CLEAN_OR_HIGH_QUALITY"], fixture["classification"]["scanConditions"])

    def test_harness_remains_not_ready_and_authority_does_not_expand(self) -> None:
        report = build_report(REGISTRY)
        self.assertEqual(10, report["fixtureCount"])
        self.assertEqual(10, report["verifiedFixtureCount"])
        self.assertEqual(10, report["eligibleVerifiedFixtureCount"])
        self.assertEqual(0, report["separatelyTrainingAuthorizedFixtureCount"])
        self.assertEqual("NOT_READY", report["readiness"])
        self.assertFalse(report["claims"]["generalAccuracyClaim"])
        self.assertFalse(report["claims"]["productionDecisionAuthority"])
        self.assertFalse(report["claims"]["teacherCorrectionsAutomaticallyTrainingData"])


if __name__ == "__main__":
    unittest.main()
