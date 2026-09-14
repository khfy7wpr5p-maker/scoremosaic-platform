import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "evidence" / "musescore-system-direction-compat-v1.json"
REGISTRY = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"


class TeacherGoldRendererDirectionCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_exact_renderer_lineage_is_pinned(self):
        renderers = self.evidence["renderers"]
        self.assertEqual(
            renderers["museScore362"]["appImageSha256"],
            "c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290",
        )
        self.assertEqual(
            renderers["museScore465"]["appImageSha256"],
            "193daa0ea18bcfa90a47145a842275b8069b7b2b8d153e562b15fab5fe50fcaf",
        )

    def test_targeted_results_remain_one_fixed_and_four_noncompliant(self):
        decisions = {r["reviewId"]: r["compatibilityDecision"] for r in self.evidence["records"]}
        self.assertEqual(
            decisions,
            {
                "TG019": "FIXED_IN_4_6_5",
                "TG036": "ONLY_TOP_NONCOMPLIANT_4_6_5",
                "TG066": "ONLY_TOP_NONCOMPLIANT_4_6_5",
                "TG081": "ONLY_TOP_NONCOMPLIANT_4_6_5",
                "TG083": "ONLY_TOP_NONCOMPLIANT_4_6_5",
            },
        )
        conclusion = self.evidence["conclusion"]
        self.assertEqual(conclusion["museScore465TargetedCasesFullyFixed"], 1)
        self.assertEqual(conclusion["museScore465TargetedCasesStillNoncompliant"], 4)
        self.assertEqual(conclusion["rootCauseClass"], "RENDERER_IMPORT_COMPATIBILITY")
        self.assertFalse(conclusion["xmlCorruptionDetected"])
        self.assertFalse(conclusion["userPlaybackSystemImplicated"])

    def test_compatibility_evidence_cannot_expand_authority(self):
        boundaries = self.evidence["boundaries"]
        self.assertEqual(
            boundaries,
            {
                "teacherGoldRegistryMutation": False,
                "teacherGoldCountMutation": False,
                "modelTrainingAuthorizationMutation": False,
                "stage7EngineOrQuorumMutation": False,
                "automaticCorrectionOrMergeMutation": False,
                "productionDecisionAuthorityMutation": False,
            },
        )

    def test_teacher_gold_registry_is_still_ten_fixtures(self):
        self.assertEqual(len(self.registry["fixtureRecords"]), 10)
        self.assertEqual(self.registry["minimumVerifiedFixtures"], 500)
        self.assertEqual(self.registry["targetVerifiedFixtures"], 1000)


if __name__ == "__main__":
    unittest.main()
