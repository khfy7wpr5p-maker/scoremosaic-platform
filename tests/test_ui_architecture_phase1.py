from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI = json.loads((ROOT / "contracts" / "ui-architecture-phase1-v1.json").read_text(encoding="utf-8"))
DOWNSTREAM = json.loads(
    (ROOT / "contracts" / "downstream-music-application-integration-v1.json").read_text(encoding="utf-8")
)
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "ui-architecture-phase1.md").read_text(encoding="utf-8")
DOWNSTREAM_DOC = (ROOT / "docs" / "downstream-music-application-integration-boundary.md").read_text(
    encoding="utf-8"
)


class UiArchitecturePhase1Tests(unittest.TestCase):
    def test_phase_is_approved_but_not_stage_numbered(self) -> None:
        self.assertEqual("scoremosaic-ui-architecture-phase1-v1", UI["version"])
        self.assertEqual("UI Architecture Phase 1", UI["workstream"])
        self.assertIs(UI["stageNumberAssigned"], False)
        self.assertEqual(
            "APPROVED_REPOSITORY_UI_ARCHITECTURE_BASELINE_LOW_FIDELITY_STARTED",
            UI["status"],
        )
        self.assertIn("not Stage 12", DOC)

    def test_primary_navigation_and_flow_are_closed(self) -> None:
        self.assertEqual(
            ["dashboard", "documents", "new_document", "review"],
            UI["informationArchitecture"]["primaryNavigation"],
        )
        self.assertEqual(["account"], UI["informationArchitecture"]["secondaryNavigation"])
        self.assertEqual(
            ["settings", "admin", "billing"],
            UI["informationArchitecture"]["deferredNavigation"],
        )
        self.assertEqual(
            [
                "dashboard",
                "new_document",
                "input_validation",
                "omr_processing",
                "review_ready",
                "teacher_review",
                "structured_correction",
                "validation",
                "revision",
                "human_approval",
                "publication_eligibility",
            ],
            UI["primaryUserFlow"],
        )

    def test_teacher_review_workspace_has_required_regions(self) -> None:
        self.assertEqual(
            [
                "document_revision_context",
                "issues",
                "score_view",
                "source_evidence",
                "structured_edit",
                "validation_revision_status",
            ],
            UI["screenArchitecture"]["teacherReview"]["requiredRegions"],
        )
        self.assertIs(UI["principles"]["scoreViewIsPrimaryWorkspace"], True)
        self.assertIs(UI["principles"]["rendererIsPresentationOnly"], True)

    def test_score_viewer_interactions_are_explicit(self) -> None:
        required = set(UI["scoreViewer"]["requiredInteractions"])
        self.assertTrue(
            {
                "page_navigation",
                "zoom",
                "fit_width",
                "fit_page",
                "measure_focus",
                "event_focus",
                "issue_overlay",
                "score_source_synchronization",
                "keyboard_issue_navigation",
                "staff_voice_context",
            }.issubset(required)
        )
        self.assertIs(UI["scoreViewer"]["rendererAuthoritative"], False)
        self.assertIs(UI["scoreViewer"]["selectionAuthoritative"], False)

    def test_structured_edit_preserves_stage11_authority_boundary(self) -> None:
        edit = UI["structuredEdit"]
        self.assertEqual("bounded_musical_controls", edit["mode"])
        self.assertIs(edit["rawMusicXmlEditingAllowed"], False)
        self.assertIs(edit["directServerMutationAllowed"], False)
        self.assertIs(edit["localIntentOnly"], True)
        self.assertEqual(
            ["pitch", "effective_duration", "dots", "remove_event"],
            edit["initialOperationFamilies"],
        )
        self.assertIs(UI["principles"]["localEditIntentIsNotScoreEditCommand"], True)

    def test_validation_approval_and_publication_remain_separate(self) -> None:
        self.assertIs(UI["validationRevision"]["validationPassImpliesApproval"], False)
        self.assertIs(UI["screenArchitecture"]["approval"]["separateFromEditWorkspace"], True)
        self.assertIs(UI["screenArchitecture"]["publicationPreparation"]["separateFromApproval"], True)
        self.assertIs(UI["screenArchitecture"]["publicationPreparation"]["executionActivated"], False)
        self.assertIs(UI["principles"]["saveIsNotApproval"], True)
        self.assertIs(UI["principles"]["approvalIsNotPublication"], True)

    def test_design_system_and_figma_sequence_are_defined(self) -> None:
        self.assertIn("color_tokens", UI["designSystem"]["foundations"])
        self.assertIn("button", UI["designSystem"]["coreComponents"])
        self.assertIn("score_viewer", UI["designSystem"]["musicComponents"])
        self.assertIs(UI["designSystem"]["tokenNamingRequired"], True)
        figma = UI["figma"]
        self.assertIs(figma["eligibleAfterThisBaseline"], True)
        self.assertIs(figma["lowFidelityStarted"], True)
        self.assertIs(figma["highFidelityStarted"], False)
        self.assertEqual("00_foundations", figma["logicalAreas"][0])
        self.assertEqual("design_freeze_v1", figma["sequence"][-1])

    def test_starter_page_grouping_preserves_all_logical_figma_areas(self) -> None:
        figma = UI["figma"]
        self.assertEqual("starter_plan_three_page_grouping", figma["physicalPagePolicy"])
        self.assertEqual(3, len(figma["physicalPages"]))
        grouped = [
            area
            for page in figma["physicalPages"]
            for area in page["logicalAreas"]
        ]
        self.assertEqual(set(figma["logicalAreas"]), set(grouped))
        self.assertEqual(len(figma["logicalAreas"]), len(grouped))
        self.assertIs(figma["logicalAreasMustNotBeDroppedBecauseOfPlanLimits"], True)

    def test_all_phase1_activation_locks_remain_false(self) -> None:
        for key, value in UI["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)

    def test_downstream_music_application_boundary_is_derivative_only(self) -> None:
        source = DOWNSTREAM["sourcePolicy"]
        self.assertIs(source["rawOmrCandidateAllowed"], False)
        self.assertIs(source["rawEngineOutputAllowed"], False)
        self.assertIs(source["productionDerivedOutputRequiresApprovedTeacherRevision"], True)
        self.assertIs(source["correctedMusicXmlSha256Required"], True)
        authority = DOWNSTREAM["authority"]
        for key in (
            "downstreamEngineMayMutateCanonicalScore",
            "downstreamEngineMayCreateTeacherRevision",
            "downstreamEngineMayApprove",
            "downstreamEngineMayPublish",
            "downstreamOutputIsAuthoritativeMusicalTruth",
            "browserMayCallDownstreamEngineDirectly",
        ):
            self.assertIs(authority[key], False, key)

    def test_guitar_tab_seam_is_reserved_but_not_live(self) -> None:
        guitar = DOWNSTREAM["guitarTabEngine"]
        self.assertEqual("MusicXML-to-GuitarTab-Engine", guitar["integrationName"])
        self.assertEqual("downstream_guitar_arrangement_and_fingering_service", guitar["role"])
        self.assertIs(guitar["mayRewriteSourceMusic"], False)
        self.assertIs(guitar["mayBeAddedToUiAsSeparateWorkspace"], True)
        for key, value in DOWNSTREAM["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)
        self.assertIn("MusicXML-to-GuitarTab-Engine", DOWNSTREAM_DOC)

    def test_current_architecture_registers_both_unnumbered_workstreams(self) -> None:
        self.assertEqual("11-F", CURRENT["asOfStage"])
        ui = CURRENT["approvedWorkstreams"]["uiArchitecturePhase1"]
        self.assertIs(ui["stageNumberAssigned"], False)
        self.assertIs(ui["figmaLowFidelityStarted"], True)
        self.assertIs(ui["figmaHighFidelityStarted"], False)
        downstream = CURRENT["approvedWorkstreams"]["downstreamMusicApplicationIntegration"]
        self.assertIs(downstream["stageNumberAssigned"], False)
        self.assertIs(downstream["guitarTabLiveIntegrationActivated"], False)
        self.assertIs(CURRENT["authorityInvariants"]["downstreamMusicApplicationIsNotScoreAuthority"], True)


if __name__ == "__main__":
    unittest.main()
