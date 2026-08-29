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


def slot(schema_version: str, digest: str = SHA_A):
    return sm.evidence_slot(
        schema_version=schema_version,
        binding_method_version="sha256-reference-v1",
        artifact_sha256s=[digest],
    )


def unavailable():
    return sm.unavailable_evidence_slot()


def engine_slots(schema_version: str):
    return {
        "audiveris": slot(schema_version, SHA_A),
        "homr": slot(schema_version, SHA_B),
        "clarity": slot(schema_version, SHA_C),
    }


def vector(**overrides):
    args = dict(
        fixture_id="poly_fixture_fixture001",
        teacher_gold_reference_sha256=SHA_A,
        source_document_sha256=SHA_B,
        stage7_result_sha256=SHA_C,
        stage7_binding_method_version="stage7-result-reference-v1",
        semantic_metrics_by_engine=engine_slots(
            "scoremosaic-polyphonic-engine-semantic-report-v1"
        ),
        visual_evidence_by_engine={engine: unavailable() for engine in sm.PRODUCTION_ENGINES},
        source_quality=slot(
            "scoremosaic-polyphonic-source-quality-profile-v1", SHA_D
        ),
        polyphony_complexity=slot(
            "scoremosaic-polyphonic-complexity-profile-v1", SHA_E
        ),
        reliability_calibration_by_engine=engine_slots(
            "scoremosaic-engine-reliability-report-v1"
        ),
        st_omr_shadow=slot("scoremosaic-st-omr-shadow-report-v1", SHA_F),
    )
    args.update(overrides)
    return sm.build_convergence_evidence_vector(**args)


class ConvergenceEvidenceV2Tests(unittest.TestCase):
    def test_schema_is_closed_and_has_nonempty_defs(self):
        self.assertFalse(SCHEMA["additionalProperties"])
        self.assertTrue(SCHEMA["$defs"])
        boundaries = SCHEMA["$defs"]["boundaries"]["properties"]
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

    def test_evidence_family_availability_is_explicit(self):
        item = vector()
        self.assertFalse(item["evidence"]["visualEvidence"]["audiveris"]["available"])
        self.assertEqual(
            item["evidence"]["visualEvidence"]["audiveris"]["artifactSha256Set"], []
        )
        self.assertTrue(item["evidence"]["stOmrShadow"]["available"])
        self.assertFalse(item["boundaries"]["stOmrProductionPromotion"])
        self.assertFalse(item["boundaries"]["stage7QuorumContribution"])

    def test_unavailable_slot_rejects_hidden_evidence(self):
        item = vector()
        bad = copy.deepcopy(item)
        visual = bad["evidence"]["visualEvidence"]["audiveris"]
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
        semantic = engine_slots("scoremosaic-engine-reliability-report-v1")
        with self.assertRaisesRegex(
            sm.ConvergenceEvidenceV2Error, "evidence_family_schema_invalid"
        ):
            vector(semantic_metrics_by_engine=semantic)

    def test_artifact_sets_are_sorted_unique_and_content_bound(self):
        one = sm.evidence_slot(
            schema_version="scoremosaic-polyphonic-visual-evidence-sidecar-v1",
            binding_method_version="sha256-reference-v1",
            artifact_sha256s=[SHA_B, SHA_A],
        )
        self.assertEqual(one["artifactSha256Set"], [SHA_A, SHA_B])
        with self.assertRaisesRegex(sm.ConvergenceEvidenceV2Error, "evidence_slot_invalid"):
            sm.evidence_slot(
                schema_version="scoremosaic-polyphonic-visual-evidence-sidecar-v1",
                binding_method_version="sha256-reference-v1",
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
        bad = copy.deepcopy(item)
        bad["derivedState"]["availableEvidenceFamilyCount"] += 1
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
