import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble import convergence_evidence_v2 as sm

SCHEMA = json.loads(
    (REPOSITORY_ROOT / "contracts" / "convergence-evidence-vector-v2.schema.json").read_text(
        encoding="utf-8"
    )
)
ARCHITECTURE = json.loads(
    (REPOSITORY_ROOT / "contracts" / "architecture-current-state-v1.json").read_text(
        encoding="utf-8"
    )
)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def slot(schema_version: str, *digests: str):
    return sm.evidence_slot(
        schema_version=schema_version,
        artifact_sha256s=list(digests or (SHA_A,)),
    )


def unavailable():
    return sm.unavailable_evidence_slot()


def vector(**overrides):
    args = dict(
        stage7_result_sha256=SHA_C,
        semantic_metrics=slot(
            "scoremosaic-polyphonic-engine-semantic-report-v1", SHA_A
        ),
        visual_evidence=slot(
            "scoremosaic-polyphonic-visual-evidence-sidecar-v1", SHA_A, SHA_B, SHA_C
        ),
        source_quality=slot(
            "scoremosaic-polyphonic-source-quality-profile-v1", SHA_D
        ),
        polyphony_complexity=slot(
            "scoremosaic-polyphonic-complexity-profile-v1", SHA_E
        ),
        reliability_calibration=slot(
            "scoremosaic-engine-reliability-report-v1", SHA_B
        ),
        st_omr_shadow=slot("scoremosaic-st-omr-shadow-report-v1", SHA_F),
    )
    args.update(overrides)
    return sm.build_convergence_evidence_vector(**args)


