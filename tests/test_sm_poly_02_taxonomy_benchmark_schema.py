from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = json.loads(
    (ROOT / "contracts" / "polyphonic-error-taxonomy-v1.json").read_text(encoding="utf-8")
)
SCHEMA = json.loads(
    (ROOT / "contracts" / "polyphonic-benchmark-fixture-v1.schema.json").read_text(
        encoding="utf-8"
    )
)
COMPARISON_SCHEMA = json.loads(
    (ROOT / "contracts" / "ensemble-comparison-report-v1.schema.json").read_text(
        encoding="utf-8"
    )
)
ARCHITECTURE = json.loads(
    (ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8")
)
DOC = (ROOT / "docs" / "sm-poly-02-polyphonic-taxonomy-benchmark-schema.md").read_text(
    encoding="utf-8"
)


REQUIRED_MINIMUM = {
    "PITCH",
    "DURATION",
    "ONSET",
    "VOICE",
    "STAFF",
    "REST",
    "ACCIDENTAL",
    "TIE",
    "SLUR",
    "TUPLET",
    "BEAM",
    "STEM",
    "CHORD_GROUPING",
    "CROSS_STAFF",
    "METER",
    "MEASURE_BOUNDARY",
    "GRACE",
    "ORNAMENT",
    "OTHER",
    "AMBIGUOUS",
}


class SmPoly02TaxonomyBenchmarkSchemaTests(unittest.TestCase):
    def test_taxonomy_identity_and_authority_boundaries(self) -> None:
        self.assertEqual("scoremosaic-polyphonic-error-taxonomy-v1", TAXONOMY["version"])
        self.assertEqual("RESEARCH_EVALUATION_ONLY", TAXONOMY["status"])
        self.assertIs(TAXONOMY["authoritativeMusicalTruth"], False)
        self.assertIs(TAXONOMY["automaticDecisionAuthority"], False)

        boundaries = TAXONOMY["boundaries"]
        for key in (
            "doesNotReplaceComparatorVocabulary",
            "doesNotChangeStage7Quorum",
            "doesNotRankEngines",
            "doesNotSelectWinner",
            "doesNotMergeMusicXml",
            "doesNotApplyCorrection",
            "doesNotOverrideTeacher",
            "ambiguousIsValidOutcome",
        ):
            self.assertIs(boundaries[key], True, key)

    def test_required_taxonomy_is_complete_unique_and_preserves_current_fields(self) -> None:
        codes = [item["code"] for item in TAXONOMY["categories"]]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(REQUIRED_MINIMUM.issubset(set(codes)))
        self.assertIn("DOT", codes)
        self.assertIn("TAB_POSITION", codes)

    def test_current_comparator_vocabulary_has_explicit_compatibility_mapping(self) -> None:
        current_categories = set(
            COMPARISON_SCHEMA["$defs"]["difference"]["properties"]["category"]["enum"]
        )
        compatibility = TAXONOMY["legacyComparatorCompatibility"]
        self.assertEqual(current_categories, set(compatibility))

        taxonomy_codes = {item["code"] for item in TAXONOMY["categories"]}
        for legacy, mapping in compatibility.items():
            with self.subTest(legacy=legacy):
                self.assertGreaterEqual(len(mapping["targets"]), 1)
                self.assertTrue(set(mapping["targets"]).issubset(taxonomy_codes))

        self.assertIs(compatibility["measure"]["requiresRefinement"], True)
        self.assertEqual(["DOT"], compatibility["dot"]["targets"])
        self.assertEqual(["TAB_POSITION"], compatibility["tab"]["targets"])

    def test_fixture_schema_taxonomy_enum_cannot_drift(self) -> None:
        taxonomy_codes = [item["code"] for item in TAXONOMY["categories"]]
        schema_codes = SCHEMA["$defs"]["errorCode"]["enum"]
        self.assertEqual(taxonomy_codes, schema_codes)

    def test_fixture_schema_covers_required_polyphonic_classes_and_conditions(self) -> None:
        classification = SCHEMA["$defs"]["classification"]["properties"]
        notation_classes = set(classification["notationClasses"]["items"]["enum"])
        self.assertTrue(
            {
                "MONOPHONIC",
                "VOICE_2",
                "VOICE_3",
                "VOICE_4_PLUS",
                "PIANO_GRAND_STAFF",
                "DENSE_PIANO_CHORD",
                "CLASSICAL_GUITAR_POLYPHONY",
                "INDEPENDENT_GUITAR_VOICES",
                "CROSS_STAFF_NOTATION",
            }.issubset(notation_classes)
        )

        notation_features = set(classification["notationFeatures"]["items"]["enum"])
        self.assertTrue(
            {
                "TIES",
                "SLURS",
                "TUPLETS",
                "GRACE_NOTES",
                "PICKUP_MEASURES",
                "IRREGULAR_MEASURES",
                "RESTS_IN_MULTIPLE_VOICES",
                "OVERLAPPING_DURATIONS",
                "ACCIDENTALS",
                "BEAMING",
                "STEM_DIRECTION_AMBIGUITY",
                "VOICE_REASSIGNMENT",
                "STAFF_REASSIGNMENT",
            }.issubset(notation_features)
        )

        scan_conditions = set(classification["scanConditions"]["items"]["enum"])
        self.assertTrue(
            {
                "LOW_QUALITY_SCAN",
                "SKEW",
                "ROTATION",
                "PHONE_PHOTOGRAPH",
                "PERSPECTIVE_DISTORTION",
                "LOW_CONTRAST",
                "DAMAGED_OR_DIRTY_SCORE",
            }.issubset(scan_conditions)
        )

    def test_teacher_gold_and_training_boundaries_are_fail_closed(self) -> None:
        gold = SCHEMA["$defs"]["gold"]["properties"]
        self.assertIs(gold["separateFromEngineOutputs"]["const"], True)
        self.assertIs(gold["teacherCorrectionAutomaticallyTrainingData"]["const"], False)
        self.assertEqual(
            ["NOT_AUTHORIZED", "SEPARATELY_AUTHORIZED"],
            gold["trainingAuthorization"]["enum"],
        )
        self.assertNotIn("engineOutputs", SCHEMA["properties"])

        boundaries = SCHEMA["$defs"]["boundaries"]["properties"]
        self.assertIs(boundaries["researchEvaluationOnly"]["const"], True)
        self.assertIs(boundaries["engineOutputsStoredSeparately"]["const"], True)
        self.assertIs(boundaries["automaticWinnerSelection"]["const"], False)
        self.assertIs(boundaries["automaticMusicXmlMerge"]["const"], False)
        self.assertIs(boundaries["automaticSemanticRepair"]["const"], False)
        self.assertIs(boundaries["teacherAuthority"]["const"], True)
        self.assertIs(boundaries["productionDecisionAuthority"]["const"], False)

    def test_license_metadata_is_explicit_and_closed(self) -> None:
        license_metadata = SCHEMA["$defs"]["licenseMetadata"]
        self.assertIs(license_metadata["additionalProperties"], False)
        required = set(license_metadata["required"])
        self.assertTrue(
            {
                "dataset",
                "version",
                "source",
                "license",
                "redistributionStatus",
                "trainingAllowed",
                "evaluationAllowed",
                "commercialUseImplications",
            }.issubset(required)
        )

    def test_package_does_not_change_current_engine_or_production_authority(self) -> None:
        current_omr = ARCHITECTURE["currentOmr"]
        self.assertEqual(["audiveris", "homr", "clarity"], current_omr["productionCandidateEngines"])
        self.assertEqual(2, current_omr["stage7MinimumCanonicalCandidates"])
        self.assertIs(current_omr["stOmrIntegratedIntoGateway"], False)
        self.assertIs(current_omr["automaticWinnerAuthority"], False)
        self.assertIs(ARCHITECTURE["production"]["productionReady"], False)
        self.assertIs(ARCHITECTURE["teacherReview"]["productionWriteActivated"], False)

    def test_documentation_records_non_duplicate_and_non_production_scope(self) -> None:
        for marker in (
            "existing frozen `evaluation/fixed-v1` regression dataset remains unchanged",
            "This schema contains no engine-output field",
            "does not modify",
            "SM-POLY-03",
        ):
            self.assertIn(marker, DOC)


if __name__ == "__main__":
    unittest.main()
