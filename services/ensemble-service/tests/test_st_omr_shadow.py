import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble import st_omr_shadow as sm

OBS_SCHEMA = json.loads((REPOSITORY_ROOT / "contracts" / "st-omr-shadow-observation-v1.schema.json").read_text(encoding="utf-8"))
REPORT_SCHEMA = json.loads((REPOSITORY_ROOT / "contracts" / "st-omr-shadow-report-v1.schema.json").read_text(encoding="utf-8"))
ARCHITECTURE = json.loads((REPOSITORY_ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def metrics():
    return {name: (9, 10) for name in sm.SEMANTIC_METRICS}


def obs(**overrides):
    args = dict(
        fixture_id="poly_fixture_fixture001",
        reference_artifact_sha256=SHA_A,
        engine_version="0.9.0",
        model_version="0.9.0",
        model_manifest_sha256=SHA_B,
        model_artifact_sha256=SHA_C,
        training_code_revision="1" * 40,
        candidate_artifact_sha256=SHA_D,
        canonical_sha256=SHA_E,
        source_document_sha256=SHA_A,
        prepared_page_set_sha256=SHA_B,
        job_id="job-001",
        run_id="run-001",
        binding_method_version="shadow-binding-v1",
        parse_success=True,
        structural_validity=True,
        semantic_metrics=metrics(),
        measure_consistency=(1, 1),
        relation_correctness=(8, 10),
        complexity_profile_id="complexity_" + "1" * 24,
        complexity_profile_sha256=SHA_C,
        source_quality_profile_id="source_quality_" + "2" * 24,
        source_quality_profile_sha256=SHA_D,
    )
    args.update(overrides)
    return sm.build_shadow_observation(**args)


def baselines():
    return {"audiveris": "1" * 64, "homr": "2" * 64, "clarity": "3" * 64}


class StOmrShadowTests(unittest.TestCase):
    def test_contracts_are_closed_and_shadow_only(self):
        self.assertFalse(OBS_SCHEMA["additionalProperties"])
        self.assertFalse(REPORT_SCHEMA["additionalProperties"])
        self.assertEqual(OBS_SCHEMA["properties"]["engine"]["properties"]["name"]["const"], "st-omr")
        boundary_schema = OBS_SCHEMA["properties"]["boundaries"]
        if "$ref" in boundary_schema:
            boundary_schema = OBS_SCHEMA["$defs"][boundary_schema["$ref"].rsplit("/", 1)[-1]]
        self.assertFalse(boundary_schema["properties"]["productionEligible"]["const"])
        self.assertFalse(boundary_schema["properties"]["stage7QuorumContribution"]["const"])

    def test_authority_regression_matches_current_architecture(self):
        current = ARCHITECTURE["currentOmr"]
        self.assertEqual(current["productionCandidateEngines"], ["audiveris", "homr", "clarity"])
        self.assertEqual(current["stage7MinimumCanonicalCandidates"], 2)
        self.assertFalse(current["stOmrIntegratedIntoGateway"])
        self.assertFalse(current["automaticWinnerAuthority"])
        self.assertFalse(ARCHITECTURE["teacherReview"]["productionWriteActivated"])
        self.assertFalse(sm._BOUNDARIES["productionEligible"])
        self.assertFalse(sm._BOUNDARIES["stage7QuorumContribution"])
        self.assertFalse(sm._BOUNDARIES["gatewayIntegration"])

    def test_observation_is_deterministic_and_provenance_bound(self):
        one = obs()
        two = obs()
        self.assertEqual(one, two)
        self.assertEqual(one["engine"]["modelManifestSha256"], SHA_B)
        self.assertEqual(one["engine"]["modelArtifactSha256"], SHA_C)
        self.assertEqual(one["engine"]["trainingCodeRevision"], "1" * 40)
        self.assertEqual(one["runBinding"]["sourceDocumentSha256"], SHA_A)
        self.assertEqual(one["runBinding"]["preparedPageSetSha256"], SHA_B)

    def test_parse_failure_requires_unavailable_semantics(self):
        empty = {name: None for name in sm.SEMANTIC_METRICS}
        item = obs(
            parse_success=False,
            structural_validity=None,
            canonical_sha256=None,
            semantic_metrics=empty,
            measure_consistency=None,
            relation_correctness=None,
        )
        self.assertFalse(item["parse"]["success"])
        with self.assertRaisesRegex(sm.StOmrShadowError, "parse_failure_evidence_invalid"):
            obs(parse_success=False)

    def test_report_requires_complete_current_engine_baseline(self):
        bad = baselines()
        bad.pop("clarity")
        with self.assertRaisesRegex(sm.StOmrShadowError, "baseline_binding_invalid"):
            sm.build_shadow_report(
                [obs()],
                baseline_report_sha256_by_engine=bad,
                baseline_method_version="sm-poly-04-v1",
            )

    def test_report_category_evidence_uses_exact_rationals(self):
        report = sm.build_shadow_report(
            [obs()],
            baseline_report_sha256_by_engine=baselines(),
            baseline_method_version="sm-poly-04-v1",
        )
        pitch = next(item for item in report["categoryEvidence"] if item["category"] == "pitch")
        self.assertEqual(pitch["metric"]["accuracy"], {"numerator": 9, "denominator": 10})
        self.assertTrue(report["currentEngineBaseline"]["completeCurrentEngineSet"])
        self.assertEqual(set(report["currentEngineBaseline"]["reportSha256ByEngine"]), set(sm.CURRENT_BASELINE_ENGINES))

    def test_json_object_key_order_does_not_change_validity(self):
        item = obs()
        item["semanticMetrics"] = dict(reversed(list(item["semanticMetrics"].items())))
        body = copy.deepcopy(item)
        body.pop("observationSha256")
        item["observationSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        sm.validate_shadow_observation(item)

        report = sm.build_shadow_report(
            [obs()],
            baseline_report_sha256_by_engine=baselines(),
            baseline_method_version="sm-poly-04-v1",
        )
        report["currentEngineBaseline"]["reportSha256ByEngine"] = dict(
            reversed(list(report["currentEngineBaseline"]["reportSha256ByEngine"].items()))
        )
        body = copy.deepcopy(report)
        body.pop("reportSha256")
        report["reportSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        sm.validate_shadow_report(report)

    def test_authority_tamper_fails_even_when_rehashed(self):
        item = obs()
        item["boundaries"]["winnerSelection"] = True
        body = copy.deepcopy(item)
        body.pop("observationSha256")
        item["observationSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(sm.StOmrShadowError, "authority_boundary_invalid"):
            sm.validate_shadow_observation(item)

    def test_report_recompute_detects_forged_metric(self):
        item = obs()
        report = sm.build_shadow_report(
            [item],
            baseline_report_sha256_by_engine=baselines(),
            baseline_method_version="sm-poly-04-v1",
        )
        forged = copy.deepcopy(report)
        forged["categoryEvidence"][2]["metric"]["correct"] = 8
        forged["categoryEvidence"][2]["metric"]["accuracy"] = {"numerator": 4, "denominator": 5}
        identity = copy.deepcopy(forged)
        identity.pop("reportId")
        identity.pop("reportSha256")
        forged["reportId"] = "st_omr_shadow_report_" + hashlib.sha256(sm._canonical_json(identity)).hexdigest()[:24]
        body = copy.deepcopy(forged)
        body.pop("reportSha256")
        forged["reportSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        sm.validate_shadow_report(forged)
        with self.assertRaisesRegex(sm.StOmrShadowError, "shadow_report_recompute_mismatch"):
            sm.validate_shadow_report_against_observations(forged, [item])

    def test_duplicate_run_evidence_is_rejected(self):
        one = obs()
        two = obs(candidate_artifact_sha256="f" * 64)
        with self.assertRaisesRegex(sm.StOmrShadowError, "duplicate_shadow_run_evidence"):
            sm.build_shadow_report(
                [one, two],
                baseline_report_sha256_by_engine=baselines(),
                baseline_method_version="sm-poly-04-v1",
            )

    def test_model_or_run_binding_changes_identity(self):
        one = obs()
        two = obs(run_id="run-002")
        three = obs(model_artifact_sha256="f" * 64)
        self.assertNotEqual(one["observationId"], two["observationId"])
        self.assertNotEqual(one["observationSha256"], two["observationSha256"])
        self.assertNotEqual(one["observationId"], three["observationId"])


if __name__ == "__main__":
    unittest.main()