class ConvergenceEvidenceV2Tests(unittest.TestCase):
    def test_schema_is_closed_and_has_nonempty_defs(self):
        self.assertFalse(SCHEMA["additionalProperties"])
        self.assertTrue(SCHEMA["$defs"])
        self.assertEqual(
            SCHEMA["properties"]["stage7Convergence"]["properties"]["bindingMethodVersion"]["const"],
            sm.STAGE7_BINDING_METHOD_VERSION,
        )
        slot_binding = SCHEMA["$defs"]["slotBase"]["properties"]["bindingMethodVersion"]["anyOf"][0]["const"]
        self.assertEqual(slot_binding, sm.EVIDENCE_BINDING_METHOD_VERSION)
        boundaries = SCHEMA["$defs"]["boundaries"]["properties"]
        self.assertFalse(boundaries["upstreamEvidenceReinterpreted"]["const"])
        self.assertFalse(boundaries["crossArtifactIdentityMatchClaimed"]["const"])
        self.assertFalse(boundaries["stage7EvidenceMutation"]["const"])
        self.assertFalse(boundaries["stage7QuorumContribution"]["const"])
        self.assertFalse(boundaries["winnerSelection"]["const"])
        self.assertFalse(boundaries["stOmrProductionPromotion"]["const"])

    def test_current_architecture_authority_is_unchanged(self):
        current = ARCHITECTURE["currentOmr"]
        self.assertEqual(
            current["productionCandidateEngines"], ["audiveris", "homr", "clarity"]
        )
        self.assertEqual(current["stage7MinimumCanonicalCandidates"], 2)
        self.assertFalse(current["stOmrIntegratedIntoGateway"])
        self.assertFalse(current["automaticWinnerAuthority"])
        self.assertFalse(ARCHITECTURE["teacherReview"]["productionWriteActivated"])
        self.assertEqual(sm.PRODUCTION_ENGINES, ("audiveris", "homr", "clarity"))
        self.assertEqual(sm.SHADOW_ENGINE, "st-omr")

    def test_vector_is_deterministic_and_sha_pinned(self):
        one = vector()
        two = vector()
        self.assertEqual(one, two)
        body = copy.deepcopy(one)
        body.pop("vectorSha256")
        self.assertEqual(
            one["vectorSha256"], hashlib.sha256(sm._canonical_json(body)).hexdigest()
        )
        self.assertIsNone(one["derivedState"]["aggregateConfidenceScore"])
        self.assertIsNone(one["derivedState"]["engineRanking"])
        self.assertIsNone(one["derivedState"]["winner"])

    def test_binding_methods_are_frozen(self):
        item = vector()
        self.assertEqual(
            item["stage7Convergence"]["bindingMethodVersion"],
            "STAGE7_RESULT_SHA256_REFERENCE_V1",
        )
        for family in sm.EVIDENCE_FAMILIES:
            self.assertEqual(
                item["evidence"][family]["bindingMethodVersion"],
                "SHA256_ARTIFACT_SET_REFERENCE_V1",
            )
        bad = copy.deepcopy(item)
        bad["evidence"]["semanticMetrics"]["bindingMethodVersion"] = "UNVERIFIED_CUSTOM_METHOD"
        body = copy.deepcopy(bad)
        body.pop("vectorSha256")
        bad["vectorSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(sm.ConvergenceEvidenceV2Error, "evidence_slot_invalid"):
            sm.validate_convergence_evidence_vector(bad)

    def test_context_does_not_claim_unverified_fixture_or_cross_artifact_identity(self):
        item = vector()
        self.assertEqual(
            item["evidenceContext"]["methodVersion"],
            "OPAQUE_UPSTREAM_ARTIFACT_SET_CONTEXT_V1",
        )
        self.assertFalse(item["evidenceContext"]["directFixtureBindingClaimed"])
        self.assertFalse(item["evidenceContext"]["crossArtifactIdentityMatchClaimed"])
        self.assertFalse(item["boundaries"]["crossArtifactIdentityMatchClaimed"])
        self.assertNotIn("fixtureId", item)
        self.assertNotIn("teacherGoldReferenceSha256", item)
        self.assertNotIn("sourceDocumentSha256", item)

    def test_upstream_artifacts_are_bound_as_opaque_family_sets(self):
        item = vector()
        semantic = item["evidence"]["semanticMetrics"]
        reliability = item["evidence"]["reliabilityCalibration"]
        visual = item["evidence"]["visualEvidence"]
        slot_keys = {
            "available",
            "schemaVersion",
            "bindingMethodVersion",
            "artifactSha256Set",
            "artifactSetSha256",
        }
        self.assertEqual(set(semantic), slot_keys)
        self.assertEqual(set(reliability), slot_keys)
        self.assertEqual(set(visual), slot_keys)
        self.assertEqual(visual["artifactSha256Set"], [SHA_A, SHA_B, SHA_C])
        self.assertNotIn("audiveris", visual)
        self.assertFalse(item["boundaries"]["upstreamEvidenceReinterpreted"])

    def test_evidence_family_availability_is_explicit(self):
        item = vector(visual_evidence=unavailable())
        self.assertFalse(item["evidence"]["visualEvidence"]["available"])
        self.assertEqual(item["evidence"]["visualEvidence"]["artifactSha256Set"], [])
        self.assertTrue(item["evidence"]["stOmrShadow"]["available"])
        self.assertFalse(item["boundaries"]["stOmrProductionPromotion"])
        self.assertFalse(item["boundaries"]["stage7QuorumContribution"])
        self.assertEqual(item["derivedState"]["availableEvidenceFamilyCount"], 5)

    def test_unavailable_slot_rejects_hidden_evidence(self):
        item = vector(visual_evidence=unavailable())
        bad = copy.deepcopy(item)
        visual = bad["evidence"]["visualEvidence"]
        visual["artifactSha256Set"] = [SHA_A]
        visual["artifactSetSha256"] = hashlib.sha256(
            sm._canonical_json([SHA_A])
        ).hexdigest()
        body = copy.deepcopy(bad)
        body.pop("vectorSha256")
        bad["vectorSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(
            sm.ConvergenceEvidenceV2Error, "unavailable_evidence_contains_value"
        ):
            sm.validate_convergence_evidence_vector(bad)

    def test_wrong_family_schema_fails_closed(self):
        wrong = slot("scoremosaic-engine-reliability-report-v1", SHA_A)
        with self.assertRaisesRegex(
            sm.ConvergenceEvidenceV2Error, "evidence_family_schema_invalid"
        ):
            vector(semantic_metrics=wrong)

    def test_artifact_sets_are_sorted_unique_and_content_bound(self):
        one = sm.evidence_slot(
            schema_version="scoremosaic-polyphonic-visual-evidence-sidecar-v1",
            artifact_sha256s=[SHA_B, SHA_A],
        )
        self.assertEqual(one["artifactSha256Set"], [SHA_A, SHA_B])
        with self.assertRaisesRegex(sm.ConvergenceEvidenceV2Error, "evidence_slot_invalid"):
            sm.evidence_slot(
                schema_version="scoremosaic-polyphonic-visual-evidence-sidecar-v1",
                artifact_sha256s=[SHA_A, SHA_A],
            )

    def test_authority_tamper_fails_even_if_rehashed(self):
        item = vector()
        bad = copy.deepcopy(item)
        bad["boundaries"]["winnerSelection"] = True
        body = copy.deepcopy(bad)
        body.pop("vectorSha256")
        bad["vectorSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(sm.ConvergenceEvidenceV2Error, "authority_boundary_invalid"):
            sm.validate_convergence_evidence_vector(bad)

    def test_context_claim_tamper_fails_even_if_rehashed(self):
        item = vector()
        bad = copy.deepcopy(item)
        bad["evidenceContext"]["crossArtifactIdentityMatchClaimed"] = True
        body = copy.deepcopy(bad)
        body.pop("vectorSha256")
        bad["vectorSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(sm.ConvergenceEvidenceV2Error, "evidence_context_invalid"):
            sm.validate_convergence_evidence_vector(bad)

    def test_shadow_evidence_never_changes_production_engine_set(self):
        item = vector()
        self.assertEqual(
            item["derivedState"]["productionCandidateEngines"],
            ["audiveris", "homr", "clarity"],
        )
        self.assertEqual(item["derivedState"]["shadowEngine"], "st-omr")
        self.assertNotIn("st-omr", item["derivedState"]["productionCandidateEngines"])

    def test_stage7_reference_or_evidence_change_changes_vector_identity(self):
        one = vector()
        two = vector(stage7_result_sha256=SHA_D)
        shadow = slot("scoremosaic-st-omr-shadow-report-v1", SHA_E)
        three = vector(st_omr_shadow=shadow)
        self.assertNotEqual(one["vectorId"], two["vectorId"])
        self.assertNotEqual(one["vectorSha256"], two["vectorSha256"])
        self.assertNotEqual(one["vectorId"], three["vectorId"])

    def test_available_count_is_recomputed(self):
        item = vector()
        self.assertEqual(item["derivedState"]["availableEvidenceFamilyCount"], 6)
        bad = copy.deepcopy(item)
        bad["derivedState"]["availableEvidenceFamilyCount"] = 5
        identity = copy.deepcopy(bad)
        identity.pop("vectorId")
        identity.pop("vectorSha256")
        bad["vectorId"] = "convergence_evidence_v2_" + hashlib.sha256(
            sm._canonical_json(identity)
        ).hexdigest()[:24]
        body = copy.deepcopy(bad)
        body.pop("vectorSha256")
        bad["vectorSha256"] = hashlib.sha256(sm._canonical_json(body)).hexdigest()
        with self.assertRaisesRegex(
            sm.ConvergenceEvidenceV2Error, "convergence_evidence_derived_state_invalid"
        ):
            sm.validate_convergence_evidence_vector(bad)

    def test_stage7_production_source_does_not_consume_v2(self):
        source = (
            SERVICE_ROOT / "src" / "scoremosaic_ensemble" / "convergence.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("convergence_evidence_v2", source)
        self.assertNotIn("ConvergenceEvidenceVector", source)
        self.assertIn('"winnerSelection": False', source)
        self.assertIn('"automaticMerge": False', source)
        self.assertIn('"automaticCorrection": False', source)


if __name__ == "__main__":
    unittest.main()
