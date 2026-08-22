from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "stage10-ui-application-experience-v1.json"
DOC = ROOT / "docs" / "stage10a-ui-application-experience-contract.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage10AUiApplicationExperienceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load(CONTRACT)
        cls.document = DOC.read_text(encoding="utf-8")

    def test_identity_and_slice_order(self) -> None:
        self.assertEqual(self.contract["version"], "scoremosaic-stage10-ui-application-experience-v1")
        self.assertEqual(self.contract["stage"], "10-A")
        self.assertEqual(
            self.contract["stageSlices"],
            [
                "10-A-contract",
                "10-B-product-shell",
                "10-C-fixture-readonly-review",
                "10-D-disconnected-edit-intent-ux",
                "10-E-accessibility-responsive-hardening",
                "10-F-exit-eligibility",
            ],
        )

    def test_local_fixture_ui_is_allowed(self) -> None:
        allowed = self.contract["allowed"]
        for field in (
            "repositoryOwnedHtmlCssJavascript",
            "checkedInDeterministicFixtures",
            "inMemoryPresentationState",
            "keyboardAccessibleLocalInteractions",
            "readOnlyIssueFocus",
            "readOnlySourceEvidencePresentation",
            "disconnectedEditIntentDraft",
        ):
            self.assertIs(allowed[field], True, field)

    def test_live_and_durable_capabilities_are_forbidden(self) -> None:
        forbidden = self.contract["forbidden"]
        for field, value in forbidden.items():
            self.assertIs(value, True, field)

    def test_browser_isolation_is_fail_closed(self) -> None:
        security = self.contract["browserSecurity"]
        for field, value in security.items():
            self.assertIs(value, True, field)

    def test_browser_and_fixture_never_gain_authority(self) -> None:
        authority = self.contract["authority"]
        for field, value in authority.items():
            self.assertIs(value, False, field)

    def test_accessibility_baseline_is_required(self) -> None:
        accessibility = self.contract["accessibility"]
        for field, value in accessibility.items():
            self.assertIs(value, True, field)

    def test_every_runtime_activation_lock_remains_false(self) -> None:
        for name, value in self.contract["activationLocks"].items():
            self.assertIs(value, False, name)

    def test_document_preserves_stage11_boundary(self) -> None:
        for marker in (
            "Stage 11 UI↔application/API integration boundary",
            "Stage 9 provisioning remains intentionally deferred",
            "fixture data == production truth",
            "local edit intent == ScoreEditCommand",
            "no network, persistence, auth, upload, write, approval, publication, playback, or production infrastructure was activated",
        ):
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
