from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "prototypes" / "stage8h-disconnected-edit-intent"
HTML_PATH = WORKSPACE / "index.html"
JS_PATH = WORKSPACE / "composer.js"
CSS_PATH = WORKSPACE / "composer.css"
SCHEMA_PATH = ROOT / "contracts" / "teacher-review-browser-edit-intent-v1.schema.json"


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.scripts: list[dict[str, str | None]] = []
        self.remote_attributes: list[tuple[str, str, str]] = []
        self.forbidden_tags: list[str] = []
        self.buttons: list[dict[str, str | None]] = []
        self._capture_projection = False
        self.projection_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value for key, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"] or "")
        if tag in {"form", "iframe", "object", "embed"}:
            self.forbidden_tags.append(tag)
        if tag == "button":
            self.buttons.append(values)
        if tag == "script":
            self.scripts.append(values)
            self._capture_projection = (
                values.get("id") == "scoremosaic-projection"
                and values.get("type") == "application/json"
            )
        for key in ("src", "href", "action"):
            value = values.get(key)
            if value and ("://" in value or value.lower().startswith("javascript:")):
                self.remote_attributes.append((tag, key, value))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._capture_projection = False

    def handle_data(self, data: str) -> None:
        if self._capture_projection:
            self.projection_chunks.append(data)


class Stage8HDisconnectedIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.javascript = JS_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.parser = _Parser()
        cls.parser.feed(cls.html)
        cls.projection = json.loads("".join(cls.parser.projection_chunks))

    def test_projection_remains_exact_read_only_and_hash_intact(self) -> None:
        projection = self.projection
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
        body = dict(projection)
        claimed = body.pop("projectionSha256")
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(claimed, sha256(canonical).hexdigest())

    def test_csp_and_static_surface_block_transport_authority(self) -> None:
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
            self.assertIn(directive, self.html)
        self.assertEqual([], self.parser.forbidden_tags)
        self.assertEqual([], self.parser.remote_attributes)
        self.assertEqual(2, len(self.parser.scripts))
        self.assertEqual("application/json", self.parser.scripts[0].get("type"))
        self.assertEqual("composer.js", self.parser.scripts[1].get("src"))

        forbidden_tokens = (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            "navigator.sendBeacon",
            "localStorage",
            "sessionStorage",
            "indexedDB",
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
        self.assertIn("replaceChildren", self.javascript)

    def test_only_local_prepare_and_clear_controls_can_be_enabled(self) -> None:
        button_by_id = {button.get("id"): button for button in self.parser.buttons if button.get("id")}
        self.assertIn("disabled", button_by_id["prepare-intent"])
        self.assertIn("disabled", button_by_id["clear-intent"])
        for label in ("Submit correction", "Approve revision", "Publish"):
            matching = [button for button in self.parser.buttons if False]
            self.assertIn(label, self.html)
        self.assertIn('<button type="button" disabled>Submit correction</button>', self.html)
        self.assertIn('<button type="button" disabled>Approve revision</button>', self.html)
        self.assertIn('<button type="button" disabled>Publish</button>', self.html)
        self.assertNotIn("submit_score_edit_request", self.javascript)
        self.assertNotIn("ScoreEditCommand", self.javascript)
        self.assertNotIn("TeacherScoreRevision", self.javascript)

    def test_composer_requires_read_only_projection_and_present_event(self) -> None:
        for fragment in (
            'value.capabilities.readOnly === true',
            'value.capabilities.canEdit === false',
            'value.capabilities.canApprove === false',
            'value.capabilities.canPublish === false',
            'value.capabilities.authoritativeTruth === false',
            'difference.focus.eventPresentInSnapshot',
            'requireCondition(difference.focus.eventPresentInSnapshot, "INTENT_TARGET_ABSENT")',
            'prepareIntentButton.disabled = !available',
        ):
            self.assertIn(fragment, self.javascript)
        self.assertFalse(self.projection["differences"][1]["focus"]["eventPresentInSnapshot"])

    def test_operation_vocabulary_is_exact_allowlist_and_bounded(self) -> None:
        match = re.search(r"const OPERATIONS = new Set\(\[(.*?)\]\);", self.javascript, re.DOTALL)
        self.assertIsNotNone(match)
        assert match is not None
        operations = set(re.findall(r'"([a-z_]+)"', match.group(1)))
        self.assertEqual(
            {
                "set_pitch",
                "set_effective_duration",
                "set_written_type",
                "set_dots",
                "set_staff_voice",
                "set_time_signature",
                "set_tab",
                "remove_event",
            },
            operations,
        )
        self.assertNotIn("raw_xml", self.javascript)
        self.assertNotIn("json_patch", self.javascript.lower())
        self.assertIn('input.maxLength = maximum', self.javascript)
        self.assertIn('Number.isSafeInteger(value)', self.javascript)

    def test_intent_contract_is_closed_non_authoritative_and_not_a_command(self) -> None:
        schema = self.schema
        self.assertFalse(schema["additionalProperties"])
        self.assertTrue(schema["$defs"])
        self.assertEqual(
            "score-edit-command-v1.schema.json#/$defs/operation",
            schema["properties"]["operation"]["$ref"],
        )
        authority = schema["$defs"]["authority"]
        self.assertFalse(authority["additionalProperties"])
        for name in (
            "authoritativeCapability",
            "serverAuthorizationIncluded",
            "oldValuePreconditionIncluded",
            "commandIdentityIncluded",
            "networkSubmissionAllowed",
        ):
            self.assertIs(False, authority["properties"][name]["const"])
        serialized = json.dumps(schema, sort_keys=True)
        for forbidden in (
            '"authorizationDecisionId"',
            '"oldValueSha256"',
            '"commandSha256"',
            '"commandId"',
            '"issueId"',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_generated_intent_marks_every_authority_dimension_false(self) -> None:
        for fragment in (
            "authoritativeCapability: false",
            "serverAuthorizationIncluded: false",
            "oldValuePreconditionIncluded: false",
            "commandIdentityIncluded: false",
            "networkSubmissionAllowed: false",
        ):
            self.assertIn(fragment, self.javascript)
        self.assertIn("projectionSha256: projection.projectionSha256", self.javascript)
        self.assertIn("differenceId: difference.differenceId", self.javascript)
        self.assertIn("stateSha256: projection.snapshot.stateSha256", self.javascript)

    def test_keyboard_accessibility_and_text_only_preview(self) -> None:
        required_ids = {
            "issue-list",
            "intent-panel",
            "operation-type",
            "value-fields",
            "reason",
            "prepare-intent",
            "clear-intent",
            "intent-preview",
        }
        self.assertTrue(required_ids.issubset(self.parser.ids))
        for key in ("ArrowDown", "ArrowUp", "Home", "End"):
            self.assertIn(f'event.key === "{key}"', self.javascript)
        self.assertIn('setAttribute("aria-selected"', self.javascript)
        self.assertIn('setAttribute("aria-activedescendant"', self.javascript)
        self.assertIn("event.preventDefault()", self.javascript)
        self.assertIn("intentPreview.textContent = stableStringify(intent)", self.javascript)
        self.assertIn('aria-live="polite"', self.html)

    def test_local_css_loads_no_external_assets(self) -> None:
        lowered = self.css.lower()
        self.assertNotIn("url(", lowered)
        self.assertNotIn("@import", lowered)


if __name__ == "__main__":
    unittest.main()
