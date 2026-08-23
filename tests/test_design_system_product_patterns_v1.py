from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = json.loads((ROOT / "contracts" / "design-system-product-patterns-v1.json").read_text(encoding="utf-8"))
UI = json.loads((ROOT / "contracts" / "ui-architecture-phase1-v1.json").read_text(encoding="utf-8"))
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "design-system-product-patterns-v1.md").read_text(encoding="utf-8")


class ProductPatternsV1Tests(unittest.TestCase):
    def test_identity_parent_and_registration(self) -> None:
        self.assertEqual("scoremosaic-design-system-product-patterns-v1", PATTERNS["version"])
        self.assertEqual("scoremosaic-design-system-music-domain-components-v1", PATTERNS["parentMusicDomainComponents"])
        self.assertIs(PATTERNS["stageNumberAssigned"], False)
        self.assertEqual("contracts/design-system-product-patterns-v1.json", UI["designSystem"]["productPatternsContract"])

    def test_async_state_vocabulary_is_complete_and_distinct(self) -> None:
        self.assertEqual(["idle", "loading", "success", "empty", "error", "unavailable", "stale"], PATTERNS["globalAsyncStates"])
        rules = PATTERNS["globalRules"]
        self.assertIs(rules["serverDerivedStateMustNotBeFabricatedLocally"], True)
        self.assertIs(rules["staleStateMustBeExplicit"], True)
        self.assertIs(rules["emptyIsNotError"], True)
        self.assertIs(rules["unavailableIsNotEmpty"], True)
        self.assertIs(rules["browserStatusIsNotDomainAuthority"], True)

    def test_application_shell_and_dashboard_are_task_oriented_not_authoritative(self) -> None:
        shell = PATTERNS["applicationShell"]
        self.assertEqual(["dashboard", "documents", "new_document", "review"], shell["primaryNavigation"])
        self.assertIs(shell["rules"]["compactLogoRequired"], True)
        self.assertIs(shell["rules"]["navigationStateIsPresentationOnly"], True)
        self.assertIs(shell["rules"]["accountDisplayDoesNotGrantAuthorization"], True)
        dashboard = PATTERNS["dashboard"]
        self.assertEqual("what_needs_attention_now", dashboard["primaryQuestion"])
        self.assertIs(dashboard["rules"]["countsReflectReadModelOnly"], True)
        self.assertIs(dashboard["rules"]["countDisplayMayNotCreateDocumentState"], True)
        self.assertIs(dashboard["rules"]["continueReviewRequiresExactDocumentRevisionContext"], True)

    def test_documents_do_not_collapse_published_and_public(self) -> None:
        rules = PATTERNS["documents"]["rules"]
        self.assertIs(rules["statusRequiresText"], True)
        self.assertIs(rules["filteringIsPresentationOnly"], True)
        self.assertIs(rules["rowOpenMustResolveStableDocumentIdentity"], True)
        self.assertIs(rules["publishedMustNotImplyPublicVisibility"], True)

    def test_new_document_remains_presentation_only_until_live_gate(self) -> None:
        rules = PATTERNS["newDocument"]["rules"]
        self.assertIs(rules["currentPhasePresentationOnly"], True)
        self.assertIs(rules["localFileSelectionIsNotUpload"], True)
        self.assertIs(rules["localValidationIsNotServerSafetyAdmission"], True)
        self.assertIs(rules["realUploadActivated"], False)
        self.assertIs(rules["unsafeOrUnsupportedInputMustHaveExplicitRejectionState"], True)

    def test_processing_cannot_fake_completion_or_approval(self) -> None:
        rules = PATTERNS["processing"]["rules"]
        self.assertIs(rules["completionMayNotBeFabricatedByTimer"], True)
        self.assertIs(rules["stepStateRequiresBoundedEvidence"], True)
        self.assertIs(rules["unknownOrStaleStateMustRemainRepresentable"], True)
        self.assertIs(rules["failureMustNotAutoAdvanceToReady"], True)
        self.assertIs(rules["reviewReadyDoesNotMeanApproved"], True)

    def test_teacher_review_and_revision_patterns_fail_closed(self) -> None:
        review = PATTERNS["teacherReviewWorkspace"]["rules"]
        self.assertIs(review["scoreViewRemainsLargest"], True)
        self.assertIs(review["synchronizationIsPresentationOnly"], True)
        self.assertIs(review["staleWorkspaceMustBecomeReadOnly"], True)
        self.assertIs(review["missingEvidenceMustNotBeInvented"], True)
        self.assertIs(review["rendererSelectionMayNotBecomeMutationIdentity"], True)
        revision = PATTERNS["revisionHistory"]["rules"]
        self.assertIs(revision["immutableOrderMustBePreserved"], True)
        self.assertIs(revision["historicalRevisionMustNotAppearCurrent"], True)
        self.assertIs(revision["compareIsReadOnly"], True)
        self.assertIs(revision["staleCurrentContextMustFailClosed"], True)

    def test_approval_and_publication_are_separate_external_authorities(self) -> None:
        approval = PATTERNS["approval"]["rules"]
        self.assertIs(approval["approvalSeparatedFromStructuredEdit"], True)
        self.assertIs(approval["explicitHumanActionRequired"], True)
        self.assertIs(approval["validationPassDoesNotAutoApprove"], True)
        self.assertIs(approval["approvalPresentationDoesNotExecuteApproval"], True)
        publication = PATTERNS["publicationPreparation"]["rules"]
        self.assertIs(publication["approvalAndPublicationSeparated"], True)
        self.assertIs(publication["publishedAndPublicVisibilitySeparated"], True)
        self.assertIs(publication["publicationExecutionActivated"], False)
        self.assertIs(publication["externalEffectRequiresSeparateGate"], True)

    def test_responsive_and_recovery_patterns_preserve_access(self) -> None:
        self.assertEqual(["score_view", "issues", "source_evidence", "structured_edit"], PATTERNS["responsive"]["narrowPriorityOrder"])
        self.assertIs(PATTERNS["responsive"]["rules"]["collapsedPanelsMustRemainKeyboardReachable"], True)
        self.assertIn("explicit_stale_banner", PATTERNS["recoveryPatterns"]["staleRevision"])
        self.assertIn("do_not_fake_success", PATTERNS["recoveryPatterns"]["networkUnavailableFuture"])

    def test_repository_prefigma_exit_is_true_but_visual_application_remains_required(self) -> None:
        exit_state = PATTERNS["preFigmaRepositoryExit"]
        for key in ("brandRulesReady", "foundationsReady", "coreComponentArchitectureReady", "musicDomainComponentArchitectureReady", "productPatternArchitectureReady"):
            self.assertIs(exit_state[key], True, key)
        self.assertIs(exit_state["figmaApplicationStillRequired"], True)
        self.assertIs(exit_state["highFidelityStillLocked"], True)
        self.assertIs(UI["figma"]["preFigmaRepositoryArchitectureReady"], True)
        self.assertIs(UI["figma"]["productPatternsAppliedInFigma"], False)
        self.assertIs(UI["figma"]["highFidelityStarted"], False)
        self.assertIn("Figma application         REQUIRED", DOC)

    def test_current_state_registers_same_fail_closed_exit(self) -> None:
        workstream = CURRENT["approvedWorkstreams"]["uiArchitecturePhase1"]
        self.assertEqual("11-F", CURRENT["asOfStage"])
        self.assertEqual("contracts/design-system-product-patterns-v1.json", workstream["productPatternsContract"])
        self.assertIs(workstream["productPatternArchitectureRepositoryReady"], True)
        self.assertIs(workstream["productPatternsAppliedInFigma"], False)
        self.assertIs(workstream["preFigmaRepositoryArchitectureReady"], True)
        self.assertIs(workstream["figmaHighFidelityStarted"], False)

    def test_all_activation_locks_false(self) -> None:
        for key, value in PATTERNS["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)
        for key, value in UI["activationLocks"].items():
            with self.subTest(ui_lock=key):
                self.assertIs(value, False)


if __name__ == "__main__":
    unittest.main()
