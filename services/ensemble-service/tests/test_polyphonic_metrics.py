from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "evaluation" / "fixed-v1" / "manifest.json"
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble import evaluate_candidate, load_fixed_dataset, normalize_musicxml
from scoremosaic_ensemble.polyphonic_metrics import (
    CURRENT_ENGINES,
    OBSERVATION_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    PolyphonicMetricError,
    aggregate_engine_semantic_metrics,
    build_parse_failure_observation,
    observation_from_fixed_evaluation_result,
    validate_semantic_observation,
)


OBSERVATION_SCHEMA = json.loads(
    (REPOSITORY_ROOT / "contracts" / "polyphonic-engine-semantic-observation-v1.schema.json").read_text(
        encoding="utf-8"
    )
)
REPORT_SCHEMA = json.loads(
    (REPOSITORY_ROOT / "contracts" / "polyphonic-engine-semantic-report-v1.schema.json").read_text(
        encoding="utf-8"
    )
)
ARCHITECTURE = json.loads(
    (REPOSITORY_ROOT / "contracts" / "architecture-current-state-v1.json").read_text(
        encoding="utf-8"
    )
)


class SmPoly04PerEngineSemanticMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_fixed_dataset(MANIFEST_PATH, REPOSITORY_ROOT)
        cls.case = cls.dataset["cases"][0]
        cls.reference_sha = cls.case["reference"]["sha256"]
        cls.fixture_id = "poly_fixture_fixedv1case01"
        cls.results = {}
        cls.observations = {}
        for candidate in cls.case["candidates"]:
            path = REPOSITORY_ROOT / candidate["path"]
            score = normalize_musicxml(
                path.read_bytes(),
                engine=candidate["engine"],
                engine_version=candidate["engineVersion"],
                model_version=candidate["modelVersion"],
                artifact_ref=candidate["path"],
            )
            result = evaluate_candidate(score, cls.dataset, cls.case["caseId"]).as_dict()
            cls.results[candidate["engine"]] = result
            cls.observations[candidate["engine"]] = observation_from_fixed_evaluation_result(
                result,
                fixture_id=cls.fixture_id,
                reference_artifact_sha256=cls.reference_sha,
            )

    def test_contract_versions_and_current_engine_scope_are_closed(self) -> None:
        self.assertEqual(
            OBSERVATION_SCHEMA_VERSION,
            OBSERVATION_SCHEMA["properties"]["schemaVersion"]["const"],
        )
        self.assertEqual(
            REPORT_SCHEMA_VERSION,
            REPORT_SCHEMA["properties"]["schemaVersion"]["const"],
        )
        self.assertEqual(
            list(CURRENT_ENGINES),
            OBSERVATION_SCHEMA["$defs"]["engine"]["properties"]["name"]["enum"],
        )
        self.assertNotIn("st-omr", CURRENT_ENGINES)
        self.assertNotIn("st_omr", CURRENT_ENGINES)

    def test_existing_evaluation_metrics_are_reused_without_reclassifying_fixed_v1(self) -> None:
        result = self.results["audiveris"]
        observation = self.observations["audiveris"]
        metric_map = {item["name"]: item for item in result["metrics"]}

        self.assertEqual(OBSERVATION_SCHEMA_VERSION, observation["schemaVersion"])
        self.assertEqual("MANUALLY_REVIEWED_FIXED_BASELINE", observation["reference"]["kind"])
        self.assertEqual(result["resultSha256"], observation["sourceEvaluationResultSha256"])
        self.assertEqual(result["candidate"]["artifactSha256"], observation["engine"]["candidateArtifactSha256"])
        self.assertEqual(result["candidate"]["canonicalSha256"], observation["engine"]["canonicalSha256"])
        self.assertEqual(
            metric_map["pitch"]["correct"], observation["semanticMetrics"]["pitch"]["correct"]
        )
        self.assertEqual(
            metric_map["effectiveDuration"]["correct"],
            observation["semanticMetrics"]["duration"]["correct"],
        )
        self.assertEqual(
            metric_map["onset"]["correct"], observation["semanticMetrics"]["onset"]["correct"]
        )
        self.assertEqual(
            metric_map["voice"]["correct"], observation["semanticMetrics"]["voice"]["correct"]
        )
        self.assertEqual(
            metric_map["staff"]["correct"], observation["semanticMetrics"]["staff"]["correct"]
        )
        self.assertEqual(
            metric_map["ties"]["correct"], observation["semanticMetrics"]["tie"]["correct"]
        )
        self.assertEqual(
            metric_map["tuplet"]["correct"], observation["semanticMetrics"]["tuplet"]["correct"]
        )

    def test_relation_and_structure_methods_are_explicit_and_bounded(self) -> None:
        result = self.results["homr"]
        observation = self.observations["homr"]
        metric_map = {item["name"]: item for item in result["metrics"]}

        expected_relation_correct = sum(
            metric_map[name]["correct"] for name in ("ties", "tuplet", "chord")
        )
        expected_relation_total = sum(
            metric_map[name]["total"] for name in ("ties", "tuplet", "chord")
        )
        self.assertEqual("TIE_TUPLET_CHORD_EXACT_V1", observation["relationCorrectness"]["method"])
        self.assertEqual(expected_relation_correct, observation["relationCorrectness"]["correct"])
        self.assertEqual(expected_relation_total, observation["relationCorrectness"]["total"])

        counts = result["counts"]
        event_presence = metric_map["eventPresence"]
        numerator = (
            abs(counts["reference"]["partCount"] - counts["candidate"]["partCount"])
            + abs(counts["reference"]["measureCount"] - counts["candidate"]["measureCount"])
            + event_presence["incorrect"]
        )
        denominator = max(
            1,
            counts["reference"]["partCount"]
            + counts["reference"]["measureCount"]
            + event_presence["total"],
        )
        expected = Fraction(numerator, denominator)
        self.assertEqual("CANONICAL_STRUCTURE_DISTANCE_V1", observation["structuralDistance"]["method"])
        self.assertEqual(expected.numerator, observation["structuralDistance"]["numerator"])
        self.assertEqual(expected.denominator, observation["structuralDistance"]["denominator"])

    def test_teacher_edits_are_unavailable_not_zero_in_fixed_compatibility_observations(self) -> None:
        for observation in self.observations.values():
            self.assertIs(observation["teacherEdits"]["available"], False)
            self.assertEqual("UNAVAILABLE", observation["teacherEdits"]["method"])
            self.assertIsNone(observation["teacherEdits"]["editCount"])
            self.assertIsNone(observation["teacherEdits"]["measureCount"])
            self.assertIsNone(observation["teacherEdits"]["pageCount"])

    def test_parse_failure_is_counted_without_inventing_semantic_evidence(self) -> None:
        failed = build_parse_failure_observation(
            fixture_id="poly_fixture_parsefail01",
            reference_kind="TEACHER_GOLD",
            reference_artifact_sha256="c" * 64,
            engine="audiveris",
            engine_version="test-1",
            model_version="test-1",
            candidate_artifact_sha256="d" * 64,
        )
        self.assertIs(failed["parse"]["success"], False)
        self.assertIs(failed["structuralValidity"]["available"], False)
        self.assertTrue(
            all(metric["available"] is False for metric in failed["semanticMetrics"].values())
        )
        self.assertIs(failed["structuralDistance"]["available"], False)

        report = aggregate_engine_semantic_metrics(
            [self.observations["audiveris"], failed]
        )
        engine = report["engineReports"][0]
        self.assertEqual("audiveris", engine["engine"])
        self.assertEqual(1, engine["musicXmlParseSuccess"]["success"])
        self.assertEqual(2, engine["musicXmlParseSuccess"]["attempted"])
        self.assertEqual({"numerator": 1, "denominator": 2}, engine["musicXmlParseSuccess"]["ratio"])
        self.assertEqual(1, engine["semanticMetrics"]["pitch"]["availableObservationCount"])

    def test_report_keeps_each_engine_separate_and_has_no_overall_accuracy(self) -> None:
        report = aggregate_engine_semantic_metrics(self.observations.values())
        self.assertEqual("RESEARCH_METRICS_AVAILABLE", report["status"])
        self.assertEqual(3, report["observationCount"])
        self.assertEqual(list(CURRENT_ENGINES), [item["engine"] for item in report["engineReports"]])
        self.assertIsNone(report["metricPolicy"]["singleAggregateAccuracyScore"])
        self.assertIs(report["metricPolicy"]["engineRanking"], False)
        self.assertIs(report["metricPolicy"]["winnerSelection"], False)
        self.assertIs(report["metricPolicy"]["tednClaimed"], False)
        self.assertEqual("CANONICAL_STRUCTURE_DISTANCE_V1", report["metricPolicy"]["structuralDistanceMethod"])
        for engine in report["engineReports"]:
            self.assertIn("pitch", engine["semanticMetrics"])
            self.assertIn("duration", engine["semanticMetrics"])
            self.assertIn("onset", engine["semanticMetrics"])
            self.assertIn("voice", engine["semanticMetrics"])
            self.assertIn("staff", engine["semanticMetrics"])
            self.assertIn("tie", engine["semanticMetrics"])
            self.assertIn("tuplet", engine["semanticMetrics"])

    def test_empty_report_is_deterministic_and_non_authoritative(self) -> None:
        first = aggregate_engine_semantic_metrics([])
        second = aggregate_engine_semantic_metrics([])
        self.assertEqual(first, second)
        self.assertEqual("NO_OBSERVATIONS", first["status"])
        self.assertEqual([], first["engineReports"])
        self.assertIs(first["boundaries"]["productionDecisionAuthority"], False)
        without_hash = dict(first)
        report_sha = without_hash.pop("reportSha256")
        expected = sha256(
            json.dumps(
                without_hash,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()
        self.assertEqual(expected, report_sha)

    def test_future_teacher_edit_evidence_aggregates_as_exact_workload_ratios(self) -> None:
        observation = deepcopy(self.observations["clarity"])
        observation["teacherEdits"] = {
            "available": True,
            "method": "TEACHER_REVISION_COMMAND_COUNT_V1",
            "editCount": 3,
            "measureCount": 4,
            "pageCount": 1,
        }
        validate_semantic_observation(observation)
        report = aggregate_engine_semantic_metrics([observation])
        workload = report["engineReports"][0]["teacherEdits"]
        self.assertEqual(1, workload["availableObservationCount"])
        self.assertEqual({"numerator": 3, "denominator": 4}, workload["editsPerMeasure"])
        self.assertEqual({"numerator": 3, "denominator": 1}, workload["editsPerPage"])
        self.assertIs(report["boundaries"]["teacherApproval"], False)

    def test_duplicate_engine_fixture_observations_fail_closed(self) -> None:
        observation = self.observations["audiveris"]
        with self.assertRaisesRegex(PolyphonicMetricError, "duplicate_metric_observation"):
            aggregate_engine_semantic_metrics([observation, deepcopy(observation)])

    def test_st_omr_cannot_enter_sm_poly_04_v1(self) -> None:
        observation = deepcopy(self.observations["audiveris"])
        observation["engine"]["name"] = "st-omr"
        with self.assertRaisesRegex(PolyphonicMetricError, "engine_invalid"):
            validate_semantic_observation(observation)

    def test_parse_failure_cannot_smuggle_semantic_or_canonical_evidence(self) -> None:
        failed = build_parse_failure_observation(
            fixture_id="poly_fixture_parsefail02",
            reference_kind="TEACHER_GOLD",
            reference_artifact_sha256="e" * 64,
            engine="homr",
            engine_version="test-1",
            model_version="test-1",
            candidate_artifact_sha256="f" * 64,
        )
        failed["semanticMetrics"]["pitch"] = {"available": True, "correct": 1, "total": 1}
        with self.assertRaisesRegex(PolyphonicMetricError, "parse_failure_semantic_evidence_invalid"):
            validate_semantic_observation(failed)

        failed = build_parse_failure_observation(
            fixture_id="poly_fixture_parsefail03",
            reference_kind="TEACHER_GOLD",
            reference_artifact_sha256="1" * 64,
            engine="clarity",
            engine_version="test-1",
            model_version="test-1",
            candidate_artifact_sha256="2" * 64,
        )
        failed["engine"]["canonicalSha256"] = "3" * 64
        with self.assertRaisesRegex(PolyphonicMetricError, "parse_failure_evidence_invalid"):
            validate_semantic_observation(failed)

    def test_current_authority_invariants_remain_unchanged(self) -> None:
        current = ARCHITECTURE["currentOmr"]
        self.assertEqual(["audiveris", "homr", "clarity"], current["productionCandidateEngines"])
        self.assertEqual(2, current["stage7MinimumCanonicalCandidates"])
        self.assertIs(current["stOmrIntegratedIntoGateway"], False)
        self.assertIs(current["automaticWinnerAuthority"], False)
        self.assertIs(ARCHITECTURE["teacherReview"]["productionWriteActivated"], False)
        self.assertIs(ARCHITECTURE["production"]["productionReady"], False)


if __name__ == "__main__":
    unittest.main()
