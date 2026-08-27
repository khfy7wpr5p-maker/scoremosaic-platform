from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPECIFIC = json.loads(
    (ROOT / "contracts" / "st-orchestration-integration-v1.json").read_text(encoding="utf-8")
)
DOWNSTREAM = json.loads(
    (ROOT / "contracts" / "downstream-music-application-integration-v1.json").read_text(encoding="utf-8")
)
CURRENT = json.loads(
    (ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8")
)
DOC = (ROOT / "docs" / "st-orchestration-integration-boundary.md").read_text(encoding="utf-8")
DOWNSTREAM_DOC = (
    ROOT / "docs" / "downstream-music-application-integration-boundary.md"
).read_text(encoding="utf-8")


EXPECTED_MAIN = "6c7f74fdbf13dd3acc2e0daa93cab7037d6a0a90"
EXPECTED_CONTRACT_BLOB = "2583f54ef6b0a9f0985edd91c82fadf3681e88f4"
EXPECTED_MODEL = "15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14"
EXPECTED_H4_RESULT = "462f492ace58ecf0c4d1125966057c869177cad99367f1364d89c17710081225"


class StOrchestrationIntegrationArchitectureTests(unittest.TestCase):
    def test_exact_counterpart_identity_is_pinned(self) -> None:
        target = SPECIFIC["target"]
        self.assertEqual("khfy7wpr5p-maker/ST-Orchestration", target["repository"])
        self.assertEqual(EXPECTED_MAIN, target["mainCommit"])
        self.assertEqual("contracts/H7_SCOREMOSAIC_INTEGRATION_V0.json", target["contractPath"])
        self.assertEqual(EXPECTED_CONTRACT_BLOB, target["contractGitBlobSha"])
        self.assertEqual("st-orchestration.h7-scoremosaic-integration/v0", target["contractSchemaVersion"])
        self.assertEqual("o5c-ossq-anonymous-context-v0", target["modelId"])
        self.assertEqual(EXPECTED_MODEL, target["modelFingerprint"])
        self.assertEqual(EXPECTED_H4_RESULT, target["h4ResultFingerprint"])
        self.assertEqual(0.55, target["abstentionThreshold"])
        self.assertEqual("bounded-research-evaluation-only", target["promotionScope"])

    def test_capability_is_bounded_and_broader_orchestration_fails_closed(self) -> None:
        capability = SPECIFIC["capability"]
        self.assertEqual(["string-seat-ranking-v0"], capability["supported"])
        self.assertIs(capability["unsupportedRequestsFailClosed"], True)
        self.assertIs(capability["currentModelIsGeneralOrchestrator"], False)
        self.assertIn("piano-to-orchestra", capability["unsupported"])
        self.assertIn("full-score-orchestration", capability["unsupported"])
        self.assertIn("full-symphonic-orchestration", capability["unsupported"])
        self.assertIn("this is **not** a general piano-to-orchestra", DOC.lower())

    def test_source_lineage_matches_scoremosaic_downstream_truth_boundary(self) -> None:
        source = SPECIFIC["sourcePolicy"]
        self.assertIs(source["rawOmrCandidateAllowed"], False)
        self.assertIs(source["rawEngineOutputAllowed"], False)
        self.assertIs(source["browserEditedAdHocXmlAllowed"], False)
        self.assertIs(source["staleRevisionAllowed"], False)
        self.assertIs(source["validatedTeacherRevisionPreviewAllowed"], True)
        self.assertIs(source["productionRequestRequiresApprovedTeacherRevision"], True)
        self.assertIs(source["correctedMusicXmlSha256Required"], True)

        self.assertEqual(
            [
                "integration_request_id",
                "document_id",
                "canonical_score_id",
                "teacher_revision_id",
                "corrected_musicxml_sha256",
                "source_state",
                "capability",
            ],
            SPECIFIC["requestLineage"]["requiredFields"],
        )
        self.assertEqual(["validated-preview", "approved"], SPECIFIC["requestLineage"]["sourceStateValues"])

    def test_result_remains_non_authoritative_and_deterministically_validated(self) -> None:
        result = SPECIFIC["resultBoundary"]
        self.assertIs(result["deterministicValidationRequired"], True)
        self.assertIs(result["downstreamOutputIsAuthoritativeMusicalTruth"], False)
        self.assertIs(result["sourceMutationAllowed"], False)
        self.assertEqual(["proposal", "abstain", "unsupported"], result["statusValues"])

        for key, value in SPECIFIC["authority"].items():
            with self.subTest(authority=key):
                self.assertIs(value, False)

    def test_only_disconnected_harness_is_ready(self) -> None:
        locks = SPECIFIC["activationLocks"]
        self.assertIs(locks["disconnectedCompatibilityHarnessReady"], True)
        for key, value in locks.items():
            if key == "disconnectedCompatibilityHarnessReady":
                continue
            with self.subTest(lock=key):
                self.assertIs(value, False)
        self.assertEqual(
            "H7-C_NON_AUTHORITATIVE_LOCAL_PREVIEW_ADAPTER_HUMAN_DECISION",
            SPECIFIC["nextGate"],
        )

    def test_generic_downstream_contract_registers_st_orchestration_without_activation(self) -> None:
        self.assertEqual("ARCHITECTURE_ONLY_FUTURE_DOWNSTREAM_INTEGRATION", DOWNSTREAM["status"])
        engine = DOWNSTREAM["stOrchestration"]
        self.assertEqual("ST-Orchestration", engine["integrationName"])
        self.assertEqual(EXPECTED_MAIN, engine["pinnedCompatibilityCommit"])
        self.assertEqual(["string-seat-ranking-v0"], engine["supportedCapabilities"])
        self.assertIs(engine["generalPianoToOrchestraSupported"], False)
        self.assertIs(engine["fullScoreOrchestrationSupported"], False)
        self.assertIs(engine["mayRewriteSourceMusic"], False)
        self.assertIs(engine["mayCreateTeacherRevision"], False)
        self.assertIs(engine["mayApprove"], False)
        self.assertIs(engine["mayPublish"], False)
        self.assertIs(engine["liveIntegrationActivated"], False)
        for key, value in DOWNSTREAM["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)

    def test_existing_scoremosaic_production_and_browser_locks_remain_closed(self) -> None:
        self.assertIs(CURRENT["production"]["productionReady"], False)
        self.assertIs(CURRENT["production"]["productionNetworkActivated"], False)
        self.assertIs(CURRENT["production"]["productionCredentialsProvisioned"], False)
        self.assertIs(CURRENT["teacherReview"]["liveTeacherReviewApiActivated"], False)
        self.assertIs(CURRENT["teacherReview"]["productionWriteActivated"], False)
        self.assertIs(CURRENT["browser"]["networkAllowed"], False)
        self.assertIs(CURRENT["browser"]["serverWriteAllowed"], False)
        self.assertIs(CURRENT["authorityInvariants"]["downstreamMusicApplicationIsNotScoreAuthority"], True)
        self.assertIs(CURRENT["authorityInvariants"]["productionActivationRequiresSeparateGate"], True)

    def test_docs_state_disconnected_only_and_direct_browser_call_is_forbidden(self) -> None:
        self.assertIn("DISCONNECTED COMPATIBILITY READY / LIVE INTEGRATION DISABLED", DOC)
        self.assertIn("The browser never calls ST-Orchestration directly", DOC)
        self.assertIn("H7-C", DOC)
        self.assertIn("ST-Orchestration — H7-B disconnected compatibility", DOWNSTREAM_DOC)
        self.assertIn("future transport — disabled", DOWNSTREAM_DOC)


if __name__ == "__main__":
    unittest.main()
