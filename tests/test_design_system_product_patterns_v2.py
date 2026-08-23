from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
V1 = json.loads((ROOT / "contracts" / "design-system-product-patterns-v1.json").read_text(encoding="utf-8"))
V2 = json.loads((ROOT / "contracts" / "design-system-product-patterns-v2.json").read_text(encoding="utf-8"))
UI = json.loads((ROOT / "contracts" / "ui-architecture-phase1-v1.json").read_text(encoding="utf-8"))
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "design-system-product-patterns-v2.md").read_text(encoding="utf-8")


class ProductPatternsV2Tests(unittest.TestCase):
    def test_v2_supersedes_v1_without_rewriting_v1_identity(self) -> None:
        self.assertEqual("scoremosaic-design-system-product-patterns-v1", V1["version"])
        self.assertEqual("scoremosaic-design-system-product-patterns-v2", V2["version"])
        self.assertEqual(V1["version"], V2["supersedes"])
        self.assertIn("v1 remains a historical repository baseline", DOC)

    def test_current_ui_and_architecture_point_to_v2(self) -> None:
        path = "contracts/design-system-product-patterns-v2.json"
        self.assertEqual(path, UI["designSystem"]["productPatternsContract"])
        self.assertEqual(path, CURRENT["approvedWorkstreams"]["uiArchitecturePhase1"]["productPatternsContract"])

    def test_primary_navigation_matches_ui_architecture(self) -> None:
        expected = ["dashboard", "documents", "upload", "teacher_review", "guitar_tab"]
        self.assertEqual(expected, V2["applicationShell"]["primaryNavigation"])
        self.assertEqual(expected, UI["informationArchitecture"]["primaryNavigation"])
        self.assertEqual(["account"], V2["applicationShell"]["secondaryNavigation"])
        self.assertIs(V2["applicationShell"]["rules"]["navigationStateIsPresentationOnly"], True)

    def test_dashboard_documents_and_upload_patterns_are_explicit(self) -> None:
        self.assertEqual(
            ["new_document_action", "needs_review_summary", "processing_summary", "continue_review"],
            V2["dashboard"]["requiredPatterns"],
        )
        self.assertEqual(
            ["search", "status_filter", "open_document"],
            V2["documents"]["requiredCapabilities"],
        )
        self.assertIs(V2["documents"]["rules"]["searchIsPresentationOnly"], True)
        self.assertEqual(["pdf", "jpg", "jpeg", "png"], V2["upload"]["acceptedPresentationTypes"])
        self.assertIs(V2["upload"]["rules"]["realUploadActivated"], False)
        self.assertIs(V2["upload"]["rules"]["coolifyPresenceDoesNotActivateUpload"], True)

    def test_guitar_tab_pattern_is_downstream_and_non_authoritative(self) -> None:
        guitar = V2["guitarTabWorkspace"]
        self.assertEqual(
            ["standard_notation", "guitar_tab", "fingering_options", "position_playability_evidence"],
            guitar["regions"],
        )
        for key in (
            "browserMayCallEngineDirectly",
            "mayMutateCanonicalScore",
            "mayCreateTeacherRevision",
            "mayApprove",
            "mayPublish",
        ):
            self.assertIs(guitar["rules"][key], False, key)
        self.assertIs(guitar["rules"]["productionDerivedOutputRequiresApprovedTeacherRevision"], True)
        self.assertIs(guitar["rules"]["missingEngineEvidenceMustNotBeInvented"], True)

    def test_existing_review_approval_publication_guards_are_preserved(self) -> None:
        self.assertIs(V2["teacherReviewWorkspace"]["rules"]["rendererSelectionMayNotBecomeMutationIdentity"], True)
        self.assertIs(V2["approval"]["rules"]["validationPassDoesNotAutoApprove"], True)
        self.assertIs(V2["publicationPreparation"]["rules"]["publicationExecutionActivated"], False)
        self.assertIs(V2["publicationPreparation"]["rules"]["publishedAndPublicVisibilitySeparated"], True)

    def test_all_activation_locks_remain_false(self) -> None:
        for key, value in V2["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)


if __name__ == "__main__":
    unittest.main()
