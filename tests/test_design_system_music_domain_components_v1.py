from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MUSIC = json.loads((ROOT / "contracts" / "design-system-music-domain-components-v1.json").read_text(encoding="utf-8"))
CORE = json.loads((ROOT / "contracts" / "design-system-core-components-v1.json").read_text(encoding="utf-8"))
UI = json.loads((ROOT / "contracts" / "ui-architecture-phase1-v1.json").read_text(encoding="utf-8"))
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))


class MusicDomainComponentsV1Tests(unittest.TestCase):
    def test_identity_and_parent_chain(self) -> None:
        self.assertEqual("scoremosaic-design-system-music-domain-components-v1", MUSIC["version"])
        self.assertEqual("scoremosaic-design-system-core-components-v1", MUSIC["parentCoreComponents"])
        self.assertIs(MUSIC["stageNumberAssigned"], False)
        self.assertEqual("contracts/design-system-music-domain-components-v1.json", UI["designSystem"]["musicDomainComponentsContract"])

    def test_repository_ready_but_figma_and_high_fidelity_locked(self) -> None:
        state = MUSIC["implementationState"]
        self.assertIs(state["repositorySpecificationReady"], True)
        self.assertIs(state["figmaComponentsCreated"], False)
        self.assertIs(state["productionComponentsImplemented"], False)
        self.assertIs(state["highFidelityScreensStarted"], False)
        self.assertIs(UI["figma"]["musicDomainComponentArchitectureRepositoryReady"], True)
        self.assertIs(UI["figma"]["musicDomainComponentsAppliedInFigma"], False)
        self.assertIs(UI["figma"]["highFidelityStarted"], False)

    def test_current_state_registers_fail_closed_music_components(self) -> None:
        workstream = CURRENT["approvedWorkstreams"]["uiArchitecturePhase1"]
        self.assertEqual("11-F", CURRENT["asOfStage"])
        self.assertEqual("contracts/design-system-music-domain-components-v1.json", workstream["musicDomainComponentsContract"])
        self.assertIs(workstream["musicDomainComponentArchitectureRepositoryReady"], True)
        self.assertIs(workstream["musicDomainComponentsAppliedInFigma"], False)

    def test_global_music_authority_rules(self) -> None:
        rules = MUSIC["globalRules"]
        for key in (
            "musicComponentsComposeCoreComponents",
            "stableDomainIdentityRequiredForSelection",
            "rendererCoordinatesAreNotDomainIdentity",
            "visualSelectionIsNotScoreMutation",
            "evidenceIsNotAuthoritativeTruth",
            "statusPresentationDoesNotCreateStatus",
            "revisionPresentationDoesNotCreateRevision",
            "localEditFieldDoesNotCreateScoreEditCommand",
            "colorOnlyMeaningForbidden",
        ):
            self.assertIs(rules[key], True, key)

    def test_issue_card_synchronizes_focus_without_mutation(self) -> None:
        issue = MUSIC["issueCard"]
        self.assertEqual(["blocking", "warning", "info"], issue["severities"])
        self.assertIs(issue["interaction"]["selectionMayRequestScoreFocus"], True)
        self.assertIs(issue["interaction"]["selectionMayRequestEvidenceFocus"], True)
        self.assertIs(issue["interaction"]["selectionMayRequestEditTargetFocus"], True)
        self.assertIs(issue["authority"]["issueCardMayResolveIssueDirectly"], False)
        self.assertIs(issue["authority"]["issueCardMayMutateScore"], False)
        self.assertIs(issue["authority"]["suggestedReviewActionIsAuthoritative"], False)

    def test_validation_status_does_not_create_approval(self) -> None:
        validation = MUSIC["validationStatus"]
        self.assertIn("exact_revision_identity", validation["requiredContent"])
        self.assertIs(validation["authority"]["displayedPassMayCreateApproval"], False)
        self.assertIs(validation["authority"]["displayedPassMayCreatePublicationEligibility"], False)
        self.assertIs(validation["authority"]["localRecalculationMaySubstituteServerValidation"], False)

    def test_revision_indicator_is_identity_safe(self) -> None:
        revision = MUSIC["revisionIndicator"]
        self.assertIn("revision_identity", revision["requiredContent"])
        self.assertIs(revision["authority"]["indicatorMayCreateRevision"], False)
        self.assertIs(revision["authority"]["indicatorMayChangeCurrentRevision"], False)
        self.assertIs(revision["authority"]["historicalRevisionMustNotAppearCurrent"], True)
        self.assertIs(revision["authority"]["staleStateMustBeExplicit"], True)

    def test_evidence_viewer_never_promotes_pixel_or_engine_evidence_to_truth(self) -> None:
        safety = MUSIC["evidenceViewer"]["safety"]
        self.assertIs(safety["sourceCropMayBePresentedAsTruth"], False)
        self.assertIs(safety["enginePredictionMayBePresentedAsTruth"], False)
        self.assertIs(safety["viewerCoordinatesMayBecomeMutationIdentity"], False)
        self.assertIs(safety["unsafeExternalResourceFetchAllowed"], False)
        self.assertIs(safety["evidenceMustRemainBoundToExactContext"], True)

    def test_structured_edit_field_remains_intent_only(self) -> None:
        field = MUSIC["structuredEditField"]
        self.assertEqual(CORE["nextMusicDomainComponents"][4], "structured_edit_field")
        self.assertEqual(["pitch", "effective_duration", "dots", "remove_event"], field["operationFamilies"])
        self.assertIn("stable_target_identity", field["requiredContext"])
        self.assertIn("exact_revision_identity", field["requiredContext"])
        self.assertIn("old_value_precondition", field["requiredContext"])
        self.assertIs(field["behavior"]["prepareIntentOnly"], True)
        self.assertIs(field["behavior"]["rawMusicXmlEditingAllowed"], False)
        self.assertIs(field["behavior"]["directServerWriteAllowed"], False)
        self.assertIs(field["behavior"]["staleContextFailsClosed"], True)
        self.assertIs(field["authority"]["localFieldValueIsScoreEditCommand"], False)
        self.assertIs(field["authority"]["preparedIntentIsTeacherRevision"], False)

    def test_markers_require_stable_domain_identity_and_are_non_mutating(self) -> None:
        measure = MUSIC["measureMarker"]
        issue = MUSIC["issueMarker"]
        self.assertIn("stable_measure_identity", measure["requiredContext"])
        self.assertIs(measure["authority"]["markerPositionIsDomainIdentity"], False)
        self.assertIs(measure["authority"]["markerMayMutateMeasure"], False)
        self.assertIn("stable_domain_target_identity", issue["requiredContext"])
        self.assertIs(issue["authority"]["markerMayResolveIssue"], False)
        self.assertIs(issue["authority"]["markerMayMutateScore"], False)

    def test_figma_build_remains_blocked_until_dependencies_exist(self) -> None:
        policy = MUSIC["figmaBuildPolicy"]
        self.assertIs(policy["foundationsAndCoreComponentsMustExistFirst"], True)
        self.assertIs(policy["coreComponentsMustBeReused"], True)
        self.assertIs(policy["metadataValidationRequired"], True)
        self.assertIs(policy["visualScreenshotValidationRequired"], True)
        self.assertIs(policy["currentFigmaBuildBlockedByStarterToolCallLimit"], True)

    def test_all_activation_locks_false(self) -> None:
        for key, value in MUSIC["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)
        for key, value in UI["activationLocks"].items():
            with self.subTest(ui_lock=key):
                self.assertIs(value, False)


if __name__ == "__main__":
    unittest.main()
