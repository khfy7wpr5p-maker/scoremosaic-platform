import io
import json
from pathlib import Path
import unittest
import zipfile

from scripts.musicxml_direction_system_semantic_gate import (
    ALLOWED_SYSTEM_RELATIONS,
    DirectionSystemSemanticGateError,
    build_report,
    route_renderer_mismatch,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "musicxml-direction-system-semantic-gate-v1.json"
EVIDENCE = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "evidence" / "musescore-system-direction-compat-v1.json"
REGISTRY = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"


def score_with_direction(system: str | None, text: str = "rit.") -> bytes:
    system_attr = "" if system is None else f' system="{system}"'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <direction placement="above"{system_attr}>
        <direction-type><words>{text}</words></direction-type>
      </direction>
      <attributes><divisions>1</divisions></attributes>
      <note><rest/><duration>4</duration><voice>1</voice><type>whole</type></note>
    </measure>
  </part>
</score-partwise>
'''.encode("utf-8")


def as_mxl(payload: bytes) -> bytes:
    container = b'''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="score.musicxml" media-type="application/vnd.recordare.musicxml+xml"/>
  </rootfiles>
</container>
'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("score.musicxml", payload)
    return output.getvalue()


class MusicXmlDirectionSystemSemanticGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_contract_matches_musicxml_4_system_relation_values(self):
        self.assertEqual(
            set(self.contract["specificationBasis"]["allowedValues"]),
            ALLOWED_SYSTEM_RELATIONS,
        )
        self.assertEqual(ALLOWED_SYSTEM_RELATIONS, {"only-top", "also-top", "none"})

    def test_only_top_is_valid_and_renderer_sensitive(self):
        report = build_report(score_with_direction("only-top"), source_name="only-top.musicxml")
        self.assertEqual(report["status"], "VALID_DIRECTION_SYSTEM_SEMANTICS")
        self.assertEqual(report["rendererSensitiveDirectionCount"], 1)
        self.assertEqual(report["systemRelationCounts"], {"only-top": 1})
        self.assertFalse(report["teacherReviewRequiredByThisGate"])
        self.assertFalse(report["sourceMutationAuthorized"])

        route = route_renderer_mismatch(
            report,
            implicated_system_relations=["only-top"],
        )
        self.assertEqual(route["decision"], "RENDERER_COMPATIBILITY_REVIEW_REQUIRED")
        self.assertFalse(route["teacherReviewRequired"])
        self.assertTrue(route["technicalReviewRequired"])
        self.assertFalse(route["symbolicReferenceRejected"])
        self.assertFalse(route["automaticMusicXmlRepairAuthorized"])

    def test_also_top_is_valid_and_renderer_sensitive(self):
        report = build_report(score_with_direction("also-top"))
        self.assertEqual(report["status"], "VALID_DIRECTION_SYSTEM_SEMANTICS")
        route = route_renderer_mismatch(
            report,
            implicated_system_relations=["also-top"],
        )
        self.assertEqual(route["decision"], "RENDERER_COMPATIBILITY_REVIEW_REQUIRED")
        self.assertFalse(route["teacherReviewRequired"])

    def test_none_is_valid_but_not_a_known_renderer_suppression_case(self):
        report = build_report(score_with_direction("none"))
        self.assertEqual(report["status"], "VALID_DIRECTION_SYSTEM_SEMANTICS")
        self.assertEqual(report["rendererSensitiveDirectionCount"], 0)
        route = route_renderer_mismatch(
            report,
            implicated_system_relations=["none"],
        )
        self.assertEqual(route["decision"], "TEACHER_REVIEW_REQUIRED")
        self.assertTrue(route["teacherReviewRequired"])

    def test_missing_system_attribute_is_not_applicable(self):
        report = build_report(score_with_direction(None))
        self.assertEqual(report["status"], "NOT_APPLICABLE_NO_DIRECTION_SYSTEM")
        self.assertEqual(report["directionSystemRecordCount"], 0)
        self.assertFalse(report["teacherReviewRequiredByThisGate"])

    def test_unknown_system_relation_routes_to_technical_semantic_review(self):
        report = build_report(score_with_direction("future-top"))
        self.assertEqual(report["status"], "SEMANTIC_VALIDATION_REVIEW_REQUIRED")
        self.assertEqual(report["invalidSystemRelations"], ["future-top"])
        self.assertTrue(report["technicalReviewRequired"])
        self.assertFalse(report["teacherReviewRequiredByThisGate"])
        self.assertFalse(report["symbolicReferenceEligibleForFurtherEvaluation"])

    def test_mxl_container_is_supported_without_extraction(self):
        payload = score_with_direction("only-top", "poco rall.")
        report = build_report(as_mxl(payload), source_name="fixture.mxl")
        self.assertEqual(report["musicXmlMember"], "score.musicxml")
        self.assertEqual(report["systemRelationCounts"], {"only-top": 1})
        self.assertEqual(report["records"][0]["text"], "poco rall.")

    def test_malformed_xml_fails_closed(self):
        with self.assertRaises(DirectionSystemSemanticGateError):
            build_report(b"<score-partwise>")

    def test_ambiguous_mxl_without_container_fails_closed(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("a.musicxml", score_with_direction("only-top"))
            zf.writestr("b.musicxml", score_with_direction("also-top"))
        with self.assertRaises(DirectionSystemSemanticGateError):
            build_report(output.getvalue())

    def test_renderer_mismatch_without_explicit_relation_fails_closed_to_teacher_review(self):
        report = build_report(score_with_direction("only-top"))
        route = route_renderer_mismatch(report, implicated_system_relations=None)
        self.assertEqual(route["decision"], "TEACHER_REVIEW_REQUIRED")
        self.assertTrue(route["teacherReviewRequired"])

    def test_compatibility_evidence_relations_are_all_semantically_known(self):
        found = set()
        for record in self.evidence["records"]:
            for direction in record["targetDirections"]:
                found.add(direction["system"])
                self.assertIn(direction["system"], ALLOWED_SYSTEM_RELATIONS)
        self.assertEqual(found, {"only-top", "also-top"})

    def test_known_five_are_renderer_compatibility_evidence_not_xml_corruption(self):
        self.assertEqual(
            {record["reviewId"] for record in self.evidence["records"]},
            {"TG019", "TG036", "TG066", "TG081", "TG083"},
        )
        self.assertEqual(
            self.evidence["conclusion"]["rootCauseClass"],
            "RENDERER_IMPORT_COMPATIBILITY",
        )
        self.assertFalse(self.evidence["conclusion"]["xmlCorruptionDetected"])
        self.assertFalse(self.evidence["conclusion"]["userPlaybackSystemImplicated"])

    def test_authority_boundaries_remain_closed(self):
        boundaries = self.contract["authorityBoundaries"]
        self.assertFalse(boundaries["rendererIsFidelityOracle"])
        self.assertFalse(boundaries["sourceMutationAuthorized"])
        self.assertFalse(boundaries["automaticMusicXmlRepairAuthorized"])
        self.assertFalse(boundaries["teacherGoldAdmissionAuthorized"])
        self.assertFalse(boundaries["teacherGoldCountMutationAuthorized"])
        self.assertFalse(boundaries["modelTrainingAuthorized"])
        self.assertFalse(boundaries["stage7EngineOrQuorumMutationAuthorized"])
        self.assertFalse(boundaries["automaticCorrectionOrMergeAuthorized"])
        self.assertFalse(boundaries["productionDecisionAuthorityGranted"])

    def test_teacher_gold_registry_remains_ten_of_five_hundred(self):
        self.assertEqual(len(self.registry["fixtureRecords"]), 10)
        self.assertEqual(self.registry["minimumVerifiedFixtures"], 500)
        self.assertEqual(self.registry["targetVerifiedFixtures"], 1000)


if __name__ == "__main__":
    unittest.main()
