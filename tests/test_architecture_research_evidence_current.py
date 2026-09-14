from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads(
    (ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8")
)
ARCHITECTURE = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
STAGE_5_7 = (ROOT / "docs" / "architecture-stage5-7-current.md").read_text(encoding="utf-8")
RESEARCH = (ROOT / "docs" / "architecture-research-evidence-current.md").read_text(encoding="utf-8")
ROADMAP = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
CONSISTENCY = (ROOT / "docs" / "architecture-consistency-report.md").read_text(encoding="utf-8")


class ArchitectureResearchEvidenceCurrentTests(unittest.TestCase):
    def test_repository_state_is_pinned_to_last_verified_main_before_sync(self) -> None:
        state = STATE["repositoryStateAsOf"]
        self.assertEqual(
            "dfd8b8607607383fd1e250ce704e97af84a5101b",
            state["mainCommit"],
        )
        self.assertEqual("2026-08-30", state["date"])
        self.assertEqual(
            "docs/architecture-research-evidence-current.md",
            state["researchEvidenceAddendum"],
        )

    def test_stage7_production_authority_is_unchanged(self) -> None:
        omr = STATE["currentOmr"]
        self.assertEqual(["audiveris", "homr", "clarity"], omr["productionCandidateEngines"])
        self.assertEqual(2, omr["stage7MinimumCanonicalCandidates"])
        self.assertIs(omr["stOmrIntegratedIntoGateway"], False)
        self.assertIs(STATE["polyphonicResearchEvidence"]["stage7QuorumChanged"], False)
        self.assertIs(
            STATE["polyphonicResearchEvidence"]["productionDecisionAuthorityGranted"],
            False,
        )

    def test_research_chain_is_exact_and_does_not_invent_missing_package_numbers(self) -> None:
        research = STATE["polyphonicResearchEvidence"]
        self.assertEqual(
            [
                "SM-POLY-02",
                "SM-POLY-03",
                "SM-POLY-04",
                "SM-POLY-05",
                "SM-POLY-06",
                "SM-POLY-07",
                "SM-POLY-08",
                "SM-POLY-09",
                "SM-POLY-11",
            ],
            research["implementedPackages"],
        )
        self.assertNotIn("SM-POLY-10", research["implementedPackages"])
        self.assertNotIn("SM-POLY-12", research["implementedPackages"])
        self.assertEqual("SM-POLY-13", research["nextPlannedPackage"])
        self.assertEqual(
            "TEACHER_REVISION_COMMAND_COUNT_V1",
            research["nextPlannedMethod"],
        )

    def test_evidence_readiness_is_not_overclaimed(self) -> None:
        research = STATE["polyphonicResearchEvidence"]
        self.assertIs(research["teacherGoldHarnessReady"], True)
        self.assertIs(research["teacherGoldRegistrySufficientlyPopulated"], False)
        self.assertIs(research["minimumResearchBenchmarkReady"], False)
        self.assertIs(research["stOmrShadowEvidenceContractReady"], True)
        self.assertIs(STATE["currentOmr"]["realWorldShadowBenchmarkComplete"], False)
        self.assertIs(research["directCrossArtifactJoinValidated"], False)
        self.assertIs(research["selectivePredictionAuthorized"], False)
        self.assertIs(research["automaticMergeOrCorrectionEnabled"], False)

    def test_real_score_intake_and_preview_integrations_remain_non_authoritative(self) -> None:
        intake = STATE["approvedWorkstreams"]["realScoreIntakeCoreIntegration"]
        self.assertIs(intake["canonicalProjectionReady"], True)
        self.assertIs(intake["chordAwareSemanticTargetsReady"], True)
        self.assertIs(intake["liveUploadActivated"], False)
        self.assertIs(intake["productionPersistenceActivated"], False)
        self.assertIs(intake["automaticCorrectionActivated"], False)
        self.assertIs(intake["approvalPublicationAuthorityGranted"], False)

        orchestration = STATE["approvedWorkstreams"]["stOrchestrationPreview"]
        self.assertIs(orchestration["h7CLocalPreviewReady"], True)
        self.assertIs(orchestration["h7DAuthenticatedStagingReady"], True)
        self.assertIs(orchestration["teacherReviewEvidenceOnly"], True)
        self.assertIs(orchestration["browserDirectEngineCallAllowed"], False)
        self.assertIs(orchestration["applyActionAvailable"], False)
        self.assertIs(orchestration["productionInferenceActivated"], False)
        self.assertIs(orchestration["h7EAuthorized"], False)

    def test_score_discovery_remains_handoff_only(self) -> None:
        discovery = STATE["approvedWorkstreams"]["scoreDiscoveryConsumer"]
        self.assertEqual("discovery-handoff-only", discovery["eligibleServerHandoffAuthority"])
        self.assertIs(discovery["safeIntakeStillRequired"], True)
        self.assertIs(discovery["liveGatewayNetworkingActivated"], False)
        self.assertIs(discovery["productionImportActivated"], False)

    def test_next_development_order_is_explicit(self) -> None:
        next_dev = STATE["nextDevelopment"]
        self.assertEqual(
            [
                "SM-POLY-13_TEACHER_REVIEW_WORKLOAD_INSTRUMENTATION",
                "POPULATE_AND_QUALIFY_REAL_TEACHER_GOLD_EVIDENCE",
                "VERSIONED_DIRECT_CROSS_ARTIFACT_JOIN",
                "SELECTIVE_PREDICTION_ABSTENTION_RESEARCH",
                "VERSIONED_ST_OMR_PROMOTION_DECISION_GATE",
            ],
            next_dev["priorityOrder"],
        )
        self.assertIs(next_dev["crossArtifactJoinPackageNumberAssigned"], False)
        self.assertIs(next_dev["selectivePredictionPackageNumberAssigned"], False)
        self.assertIs(next_dev["h7ESeparateHumanGate"], True)

    def test_current_documents_reference_research_addendum_and_next_gate(self) -> None:
        marker = "docs/architecture-research-evidence-current.md"
        for text in (ARCHITECTURE, STAGE_5_7, ROADMAP, CONSISTENCY):
            self.assertIn(marker, text)

        for text in (ARCHITECTURE, STAGE_5_7, RESEARCH, ROADMAP):
            self.assertIn("SM-POLY-13", text)
            self.assertIn("TEACHER_REVISION_COMMAND_COUNT_V1", text)

        self.assertIn("SM-POLY-11", RESEARCH)
        self.assertIn("directCrossArtifactJoinValidated=false", RESEARCH)
        self.assertIn("selectivePredictionAuthorized=false", RESEARCH)


if __name__ == "__main__":
    unittest.main()
