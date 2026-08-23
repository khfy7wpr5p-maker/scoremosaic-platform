from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE = json.loads(
    (ROOT / "contracts" / "design-system-core-components-v1.json").read_text(encoding="utf-8")
)
FOUNDATIONS = json.loads(
    (ROOT / "contracts" / "design-system-foundations-v1.json").read_text(encoding="utf-8")
)
UI = json.loads((ROOT / "contracts" / "ui-architecture-phase1-v1.json").read_text(encoding="utf-8"))
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "design-system-core-components-v1.md").read_text(encoding="utf-8")


class DesignSystemCoreComponentsV1Tests(unittest.TestCase):
    def test_contract_identity_and_parent_chain_are_closed(self) -> None:
        self.assertEqual("scoremosaic-design-system-core-components-v1", CORE["version"])
        self.assertEqual("scoremosaic-design-system-foundations-v1", CORE["parentFoundations"])
        self.assertEqual("scoremosaic-ui-architecture-phase1-v1", CORE["parentWorkstream"])
        self.assertIs(CORE["stageNumberAssigned"], False)
        self.assertEqual(
            "contracts/design-system-core-components-v1.json",
            UI["designSystem"]["coreComponentsContract"],
        )

    def test_repository_ready_does_not_claim_figma_or_production_implementation(self) -> None:
        state = CORE["implementationState"]
        self.assertIs(state["repositorySpecificationReady"], True)
        self.assertIs(state["figmaComponentsCreated"], False)
        self.assertIs(state["productionComponentsImplemented"], False)
        self.assertIs(state["highFidelityScreensStarted"], False)
        self.assertIs(UI["figma"]["coreComponentArchitectureRepositoryReady"], True)
        self.assertIs(UI["figma"]["coreComponentsAppliedInFigma"], False)
        self.assertIs(UI["figma"]["highFidelityStarted"], False)

    def test_current_architecture_registers_same_fail_closed_state(self) -> None:
        self.assertEqual("11-F", CURRENT["asOfStage"])
        workstream = CURRENT["approvedWorkstreams"]["uiArchitecturePhase1"]
        self.assertEqual(
            "contracts/design-system-core-components-v1.json",
            workstream["coreComponentsContract"],
        )
        self.assertIs(workstream["coreComponentArchitectureRepositoryReady"], True)
        self.assertIs(workstream["coreComponentsAppliedInFigma"], False)
        self.assertIs(workstream["figmaHighFidelityStarted"], False)

    def test_shared_sizes_preserve_foundation_hit_target_floor(self) -> None:
        floor = FOUNDATIONS["interaction"]["minimumPointerHitTargetPx"]
        self.assertEqual(44, floor)
        expected_heights = {"compact": 32, "default": 36, "comfortable": 40}
        for size, height in expected_heights.items():
            with self.subTest(size=size):
                self.assertEqual(height, CORE["sharedSizing"][size]["visualHeightPx"])
                self.assertGreaterEqual(CORE["sharedSizing"][size]["minimumHitTargetPx"], floor)

    def test_global_accessibility_and_authority_rules_are_closed(self) -> None:
        rules = CORE["globalRules"]
        for key in (
            "semanticTokensOnly",
            "visualEmphasisDoesNotGrantAuthority",
            "statusPresentationDoesNotCreateStatus",
            "browserComponentStateIsNotDomainAuthority",
            "visibleFocusRequired",
            "keyboardOperationRequired",
            "colorOnlyMeaningForbidden",
            "iconOnlyControlsRequireAccessibleName",
        ):
            self.assertIs(rules[key], True, key)

    def test_button_primary_and_danger_do_not_collapse_domain_authority(self) -> None:
        button = CORE["button"]
        self.assertEqual(["primary", "secondary", "ghost", "danger"], button["variants"])
        self.assertIn("loading", button["states"])
        semantics = button["semantics"]
        self.assertIs(semantics["primaryDoesNotMeanApprove"], True)
        self.assertIs(semantics["primaryDoesNotMeanPublish"], True)
        self.assertIs(semantics["dangerReservedForDestructiveIntent"], True)
        self.assertIs(semantics["dangerDoesNotBypassConfirmationPolicy"], True)
        self.assertIn("Primary button != approval authority", DOC)

    def test_icon_button_requires_accessible_name_tooltip_and_non_color_selected_cue(self) -> None:
        properties = CORE["iconButton"]["properties"]
        self.assertIs(properties["iconUsesInstanceSwap"], True)
        self.assertIs(properties["accessibleNameRequired"], True)
        self.assertIs(properties["tooltipOnHoverAndFocusRequired"], True)
        self.assertIs(properties["selectedStateMustHaveNonColorCue"], True)

    def test_tabs_preserve_keyboard_and_non_mutating_navigation(self) -> None:
        tabs = CORE["tabs"]
        self.assertIs(tabs["properties"]["selectedIndicatorRequired"], True)
        self.assertIs(tabs["properties"]["selectedStateMustNotRelyOnColorAlone"], True)
        self.assertIs(tabs["keyboard"]["arrowNavigationRequired"], True)
        self.assertIs(tabs["keyboard"]["homeEndNavigationRequired"], True)
        self.assertIs(tabs["keyboard"]["rovingTabIndexRequired"], True)
        self.assertIs(tabs["authority"]["tabSelectionMayNotMutateScoreDirectly"], True)

    def test_status_badge_is_display_only(self) -> None:
        badge = CORE["statusBadge"]
        self.assertEqual(
            ["neutral", "info", "success", "warning", "danger", "locked"],
            badge["tones"],
        )
        self.assertIs(badge["properties"]["textLabelRequired"], True)
        self.assertIs(badge["properties"]["colorOnlyMeaningForbidden"], True)
        authority = badge["authority"]
        self.assertIs(authority["badgeReflectsExistingStateOnly"], True)
        self.assertIs(authority["badgeMayNotCreateApproval"], True)
        self.assertIs(authority["badgeMayNotCreatePublication"], True)
        self.assertIs(authority["badgeMayNotCreateValidationPass"], True)

    def test_input_and_select_remain_local_until_typed_intent_boundary(self) -> None:
        input_authority = CORE["input"]["authority"]
        self.assertIs(input_authority["fieldValueIsLocalPresentationStateUntilTypedIntentBoundary"], True)
        self.assertIs(input_authority["fieldMayNotWriteScoreDirectly"], True)
        self.assertIs(input_authority["invalidVisualStateMayNotSubstituteServerValidation"], True)
        select_authority = CORE["select"]["authority"]
        self.assertIs(select_authority["selectedValueIsLocalUntilTypedIntentBoundary"], True)
        self.assertIs(select_authority["selectionMayNotWriteScoreDirectly"], True)

    def test_toolbar_is_not_authorization_boundary(self) -> None:
        toolbar = CORE["toolbar"]
        self.assertIs(toolbar["properties"]["ambiguousIconOnlyDestructiveActionForbidden"], True)
        self.assertIs(toolbar["keyboard"]["allActionsReachable"], True)
        self.assertIs(toolbar["authority"]["toolbarIsNotPermissionBoundary"], True)
        self.assertIs(toolbar["authority"]["hiddenOrDisabledActionDoesNotReplaceServerAuthorization"], True)

    def test_figma_build_policy_stays_blocked_until_foundations_can_be_applied(self) -> None:
        figma = CORE["figmaBuildPolicy"]
        self.assertIs(figma["foundationsMustBeAppliedBeforeComponentCreation"], True)
        self.assertIs(figma["oneComponentFamilyAtATime"], True)
        self.assertIs(figma["variablesMustBeBound"], True)
        self.assertIs(figma["metadataValidationRequired"], True)
        self.assertIs(figma["visualScreenshotValidationRequired"], True)
        self.assertIs(figma["currentFigmaBuildBlockedByStarterToolCallLimit"], True)

    def test_all_activation_locks_remain_false(self) -> None:
        for key, value in CORE["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)
        for key, value in UI["activationLocks"].items():
            with self.subTest(ui_lock=key):
                self.assertIs(value, False)


if __name__ == "__main__":
    unittest.main()
