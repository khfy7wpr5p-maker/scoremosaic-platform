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