from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototypes" / "stage10-ui-application-experience"
HTML = PROTOTYPE / "index.html"
CSS = PROTOTYPE / "styles.css"
README = PROTOTYPE / "README.md"


class ShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.scripts: list[dict[str, str | None]] = []
        self.forms = 0
        self.buttons: list[dict[str, str | None]] = []
        self.meta: list[dict[str, str | None]] = []
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        data = dict(attrs)
        if data.get("id"):
            self.ids.add(data["id"])
        if tag == "script":
            self.scripts.append(data)
        if tag == "form":
            self.forms += 1
        if tag == "button":
            self.buttons.append(data)
        if tag == "meta":
            self.meta.append(data)
        for key in ("src", "href", "action"):
            if data.get(key):
                self.urls.append(data[key])


class Stage10BIntegratedProductShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")
        cls.parser = ShellParser()
        cls.parser.feed(cls.html)

    def test_required_product_regions_exist(self) -> None:
        for marker in (
            'class="app-header"',
            'class="panel issues-panel"',
            'id="score-view"',
            'class="panel edit-panel"',
            'class="panel evidence-panel"',
            'class="transport"',
            'class="statusbar"',
        ):
            self.assertIn(marker, self.html)

    def test_csp_blocks_script_and_network_execution(self) -> None:
        csp = next(
            meta.get("content", "")
            for meta in self.parser.meta
            if meta.get("http-equiv") == "Content-Security-Policy"
        )
        for directive in (
            "default-src 'none'",
            "connect-src 'none'",
            "script-src 'none'",
            "object-src 'none'",
            "frame-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
        ):
            self.assertIn(directive, csp)

    def test_shell_has_no_scripts_forms_or_remote_resources(self) -> None:
        self.assertEqual(self.parser.scripts, [])
        self.assertEqual(self.parser.forms, 0)
        for url in self.parser.urls:
            self.assertFalse(re.match(r"^(?:https?:)?//", url), url)

    def test_every_button_is_disabled_in_stage10b(self) -> None:
        self.assertGreater(len(self.parser.buttons), 0)
        for button in self.parser.buttons:
            self.assertIn("disabled", button)

    def test_authority_and_runtime_locks_are_visible(self) -> None:
        for marker in (
            "Local shell · no backend",
            "No ScoreEditCommand, revision, approval, or publication can be created",
            "No API · no persistence · no playback · no publication",
            "No source read",
        ):
            self.assertIn(marker, self.html)

    def test_responsive_and_reduced_motion_contract_exists(self) -> None:
        self.assertIn("@media (max-width: 760px)", self.css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        self.assertIn(".score-panel { order: 1; }", self.css)

    def test_readme_preserves_stage10c_boundary(self) -> None:
        for marker in (
            "no JavaScript",
            "no network",
            "no Teacher Review write",
            "Stage 10-C may add deterministic checked-in fixture data",
        ):
            self.assertIn(marker, self.readme)


if __name__ == "__main__":
    unittest.main()
