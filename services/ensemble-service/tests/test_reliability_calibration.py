import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble import reliability_calibration as rc

OBSERVATION_SCHEMA = json.loads((REPOSITORY_ROOT / "contracts" / "engine-reliability-observation-v1.schema.json").read_text(encoding="utf-8"))
REPORT_SCHEMA = json.loads((REPOSITORY_ROOT / "contracts" / "engine-reliability-report-v1.schema.json").read_text(encoding="utf-8"))
ARCHITECTURE = json.loads((REPOSITORY_ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def complexity(**overrides):
    value = {
        "available": True,
        "profileId": "complexity_" + "1" * 24,
        "profileSha256": "d" * 64,
        "voiceCount": 2,
        "maxSimultaneousVoiceCount": 2,
        "multiStaffPresent": False,
        "tupletPresent": False,
        "overlapDensityBasisPoints": 2500,
    }
    value.update(overrides)
    return value


def quality(**overrides):
    value = {
        "available": True,
        "profileId": "source_quality_" + "2" * 24,
        "profileSha256": "e" * 64,
        "severity": "MODERATE",
        "maxDegradationRiskBasisPoints": 3000,
    }
    value.update(overrides)
    return value


def obs(*, correct=True, confidence=8000, engine="audiveris", category="pitch", unit="event-1", comp=True, qual=True):
    return rc.build_reliability_observation(
        fixture_id="poly_fixture_fixture001",
        target_category=category,
        target_unit_id=unit,
        correct=correct,
        engine=engine,
        engine_version="1.0",
        model_version="model-1",
        confidence_basis_points=confidence,
        confidence_evidence_source="REPOSITORY_RESEARCH_FIXTURE" if confidence is not None else None,
        confidence_method_version="native-confidence-v1" if confidence is not None else None,
        teacher_gold_reference_sha256=SHA_A,
        semantic_evidence_sha256=SHA_B,
        context_binding_method_version="benchmark-binding-v1",
        complexity=complexity() if comp else None,
        source_quality=quality() if qual else None,
    )


class ReliabilityCalibrationTests(unittest.TestCase):
    def test_contracts_are_closed_and_research_only(self):
        self.assertFalse(OBSERVATION_SCHEMA["additionalProperties"])
        self.assertFalse(REPORT_SCHEMA["additionalProperties"])
        self.assertIn("boundaries", OBSERVATION_SCHEMA["required"])
        self.assertIn("observationSetSha256", REPORT_SCHEMA["required"])
        self.assertIn("reportSha256", REPORT_SCHEMA["required"])

    def test_authority_regression_matches_architecture(self):
        current = ARCHITECTURE["currentOmr"]
        self.assertEqual(current["productionCandidateEngines"], ["audiveris", "homr", "clarity"])
        self.assertEqual(current["stage7MinimumCanonicalCandidates"], 2)
        self.assertFalse(current["stOmrIntegratedIntoGateway"])
        self.assertFalse(current["automaticWinnerAuthority"])
        self.assertFalse(ARCHITECTURE["teacherReview"]["productionWriteActivated"])
        self.assertFalse(rc._BOUNDARIES["winnerSelection"])
        self.assertFalse(rc._BOUNDARIES["productionThreshold"])
        self.assertFalse(rc._BOUNDARIES["selectivePrediction"])
        self.assertFalse(rc._BOUNDARIES["stage7QuorumChange"])
        self.assertFalse(rc._BOUNDARIES["stOmrIntegration"])

    def test_observation_is_deterministic_and_hash_pinned(self):
        one = obs()
        two = obs()
        self.assertEqual(one, two)
        self.assertEqual(len(one["observationSha256"]), 64)
        self.assertEqual(one["boundaries"]["productionDecisionAuthority"], False)
        self.assertEqual(one["confidence"]["calibratedInput"], False)

    def test_missing_confidence_is_unavailable_not_zero(self):
        item = obs(confidence=None)
        self.assertFalse(item["confidence"]["available"])
        self.assertIsNone(item["confidence"]["basisPoints"])
        report = rc.build_reliability_report([item])
        self.assertEqual(report["observationCount"], 1)
        self.assertEqual(report["eligibleObservationCount"], 0)
        self.assertEqual(report["groups"], [])

    def test_exact_brier_and_ece(self):
        items = [
            obs(correct=True, confidence=8000, unit="e1"),
            obs(correct=False, confidence=8000, unit="e2"),
        ]
        report = rc.build_reliability_report(items)
        group = report["groups"][0]
        self.assertEqual(group["brierScore"], {"numerator": 17, "denominator": 50})
        self.assertEqual(group["expectedCalibrationError"], {"numerator": 3, "denominator": 10})
        self.assertEqual(group["empiricalAccuracy"], {"numerator": 1, "denominator": 2})
        self.assertEqual(group["meanReportedConfidenceBasisPoints"], {"numerator": 8000, "denominator": 1})

    def test_fixed_bins_cover_zero_and_ten_thousand(self):
        items = [
            obs(correct=False, confidence=0, unit="e0"),
            obs(correct=True, confidence=10000, unit="e10"),
        ]
        bins = rc.build_reliability_report(items)["groups"][0]["reliabilityBins"]
        self.assertEqual(bins[0]["observationCount"], 1)
        self.assertEqual(bins[9]["observationCount"], 1)
        self.assertEqual(bins[9]["upperInclusiveBasisPoints"], 10000)

    def test_context_slices_are_componentized(self):
        report = rc.build_reliability_report([obs()])
        pairs = {(item["dimension"], item["value"]) for item in report["contextSlices"]}
        self.assertIn(("voiceCount", "2"), pairs)
        self.assertIn(("multiStaffPresent", "false"), pairs)
        self.assertIn(("tupletPresent", "false"), pairs)
        self.assertIn(("overlapDensityBand", "MODERATE"), pairs)
        self.assertIn(("sourceQualitySeverity", "MODERATE"), pairs)
        self.assertNotIn(("complexityScore", "2"), pairs)

    def test_groups_remain_per_engine_without_ranking(self):
        items = [
            obs(engine="audiveris", unit="a"),
            obs(engine="homr", unit="b", correct=False, confidence=4000),
            obs(engine="clarity", unit="c", confidence=6000),
        ]
        report = rc.build_reliability_report(items)
        self.assertEqual([g["engine"] for g in report["groups"]], ["audiveris", "homr", "clarity"])
        self.assertFalse(report["boundaries"]["engineRanking"])
        self.assertFalse(report["boundaries"]["winnerSelection"])
        self.assertIsNone(report["method"]["fittedCalibrationModel"])
        self.assertIsNone(report["method"]["recalibratedProbability"])

    def test_target_categories_are_separate(self):
        items = [obs(category="pitch", unit="p"), obs(category="voice", unit="v")]
        groups = rc.build_reliability_report(items)["groups"]
        self.assertEqual({g["category"] for g in groups}, {"pitch", "voice"})

    def test_missing_context_stays_unavailable(self):
        item = obs(comp=False, qual=False)
        self.assertFalse(item["context"]["complexity"]["available"])
        self.assertFalse(item["context"]["sourceQuality"]["available"])
        report = rc.build_reliability_report([item])
        self.assertEqual(report["groups"][0]["contextCoverage"], {
            "complexityObservationCount": 0,
            "sourceQualityObservationCount": 0,
        })
        self.assertEqual(report["contextSlices"], [])

    def test_observation_tamper_fails_closed(self):
        item = obs()
        tampered = copy.deepcopy(item)
        tampered["confidence"]["basisPoints"] = 9999
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "reliability_observation_hash_invalid"):
            rc.validate_reliability_observation(tampered)

    def test_rehashed_authority_tamper_fails_closed(self):
        item = obs()
        tampered = copy.deepcopy(item)
        tampered["boundaries"]["winnerSelection"] = True
        body = copy.deepcopy(tampered)
        body.pop("observationSha256")
        tampered["observationSha256"] = hashlib.sha256(rc._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "authority_boundary_invalid"):
            rc.validate_reliability_observation(tampered)

    def test_rehashed_observation_content_requires_derived_id(self):
        item = obs()
        tampered = copy.deepcopy(item)
        tampered["confidence"]["basisPoints"] = 7000
        body = copy.deepcopy(tampered)
        body.pop("observationSha256")
        tampered["observationSha256"] = hashlib.sha256(rc._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "reliability_observation_id_mismatch"):
            rc.validate_reliability_observation(tampered)

    def test_unavailable_confidence_rejects_smuggled_method_arguments(self):
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "confidence_evidence_invalid"):
            rc.build_reliability_observation(
                fixture_id="poly_fixture_fixture001",
                target_category="pitch",
                target_unit_id="event",
                correct=True,
                engine="audiveris",
                engine_version="1.0",
                model_version="model-1",
                confidence_basis_points=None,
                confidence_evidence_source="ENGINE_NATIVE_REPORTED",
                confidence_method_version="native-v1",
                teacher_gold_reference_sha256=SHA_A,
                semantic_evidence_sha256=SHA_B,
                context_binding_method_version="v1",
            )

    def test_same_target_and_confidence_method_cannot_be_double_counted(self):
        one = obs(confidence=7000)
        two = rc.build_reliability_observation(
            fixture_id="poly_fixture_fixture001",
            target_category="pitch",
            target_unit_id="event-1",
            correct=True,
            engine="audiveris",
            engine_version="1.0",
            model_version="model-1",
            confidence_basis_points=8000,
            confidence_evidence_source="REPOSITORY_RESEARCH_FIXTURE",
            confidence_method_version="native-confidence-v1",
            teacher_gold_reference_sha256=SHA_A,
            semantic_evidence_sha256=SHA_C,
            context_binding_method_version="benchmark-binding-v1",
            complexity=complexity(),
            source_quality=quality(),
        )
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "duplicate_reliability_target_unit"):
            rc.build_reliability_report([one, two])

    def test_report_tamper_fails_closed(self):
        report = rc.build_reliability_report([obs()])
        tampered = copy.deepcopy(report)
        tampered["reportId"] = "reliability_report_" + "f" * 24
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "reliability_report_hash_invalid"):
            rc.validate_reliability_report(tampered)

    def test_rehashed_metric_tamper_fails_against_observations(self):
        items = [obs(correct=True, confidence=8000, unit="e1"), obs(correct=False, confidence=8000, unit="e2")]
        report = rc.build_reliability_report(items)
        tampered = copy.deepcopy(report)
        tampered["groups"][0]["brierScore"] = {"numerator": 1, "denominator": 2}
        identity = copy.deepcopy(tampered)
        identity.pop("reportId")
        identity.pop("reportSha256")
        tampered["reportId"] = "reliability_report_" + hashlib.sha256(rc._canonical_json(identity)).hexdigest()[:24]
        body = copy.deepcopy(tampered)
        body.pop("reportSha256")
        tampered["reportSha256"] = hashlib.sha256(rc._canonical_json(body)).hexdigest()
        rc.validate_reliability_report(tampered)
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "reliability_report_recompute_mismatch"):
            rc.validate_reliability_report_against_observations(tampered, items)

    def test_observation_set_binding_rejects_wrong_source_set(self):
        one = obs(unit="one")
        two = obs(unit="two")
        report = rc.build_reliability_report([one])
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "observation_set_mismatch"):
            rc.validate_reliability_report_against_observations(report, [two])

    def test_report_rehashed_method_tamper_fails_closed(self):
        report = rc.build_reliability_report([obs()])
        tampered = copy.deepcopy(report)
        tampered["method"]["recalibratedProbability"] = {"fake": True}
        body = copy.deepcopy(tampered)
        body.pop("reportSha256")
        tampered["reportSha256"] = hashlib.sha256(rc._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "reliability_report_method_invalid"):
            rc.validate_reliability_report(tampered)

    def test_float_nan_and_bounds_rejected(self):
        item = obs()
        body = copy.deepcopy(item)
        body["confidence"]["basisPoints"] = 10001
        raw = copy.deepcopy(body)
        raw.pop("observationSha256")
        body["observationSha256"] = hashlib.sha256(rc._canonical_json(raw)).hexdigest()
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "confidence_evidence_invalid"):
            rc.validate_reliability_observation(body)

        with self.assertRaises(rc.ReliabilityCalibrationError):
            rc.build_reliability_observation(
                fixture_id="poly_fixture_fixture001",
                target_category="pitch",
                target_unit_id="event",
                correct=True,
                engine="audiveris",
                engine_version="1.0",
                model_version="model-1",
                confidence_basis_points=float("nan"),
                confidence_evidence_source="REPOSITORY_RESEARCH_FIXTURE",
                confidence_method_version="v1",
                teacher_gold_reference_sha256=SHA_A,
                semantic_evidence_sha256=SHA_B,
                context_binding_method_version="v1",
            )

    def test_duplicate_observation_rejected(self):
        item = obs()
        with self.assertRaisesRegex(rc.ReliabilityCalibrationError, "duplicate_reliability_observation"):
            rc.build_reliability_report([item, item])

    def test_order_independent_report_determinism(self):
        one = obs(unit="a", confidence=7000)
        two = obs(unit="b", correct=False, confidence=3000)
        report_a = rc.build_reliability_report([one, two])
        report_b = rc.build_reliability_report([two, one])
        self.assertEqual(report_a, report_b)


if __name__ == "__main__":
    unittest.main()
