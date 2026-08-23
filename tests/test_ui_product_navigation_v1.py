from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI_CONTRACT = json.loads((ROOT / "contracts" / "ui-architecture-phase1-v1.json").read_text(encoding="utf-8"))
DOWNSTREAM = json.loads((ROOT / "contracts" / "downstream-music-application-integration-v1.json").read_text(encoding="utf-8"))
HTML = (ROOT / "prototypes" / "stage10-ui-application-experience" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "prototypes" / "stage10-ui-application-experience" / "app.js").read_text(encoding="utf-8")


class UiProductNavigationV1Tests(unittest.TestCase):
    def test_primary_navigation_matches_approved_product_shell(self) -> None:
        self.assertEqual(
            ["dashboard", "documents", "upload", "teacher_review", "guitar_tab"],
            UI_CONTRACT["informationArchitecture"]["primaryNavigation"],
        )
        self.assertEqual(["account"], UI_CONTRACT["informationArchitecture"]["secondaryNavigation"])

    def test_upload_remains_preview_only(self) -> None:
        upload = UI_CONTRACT["screenArchitecture"]["upload"]
        self.assertIs(upload["presentationOnlyUntilLiveGate"], True)
        self.assertIs(upload["realFileSubmissionActivated"], False)
        self.assertEqual(["pdf", "jpg", "jpeg", "png"], upload["acceptedPresentationTypes"])
        self.assertIn('data-view="upload"', HTML)
        self.assertIn("Preview only · Upload not connected", HTML)
        self.assertNotIn('type="file"', HTML)

    def test_guitar_tab_is_separate_non_live_workspace(self) -> None:
        guitar = UI_CONTRACT["screenArchitecture"]["guitarTab"]
        self.assertIs(guitar["separateWorkspace"], True)
        self.assertIs(guitar["engineRuntimeActivated"], False)
        self.assertIs(DOWNSTREAM["guitarTabEngine"]["mayBeAddedToUiAsSeparateWorkspace"], True)
        self.assertIs(DOWNSTREAM["activationLocks"]["guitarTabLiveIntegrationActivated"], False)
        self.assertIn('data-view="guitar-tab"', HTML)
        self.assertIn("Guitar TAB", HTML)
        self.assertIn("Engine not connected", HTML)

    def test_navigation_switching_is_local_only(self) -> None:
        self.assertIn("data-product-view", HTML)
        self.assertIn("data-product-nav", HTML)
        self.assertIn("activateProductView", JS)
        for forbidden in (
            r"\bfetch\s*\(",
            r"XMLHttpRequest",
            r"WebSocket",
            r"EventSource",
            r"localStorage",
            r"sessionStorage",
            r"indexedDB",
            r"document\.cookie",
            r"\bwindow\.location\b",
        ):
            self.assertIsNone(re.search(forbidden, JS), forbidden)

    def test_core_authority_locks_remain_closed(self) -> None:
        locks = UI_CONTRACT["activationLocks"]
        for key in (
            "liveApiActivated",
            "realUploadActivated",
            "serverWriteActivated",
            "approvalExecutionActivated",
            "publicationExecutionActivated",
            "productionInfrastructureActivated",
        ):
            self.assertIs(locks[key], False, key)


if __name__ == "__main__":
    unittest.main()
