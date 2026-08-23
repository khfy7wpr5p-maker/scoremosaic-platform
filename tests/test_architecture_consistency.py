from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))

CURRENT_DOCS = {
    "README.md": ROOT / "README.md",
    "architecture.md": ROOT / "docs" / "architecture.md",
    "stage5-7": ROOT / "docs" / "architecture-stage5-7-current.md",
    "stage8": ROOT / "docs" / "architecture-stage8-current.md",
    "stage9-11": ROOT / "docs" / "architecture-stage9-11-current.md",
    "ui-phase1": ROOT / "docs" / "ui-architecture-phase1.md",
    "live-ui-api-security": ROOT / "docs" / "live-ui-api-security-architecture-v1.md",
    "downstream-music-apps": ROOT / "docs" / "downstream-music-application-integration-boundary.md",
    "st-omr": ROOT / "docs" / "st-omr-architecture-contract-v1.md",
    "teacher-review": ROOT / "docs" / "teacher-review-score-editor-architecture-contract.md",
    "roadmap": ROOT / "docs" / "roadmap.md",
    "security": ROOT / "docs" / "security-boundaries.md",
}

TEXT = {name: path.read_text(encoding="utf-8") for name, path in CURRENT_DOCS.items()}


class ArchitectureConsistencyTests(unittest.TestCase):
    def test_current_state_contract_identity(self) -> None:
        self.assertEqual("scoremosaic-architecture-current-state-v1", CONTRACT["version"])
        self.assertEqual("11-F", CONTRACT["asOfStage"])
        self.assertIs(CONTRACT["sourceOfTruth"], True)

    def test_stage_statuses_are_closed_and_current_through_11(self) -> None:
        self.assertEqual(
            {
                "5": "CONTROLLED_STAGING_EXECUTION_COMPLETE",
                "6": "AUTHENTICATED_CANDIDATE_INGESTION_PERSISTENCE_COMPLETE",
                "7": "CANONICAL_ENSEMBLE_CONVERGENCE_COMPLETE",
                "8": "TEACHER_REVIEW_PUBLICATION_PREPARATION_COMPLETE_EXTERNAL_EFFECT_LOCKED",
                "9": "REPOSITORY_PRODUCTION_FOUNDATION_COMPLETE_EXTERNAL_PROVISIONING_DEFERRED",
                "10": "REPOSITORY_UI_EXPERIENCE_COMPLETE",
                "11": "REPOSITORY_TYPED_UI_APPLICATION_INTEGRATION_COMPLETE_LIVE_INTEGRATION_LOCKED",
            },
            CONTRACT["stageStatus"],
        )

    def test_approved_post_stage11_workstreams_are_unnumbered_and_non_live(self) -> None:
        ui = CONTRACT["approvedWorkstreams"]["uiArchitecturePhase1"]
        self.assertIs(ui["stageNumberAssigned"], False)
        self.assertEqual(
            "APPROVED_REPOSITORY_UI_ARCHITECTURE_BASELINE_LOW_FIDELITY_STARTED",
            ui["status"],
        )
        self.assertIs(ui["figmaLowFidelityStarted"], True)
        self.assertIs(ui["figmaHighFidelityStarted"], False)
        self.assertIs(ui["liveActivationGranted"], False)

        security = CONTRACT["approvedWorkstreams"]["liveUiApiSecurityDesign"]
        self.assertIs(security["stageNumberAssigned"], False)
        self.assertEqual(
            "APPROVED_REPOSITORY_LIVE_UI_API_SECURITY_ARCHITECTURE_BASELINE",
            security["status"],
        )
        self.assertIs(security["repositorySecurityArchitectureReady"], True)
        for key in ("runtimeActivated", "liveNetworkActivated", "authRuntimeActivated", "serverWriteActivated"):
            self.assertIs(security[key], False, key)

        downstream = CONTRACT["approvedWorkstreams"]["downstreamMusicApplicationIntegration"]
        self.assertIs(downstream["stageNumberAssigned"], False)
        self.assertEqual("ARCHITECTURE_ONLY_FUTURE_DOWNSTREAM_INTEGRATION", downstream["status"])
        self.assertIs(downstream["guitarTabLiveIntegrationActivated"], False)

    def test_current_stage7_engine_set_and_quorum_are_not_silently_changed(self) -> None:
        omr = CONTRACT["currentOmr"]
        self.assertEqual(["audiveris", "homr", "clarity"], omr["productionCandidateEngines"])
        self.assertEqual(2, omr["stage7MinimumCanonicalCandidates"])
        self.assertIs(omr["stOmrIntegratedIntoGateway"], False)
        self.assertIs(omr["engineOutputAuthoritativeMusicalTruth"], False)
        self.assertIs(omr["automaticWinnerAuthority"], False)

    def test_st_omr_only_migration_cannot_happen_by_implication(self) -> None:
        migration = CONTRACT["stOmrMigration"]
        self.assertEqual("ARCHITECTURE_ONLY_ISOLATED_TRACK", migration["currentState"])
        for key in (
            "requiresVersionedStage7Migration",
            "requiresShadowBenchmarkEvidence",
            "requiresTeacherGoldEvaluation",
            "requiresCategoryStratifiedNoRegressionEvidence",
            "requiresCalibratedAbstentionAndDeterministicValidation",
        ):
            self.assertIs(migration[key], True, key)
        self.assertIs(migration["mayRemoveExistingProductionEnginesNow"], False)

    def test_production_activation_locks_remain_false(self) -> None:
        production = CONTRACT["production"]
        for key in (
            "providerResourcesCreated",
            "productionCredentialsProvisioned",
            "productionNetworkActivated",
            "productionDatabaseActivated",
            "productionObjectStorageActivated",
            "productionIdentityActivated",
            "productionSecretsActivated",
            "publicApiActivated",
            "publicTrafficActivated",
        ):
            self.assertIs(production[key], False, key)

    def test_teacher_review_live_activation_locks_remain_false(self) -> None:
        review = CONTRACT["teacherReview"]
        self.assertIs(review["repositoryRevisionApprovalPublicationPreparationComplete"], True)
        self.assertIs(review["disconnectedProductUiComplete"], True)
        self.assertIs(review["typedLocalUiApplicationIntegrationComplete"], True)
        for key in (
            "liveTeacherReviewApiActivated",
            "productionWriteActivated",
            "productionApprovalPersistenceActivated",
            "publicationExecutionActivated",
        ):
            self.assertIs(review[key], False, key)

    def test_browser_remains_disconnected_and_non_authoritative(self) -> None:
        browser = CONTRACT["browser"]
        self.assertIs(browser["localFixtureUiAvailable"], True)
        self.assertIs(browser["typedLocalApplicationAvailable"], True)
        for key in (
            "networkAllowed",
            "browserPersistenceAllowed",
            "productionArtifactReadsAllowed",
            "serverWriteAllowed",
            "playbackAllowed",
        ):
            self.assertIs(browser[key], False, key)

    def test_downstream_music_applications_cannot_become_upstream_authority(self) -> None:
        downstream = CONTRACT["downstreamMusicApplications"]
        self.assertEqual("POST_CANONICAL_TEACHER_REVIEW_VALIDATION", downstream["integrationPosition"])
        self.assertIs(downstream["rawOmrCandidateInputAllowed"], False)
        self.assertIs(downstream["directBrowserEngineCallsAllowed"], False)
        self.assertIs(downstream["downstreamMayMutateCanonicalOrTeacherRevision"], False)
        self.assertIs(downstream["productionDerivedOutputRequiresApprovedTeacherRevision"], True)
        guitar = downstream["musicXmlToGuitarTabEngine"]
        self.assertIs(guitar["architecturalSeamReserved"], True)
        self.assertIs(guitar["liveIntegrationActivated"], False)

    def test_all_current_architecture_documents_bind_to_current_state_contract(self) -> None:
        marker = "contracts/architecture-current-state-v1.json"
        for name, text in TEXT.items():
            with self.subTest(document=name):
                self.assertIn(marker, text)

    def test_main_architecture_names_all_current_addenda(self) -> None:
        text = TEXT["architecture.md"]
        for marker in (
            "architecture-stage5-7-current.md",
            "architecture-stage8-current.md",
            "architecture-stage9-11-current.md",
            "ui-architecture-phase1.md",
            "live-ui-api-security-architecture-v1.md",
            "downstream-music-application-integration-boundary.md",
        ):
            self.assertIn(marker, text)

    def test_ui_phase1_is_not_silently_reassigned_to_stage12(self) -> None:
        self.assertIn("not Stage 12", TEXT["ui-phase1"])
        self.assertIn("does not consume or reserve Stage 12 numbering", TEXT["roadmap"])
        self.assertIs(CONTRACT["approvedWorkstreams"]["uiArchitecturePhase1"]["stageNumberAssigned"], False)

    def test_live_ui_api_security_is_not_silently_reassigned_to_stage12(self) -> None:
        self.assertIn("does not consume Stage 12", TEXT["live-ui-api-security"])
        self.assertIs(CONTRACT["approvedWorkstreams"]["liveUiApiSecurityDesign"]["stageNumberAssigned"], False)

    def test_stale_current_state_phrases_do_not_return(self) -> None:
        forbidden = {
            "README.md": (
                "Gateway orchestration/execution is disabled.",
                "Teacher Review API + RBAC + immutable revisions | Not started",
            ),
            "architecture.md": (
                "public data plane and engine execution remain deliberately closed",
                "Teacher Review Score Editor TR-0A architecture contract foundation; no runtime capability is activated",
            ),
            "stage5-7": (
                "The first Stage 8 implementation should",
            ),
            "stage8": (
                "Autonomous repository-only development stops here by design.",
            ),
            "roadmap": (
                "Teacher Review API + RBAC + immutable revisions | Not started",
                "Approval-to-publication barrier | Not started",
            ),
            "security": (
                "Current Gateway orchestration remains disabled.",
            ),
            "teacher-review": (
                "This document defines the intended architectural position",
                "future Teacher Review Score Editor",
            ),
        }
        for name, phrases in forbidden.items():
            for phrase in phrases:
                with self.subTest(document=name, phrase=phrase):
                    self.assertNotIn(phrase, TEXT[name])

    def test_authority_invariants_are_all_true(self) -> None:
        for key, value in CONTRACT["authorityInvariants"].items():
            with self.subTest(invariant=key):
                self.assertIs(value, True)


if __name__ == "__main__":
    unittest.main()
