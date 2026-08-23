from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BRAND = json.loads((ROOT / "contracts" / "web-brand-rules-v1.json").read_text(encoding="utf-8"))
UI = json.loads((ROOT / "contracts" / "ui-architecture-phase1-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "web-brand-rules-v1.md").read_text(encoding="utf-8")
UI_DOC = (ROOT / "docs" / "ui-architecture-phase1.md").read_text(encoding="utf-8")


class WebBrandRulesV1Tests(unittest.TestCase):
    def test_contract_identity_and_parent(self) -> None:
        self.assertEqual("scoremosaic-web-brand-rules-v1", BRAND["version"])
        self.assertEqual("scoremosaic-ui-architecture-phase1-v1", BRAND["parentWorkstream"])
        self.assertIs(BRAND["stageNumberAssigned"], False)
        self.assertEqual("contracts/web-brand-rules-v1.json", UI["designSystem"]["brandRulesContract"])

    def test_scoremosaic_is_master_brand(self) -> None:
        root = BRAND["brandRoot"]
        self.assertEqual("ScoreMosaic", root["name"])
        self.assertEqual("SCOREMOSAIC", root["primaryWordmark"])
        self.assertIs(root["primaryLogoHasSubtitle"], False)
        self.assertIs(root["omrGatewayIsBrandRoot"], False)
        self.assertIn("OMR Gateway", BRAND["logoSystem"]["productLockup"]["allowedModuleExamples"])
        self.assertIs(BRAND["logoSystem"]["productLockup"]["moduleLabelMayReplaceBrandName"], False)

    def test_required_logo_variants_are_defined(self) -> None:
        logo = BRAND["logoSystem"]
        for key in ("primary", "compact", "appIcon", "productLockup", "monochrome"):
            self.assertIn(key, logo)
        self.assertEqual("symbol_above_wordmark", logo["primary"]["composition"])
        self.assertIsNone(logo["primary"]["subtitle"])
        self.assertEqual("symbol_left_wordmark_right", logo["compact"]["composition"])
        self.assertIs(logo["appIcon"]["mustRemainLegibleAt16Px"], True)
        self.assertIs(logo["monochrome"]["whiteReverseRequired"], True)

    def test_palette_is_closed(self) -> None:
        self.assertEqual(
            {
                "brandNavy": "#0B1D3A",
                "brandBlue": "#1D4ED8",
                "brandTeal": "#0EA5A6",
                "brandViolet": "#7C3AED",
                "brandGreen": "#22C55E",
            },
            BRAND["palette"],
        )

    def test_brand_color_cannot_replace_status_semantics(self) -> None:
        policy = BRAND["colorPolicy"]
        self.assertIs(policy["brandGradientMayEncodeValidationState"], False)
        self.assertIs(policy["brandGradientMayEncodeApprovalState"], False)
        self.assertIs(policy["brandGradientMayEncodePublicationState"], False)
        self.assertIs(policy["statusMeaningMayRelyOnColorAlone"], False)

    def test_small_size_and_asset_governance_are_explicit(self) -> None:
        sizes = BRAND["minimumDigitalSize"]
        self.assertEqual(32, sizes["fullMosaicSymbolWidthCssPx"])
        self.assertEqual(32, sizes["simplifiedAppSymbolRequiredBelowCssPx"])
        self.assertEqual([16, 24, 32], sizes["faviconTargetSizesCssPx"])
        assets = BRAND["assetGovernance"]
        self.assertIs(assets["vectorMasterRequiredBeforeProductionExport"], True)
        self.assertIs(assets["rasterReferenceAloneIsNotProductionMaster"], True)
        self.assertIs(assets["faviconExportsMustComeFromSimplifiedAppIconMaster"], True)

    def test_web_placement_map_is_closed(self) -> None:
        self.assertEqual(
            {
                "navigation": "compact",
                "landingHero": "primary",
                "favicon": "appIcon",
                "pwa": "appIcon",
                "moduleHeader": "productLockup",
                "technicalPrintOrSingleColor": "monochrome",
            },
            BRAND["webPlacement"],
        )

    def test_brand_rules_do_not_activate_runtime_authority(self) -> None:
        for key, value in BRAND["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)

    def test_docs_bind_brand_rules_to_ui_architecture(self) -> None:
        self.assertIn("contracts/web-brand-rules-v1.json", DOC)
        self.assertIn("contracts/web-brand-rules-v1.json", UI_DOC)
        self.assertIn("ScoreMosaic", DOC)
        self.assertIn("OMR Gateway", DOC)
        self.assertIn("Brand color is not application authority", DOC)


if __name__ == "__main__":
    unittest.main()
