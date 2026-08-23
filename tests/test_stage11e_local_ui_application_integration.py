from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "prototypes" / "stage10-ui-application-experience"
STAGE11 = ROOT / "prototypes" / "stage11-ui-application-contracts"
HTML = (UI / "index.html").read_text(encoding="utf-8")
APP = (UI / "app.js").read_text(encoding="utf-8")
EDIT = (UI / "edit-intent.js").read_text(encoding="utf-8")
LOCAL_APP = (STAGE11 / "local-application.js").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "stage11e-local-ui-application-integration.md").read_text(encoding="utf-8")


class Stage11ELocalUiApplicationIntegrationTests(unittest.TestCase):
    def test_stage11_scripts_load_before_ui_scripts(self) -> None:
        expected = [
            "fixture.js",
            "../stage11-ui-application-contracts/read-adapter.js",
            "../stage11-ui-application-contracts/edit-intent-adapter.js",
            "../stage11-ui-application-contracts/application-state.js",
            "../stage11-ui-application-contracts/local-application.js",
            "app.js",
            "edit-intent.js",
        ]
        positions = [HTML.index(f'src="{src}"') for src in expected]
        self.assertEqual(positions, sorted(positions))

    def test_csp_remains_disconnected(self) -> None:
        for directive in (
            "default-src 'none'",
            "connect-src 'none'",
            "script-src 'self'",
            "object-src 'none'",
            "frame-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
        ):
            self.assertIn(directive, HTML)
        self.assertNotRegex(HTML, r'<script[^>]+src=["\']https?://')

    def test_local_application_is_explicitly_nonproduction_and_nonauthoritative(self) -> None:
        for marker in (
            "productionApplication: false",
            "authoritative: false",
            "networkCapable: false",
            "persistent: false",
        ):
            self.assertIn(marker, LOCAL_APP)

    def test_ui_reads_through_local_application(self) -> None:
        for kind in ("review.read", "issues.read", "sourceEvidence.read", "validation.read"):
            self.assertIn(f"application.read('{kind}')", APP)
        self.assertIn("statesReady", APP)
        self.assertIn("Local typed application data failed closed", APP)

    def test_structured_edit_uses_typed_local_application(self) -> None:
        self.assertIn("application.read('issues.read')", EDIT)
        self.assertIn("application.prepareEditIntent", EDIT)
        self.assertIn("result?.phase !== 'ready'", EDIT)
        self.assertIn("result.authority?.authoritative !== false", EDIT)
        self.assertIn("preview.textContent = JSON.stringify(intent, null, 2)", EDIT)

    def test_local_application_has_no_live_transport_or_persistence_apis(self) -> None:
        combined = LOCAL_APP + "\n" + APP + "\n" + EDIT
        banned = {
            "fetch": r"\bfetch\s*\(",
            "xhr": r"XMLHttpRequest",
            "websocket": r"WebSocket",
            "eventsource": r"EventSource",
            "localStorage": r"localStorage",
            "sessionStorage": r"sessionStorage",
            "indexedDB": r"indexedDB",
            "cookie": r"document\.cookie",
            "serviceWorker": r"serviceWorker",
            "clipboard": r"navigator\.clipboard",
            "navigation": r"\b(?:window|document)\.location\b",
            "innerHTML": r"innerHTML",
            "insertAdjacentHTML": r"insertAdjacentHTML",
            "eval": r"\beval\s*\(",
            "Function": r"new\s+Function",
        }
        for name, pattern in banned.items():
            with self.subTest(api=name):
                self.assertIsNone(re.search(pattern, combined))

    def test_document_preserves_stage11f_boundary(self) -> None:
        self.assertIn("Disconnected fixture-backed integration only", DOC)
        self.assertIn("There is no production or network fallback", DOC)
        self.assertIn("not a ScoreEditCommand", DOC)
        self.assertIn("Stage 11-F", DOC)


if __name__ == "__main__":
    unittest.main()
