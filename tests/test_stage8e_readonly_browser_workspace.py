from __future__ import annotations

from html.parser import HTMLParser
from hashlib import sha256
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = ROOT / "prototypes" / "stage8e-readonly-review-workspace"
HTML_PATH = WORKSPACE_DIR / "index.html"
JS_PATH = WORKSPACE_DIR / "adapter.js"
CSS_PATH = WORKSPACE_DIR / "readonly-adapter.css"


class _WorkspaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.forbidden_tags: list[str] = []
        self.remote_attributes: list[tuple[str, str, str]] = []
        self.scripts: list[dict[str, str | None]] = []
        self.static_buttons_without_disabled: list[int] = []
        self._button_count = 0
        self._projection_capture = False
        self.projection_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value for key, value in attrs}
        element_id = attr_map.get("id")
        if element_id:
            self.ids.add(element_id)

        if tag in {"form", "iframe", "object", "embed"}:
            self.forbidden_tags.append(tag)

        if tag == "button":
            self._button_count += 1
            if "disabled" not in attr_map:
                self.static_buttons_without_disabled.append(self._button_count)

        if tag == "script":
            self.scripts.append(attr_map)
            self._projection_capture = (
                attr_map.get("id") == "scoremosaic-projection"
                and attr_map.get("type") == "application/json"
            )

        for key in ("src", "href", "action"):
            value = attr_map.get(key)
            if value and ("://" in value or value.lower().startswith("javascript:")):
                self.remote_attributes.append((tag, key, value))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._projection_capture = False

    def handle_data(self, data: str) -> None:
        if self._projection_capture:
            self.projection_chunks.append(data)


class Stage8EReadOnlyBrowserWorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.javascript = JS_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.parser = _WorkspaceParser()
        cls.parser.feed(cls.html)
        cls.projection = json.loads("".join(cls.parser.projection_chunks))

    def test_required_review_regions_and_accessible_status_exist(self) -> None:
        required_ids = {
            "issues-panel",
            "issue-list",
            "score-view",
            "structured-edit",
            "source-evidence",
            "observation-list",
            "review-transport",
            "validation-status",
        }
        self.assertTrue(required_ids.issubset(self.parser.ids))
        self.assertIn('role="listbox"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('aria-atomic="true"', self.html)

    def test_csp_allows_only_local_script_execution_and_blocks_network(self) -> None:
        for directive in (
            "default-src 'none'",
            "style-src 'self'",
            "connect-src 'none'",
            "script-src 'self'",
            "object-src 'none'",
            "frame-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
        ):
            with self.subTest(directive=directive):
                self.assertIn(directive, self.html)

        self.assertEqual([], self.parser.forbidden_tags)
        self.assertEqual([], self.parser.remote_attributes)
        self.assertEqual([], self.parser.static_buttons_without_disabled)
        self.assertEqual(2, len(self.parser.scripts))
        self.assertEqual("application/json", self.parser.scripts[0].get("type"))
        self.assertIsNone(self.parser.scripts[0].get("src"))
        self.assertEqual("adapter.js", self.parser.scripts[1].get("src"))

    def test_embedded_projection_is_exact_read_only_contract_shape(self) -> None:
        projection = self.projection
        self.assertEqual(
            {
                "schemaVersion",
                "scope",
                "snapshot",
                "page",
                "capabilities",
                "baseCandidateIds",
                "differences",
                "projectionSha256",
            },
            set(projection),
        )
        self.assertEqual("scoremosaic-teacher-review-projection-v1", projection["schemaVersion"])
        self.assertEqual(
            {
                "readOnly": True,
                "canEdit": False,
                "canApprove": False,
                "canPublish": False,
                "authoritativeTruth": False,
            },
            projection["capabilities"],
        )
        self.assertEqual(projection["page"]["returned"], len(projection["differences"]))
        self.assertLessEqual(len(projection["differences"]), 200)

    def test_embedded_projection_hash_is_deterministic_and_intact(self) -> None:
        payload = dict(self.projection)
        claimed = payload.pop("projectionSha256")
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertEqual(claimed, sha256(canonical).hexdigest())

    def test_projection_fixture_contains_no_server_only_or_source_artifact_fields(self) -> None:
        banned_keys = {
            "xmlPath",
            "sourceEventIndex",
            "source",
            "artifactRef",
            "artifactSha256",
            "signature",
            "allowedActions",
        }

        def walk(value: object) -> None:
            if isinstance(value, dict):
                self.assertTrue(banned_keys.isdisjoint(value.keys()))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.projection)

    def test_adapter_has_no_network_storage_navigation_or_html_injection_surface(self) -> None:
        forbidden_tokens = (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            "navigator.sendBeacon",
            "localStorage",
            "sessionStorage",
            "document.cookie",
            "window.location",
            "document.location",
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "eval(",
            "new Function",
        )
        for token in forbidden_tokens:
            with self.subTest(token=token):
                self.assertNotIn(token, self.javascript)

        self.assertIn("textContent", self.javascript)
        self.assertIn("createElement", self.javascript)
        self.assertIn("replaceChildren", self.javascript)

    def test_adapter_fails_closed_on_capability_expansion(self) -> None:
        for required_fragment in (
            'value.capabilities.readOnly === true',
            'value.capabilities.canEdit === false',
            'value.capabilities.canApprove === false',
            'value.capabilities.canPublish === false',
            'value.capabilities.authoritativeTruth === false',
            'document.body.dataset.reviewState = "rejected"',
        ):
            with self.subTest(required_fragment=required_fragment):
                self.assertIn(required_fragment, self.javascript)

    def test_issue_selection_is_keyboard_navigable_and_ui_only(self) -> None:
        for key in ("ArrowDown", "ArrowUp", "Home", "End"):
            with self.subTest(key=key):
                self.assertIn(f'event.key === "{key}"', self.javascript)
        self.assertIn('setAttribute("aria-selected"', self.javascript)
        self.assertIn('setAttribute("aria-activedescendant"', self.javascript)
        self.assertIn("event.preventDefault()", self.javascript)
        self.assertNotIn("ScoreEditCommand", self.javascript)
        self.assertNotIn("TeacherScoreRevision", self.javascript)

    def test_edit_approval_publication_and_playback_remain_disabled(self) -> None:
        for label in (
            "Apply correction",
            "Approve revision",
            "Publish",
            "Play",
            "Pause",
            "Stop",
            "Loop measure",
        ):
            with self.subTest(label=label):
                self.assertIn(label, self.html)
        self.assertIn("Mutation, approval and publication remain outside Stage 8-E authority.", self.html)
        self.assertIn("Read-only · no API · no writes · no playback", self.html)

    def test_local_css_loads_no_assets_or_imports(self) -> None:
        lowered = self.css.lower()
        self.assertNotIn("url(", lowered)
        self.assertNotIn("@import", lowered)


if __name__ == "__main__":
    unittest.main()
