from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototypes" / "stage10-ui-application-experience"
HTML = (PROTOTYPE / "index.html").read_text(encoding="utf-8")
FIXTURE = (PROTOTYPE / "fixture.js").read_text(encoding="utf-8")
APP = (PROTOTYPE / "app.js").read_text(encoding="utf-8")


class Stage10CFixtureReadonlyReviewTests(unittest.TestCase):
    def test_fixture_is_explicitly_non_authoritative_and_nonproduction(self) -> None:
        self.assertIn("authoritativeTruth: false", FIXTURE)
        self.assertIn("productionArtifact: false", FIXTURE)
        self.assertIn("freezeDeep", FIXTURE)
        self.assertIn("Object.freeze", FIXTURE)

    def test_fixture_covers_blocking_warning_and_info_review_states(self) -> None:
        for marker in ("severity: 'blocking'", "severity: 'warning'", "severity: 'info'"):
            self.assertIn(marker, FIXTURE)
        self.assertIn("approvalEligible: false", FIXTURE)
        self.assertIn("publicationEligible: false", FIXTURE)

    def test_csp_allows_only_local_scripts_and_still_blocks_network(self) -> None:
        self.assertIn("script-src 'self'", HTML)
        self.assertIn("connect-src 'none'", HTML)
        self.assertIn("form-action 'none'", HTML)
        self.assertIn('<script src="fixture.js" defer></script>', HTML)
        self.assertIn('<script src="app.js" defer></script>', HTML)

    def test_app_has_no_network_persistence_navigation_or_injection_apis(self) -> None:
        combined = APP + "\n" + FIXTURE
        banned_patterns = {
            "fetch": r"\bfetch\s*\(",
            "xhr": r"XMLHttpRequest",
            "websocket": r"WebSocket",
            "eventsource": r"EventSource",
            "localStorage": r"localStorage",
            "sessionStorage": r"sessionStorage",
            "indexedDb": r"indexedDB",
            "cookie": r"document\.cookie",
            "innerHTML": r"innerHTML",
            "insertAdjacentHTML": r"insertAdjacentHTML",
            "eval": r"\beval\s*\(",
            "Function": r"new\s+Function",
            "location": r"(?:window\.)?location\s*[=.]",
        }
        for name, pattern in banned_patterns.items():
            self.assertIsNone(re.search(pattern, combined), name)

    def test_app_uses_safe_dom_construction_and_in_memory_state(self) -> None:
        for marker in (
            "document.createElement",
            "textContent",
            "replaceChildren",
            "addEventListener",
            "const state =",
        ):
            self.assertIn(marker, APP)

    def test_issue_focus_fields_are_bounded_to_fixture_location(self) -> None:
        for marker in (
            "focused-page",
            "focused-measure",
            "focused-staff",
            "focused-voice",
            "focused-event",
            "source-region",
            "candidate-id",
            "canonical-id",
        ):
            self.assertIn(marker, HTML)

    def test_server_authority_controls_remain_disabled(self) -> None:
        self.assertIn('class="primary-button" type="button" disabled', HTML)
        self.assertIn("No ScoreEditCommand, revision, approval, or publication can be created", HTML)
        self.assertIn("no API · no persistence · no playback · no publication", HTML)


if __name__ == "__main__":
    unittest.main()
