from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FOUNDATIONS = json.loads(
    (ROOT / "contracts" / "design-system-foundations-v1.json").read_text(encoding="utf-8")
)
UI = json.loads((ROOT / "contracts" / "ui-architecture-phase1-v1.json").read_text(encoding="utf-8"))
BRAND = json.loads((ROOT / "contracts" / "web-brand-rules-v1.json").read_text(encoding="utf-8"))
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "design-system-foundations-v1.md").read_text(encoding="utf-8")


class DesignSystemFoundationsV1Tests(unittest.TestCase):
    def test_contract_identity_and_parent_are_closed(self) -> None:
        self.assertEqual("scoremosaic-design-system-foundations-v1", FOUNDATIONS["version"])
        self.assertEqual("scoremosaic-ui-architecture-phase1-v1", FOUNDATIONS["parentWorkstream"])
        self.assertIs(FOUNDATIONS["stageNumberAssigned"], False)
        self.assertEqual(
            "APPROVED_REPOSITORY_DESIGN_SYSTEM_FOUNDATIONS_BASELINE",
            FOUNDATIONS["status"],
        )
        self.assertEqual(
            "contracts/design-system-foundations-v1.json",
            UI["designSystem"]["foundationsContract"],
        )

    def test_current_architecture_registers_repository_ready_but_not_figma_applied(self) -> None:
        self.assertEqual("11-F", CURRENT["asOfStage"])
        workstream = CURRENT["approvedWorkstreams"]["uiArchitecturePhase1"]
        self.assertEqual(
            "contracts/design-system-foundations-v1.json",
            workstream["designSystemFoundationsContract"],
        )
        self.assertIs(workstream["designSystemFoundationsRepositoryReady"], True)
        self.assertIs(workstream["designSystemFoundationsAppliedInFigma"], False)
        self.assertIs(workstream["figmaHighFidelityStarted"], False)

    def test_approved_brand_palette_is_preserved(self) -> None:
        expected = {
            "navy": "#0B1D3A",
            "blue": "#1D4ED8",
            "teal": "#0EA5A6",
            "violet": "#7C3AED",
            "green": "#22C55E",
        }
        self.assertEqual(expected, FOUNDATIONS["primitiveColors"]["brand"])
        self.assertEqual(expected, {
            "navy": BRAND["palette"]["brandNavy"],
            "blue": BRAND["palette"]["brandBlue"],
            "teal": BRAND["palette"]["brandTeal"],
            "violet": BRAND["palette"]["brandViolet"],
            "green": BRAND["palette"]["brandGreen"],
        })

    def test_brand_and_status_semantics_remain_separate(self) -> None:
        brand_values = set(FOUNDATIONS["primitiveColors"]["brand"].values())
        status = FOUNDATIONS["primitiveColors"]["status"]
        for key in ("success", "warning", "danger", "focus"):
            self.assertNotIn(status[key], brand_values, key)
        self.assertIs(FOUNDATIONS["principles"]["brandColorDoesNotEncodeAuthority"], True)
        self.assertIs(FOUNDATIONS["principles"]["statusMeaningCannotRelyOnColorAlone"], True)
        self.assertIn("do **not** automatically mean success", DOC)

    def test_semantic_colors_reference_known_primitives(self) -> None:
        roots = {
            "brand": set(FOUNDATIONS["primitiveColors"]["brand"]),
            "neutral": set(FOUNDATIONS["primitiveColors"]["neutral"]),
            "status": set(FOUNDATIONS["primitiveColors"]["status"]),
        }
        for name, reference in FOUNDATIONS["semanticColors"].items():
            with self.subTest(token=name):
                root, key = reference.split(".", 1)
                self.assertIn(root, roots)
                self.assertIn(key, roots[root])

    def test_typography_spacing_and_radius_are_explicit(self) -> None:
        typography = FOUNDATIONS["typography"]
        self.assertEqual("Inter", typography["family"])
        self.assertEqual(14, typography["styles"]["body"]["fontSize"])
        self.assertEqual(20, typography["styles"]["body"]["lineHeight"])
        self.assertIs(typography["wordmarkUsesUiTypography"], False)
        self.assertEqual([0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64], list(FOUNDATIONS["spacing"].values()))
        self.assertEqual(14, FOUNDATIONS["radius"]["panel"])
        self.assertEqual(9, FOUNDATIONS["radius"]["control"])

    def test_interaction_accessibility_floor_is_preserved(self) -> None:
        interaction = FOUNDATIONS["interaction"]
        self.assertGreaterEqual(interaction["minimumPointerHitTargetPx"], 44)
        self.assertGreaterEqual(interaction["focusOutlinePx"], 3)
        self.assertIs(interaction["disabledStateMustNotRelyOnOpacityAlone"], True)
        self.assertIs(interaction["hoverStateMustNotBeOnlyIndicatorOfActionability"], True)
        self.assertIs(FOUNDATIONS["iconography"]["iconOnlyControlsRequireAccessibleLabel"], True)

    def test_score_view_remains_primary_layout_authority_free_surface(self) -> None:
        self.assertIs(FOUNDATIONS["principles"]["scoreViewRemainsPrimaryWorkspace"], True)
        self.assertIs(FOUNDATIONS["layout"]["scoreColumnMustRemainLargest"], True)
        self.assertIs(FOUNDATIONS["layout"]["narrowLayoutMustPrioritizeScoreView"], True)
        self.assertEqual(
            ["issues", "score_and_evidence", "structured_edit"],
            FOUNDATIONS["layout"]["teacherReviewColumns"],
        )

    def test_starter_mode_policy_is_explicit_and_dark_mode_not_faked(self) -> None:
        modes = FOUNDATIONS["figmaModePolicy"]
        self.assertEqual("Starter", modes["currentPlan"])
        self.assertEqual(["Light"], modes["currentSupportedModesForThisBaseline"])
        self.assertIs(modes["darkModeArchitectureRequiredLater"], True)
        self.assertIs(modes["darkModeMayBeFakedWithDuplicateHardcodedFrames"], False)
        self.assertIs(modes["modeExpansionMustReuseSemanticTokenNames"], True)

    def test_figma_foundation_order_is_fail_closed(self) -> None:
        figma = FOUNDATIONS["figmaRequirements"]
        for key in (
            "primitiveVariablesBeforeSemanticVariables",
            "semanticColorsAliasPrimitives",
            "allVariableScopesExplicit",
            "webCodeSyntaxRequired",
            "textStylesRequired",
            "effectStylesRequired",
            "componentsMayNotPrecedeFoundations",
            "visualQaRequiredBeforeHighFidelity",
        ):
            self.assertIs(figma[key], True, key)
        self.assertIs(UI["figma"]["designSystemFoundationsRepositoryReady"], True)
        self.assertIs(UI["figma"]["designSystemFoundationsAppliedInFigma"], False)
        self.assertIs(UI["figma"]["highFidelityStarted"], False)

    def test_all_activation_locks_remain_false(self) -> None:
        for key, value in FOUNDATIONS["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)
        for key, value in UI["activationLocks"].items():
            with self.subTest(ui_lock=key):
                self.assertIs(value, False)


if __name__ == "__main__":
    unittest.main()
