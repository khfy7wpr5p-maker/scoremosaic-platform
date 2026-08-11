from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELL_DIR = ROOT / "prototypes" / "ui-0b-static-shell"
HTML_PATH = SHELL_DIR / "index.html"
CSS_PATH = SHELL_DIR / "styles.css"


class _ShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.forbidden_tags: list[str] = []
        self.buttons_without_disabled: list[int] = []
        self.remote_or_executable_attributes: list[tuple[str, str, str]] = []
        self._button_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value for key, value in attrs}

        element_id = attr_map.get("id")
        if element_id:
            self.ids.add(element_id)

        if tag in {"script", "form", "iframe", "object", "embed"}:
            self.forbidden_tags.append(tag)

        if tag == "button":
            self._button_count += 1
            if "disabled" not in attr_map:
                self.buttons_without_disabled.append(self._button_count)

        for key in ("src", "href", "action"):
            value = attr_map.get(key)
            if value and ("://" in value or value.lower().startswith("javascript:")):
                self.remote_or_executable_attributes.append((tag, key, value))


class Ui0BStaticShellContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.parser = _ShellParser()
        cls.parser.feed(cls.html)

    def test_required_workspace_regions_exist(self) -> None:
        required_ids = {
            "issues-panel",
            "score-view",
            "structured-edit",
            "source-evidence",
            "review-transport",
            "validation-status",
        }
        self.assertTrue(required_ids.issubset(self.parser.ids))

    def test_static_shell_contains_no_active_runtime_surfaces(self) -> None:
        self.assertEqual([], self.parser.forbidden_tags)
        self.assertEqual([], self.parser.remote_or_executable_attributes)
        self.assertEqual([], self.parser.buttons_without_disabled)

    def test_content_security_policy_blocks_network_and_execution(self) -> None:
        required_csp_directives = (
            "default-src 'none'",
            "connect-src 'none'",
            "script-src 'none'",
            "object-src 'none'",
            "frame-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
        )
        for directive in required_csp_directives:
            with self.subTest(directive=directive):
                self.assertIn(directive, self.html)

    def test_css_does_not_load_external_assets(self) -> None:
        self.assertNotIn("url(", self.css.lower())
        self.assertNotIn("@import", self.css.lower())

    def test_shell_does_not_claim_connected_capabilities(self) -> None:
        lowered = self.html.lower()
        for required_phrase in (
            "no backend connection",
            "score renderer not connected",
            "no review data connected",
            "no source loaded",
            "writes remain disabled",
        ):
            with self.subTest(required_phrase=required_phrase):
                self.assertIn(required_phrase, lowered)


if __name__ == "__main__":
    unittest.main()
