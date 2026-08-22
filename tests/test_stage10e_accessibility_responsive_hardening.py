from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototypes" / "stage10-ui-application-experience"
HTML = (PROTOTYPE / "index.html").read_text(encoding="utf-8")
APP = (PROTOTYPE / "app.js").read_text(encoding="utf-8")
CSS = (PROTOTYPE / "accessibility.css").read_text(encoding="utf-8")
BASE_CSS = (PROTOTYPE / "styles.css").read_text(encoding="utf-8")
README = (PROTOTYPE / "README.md").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "stage10e-accessibility-responsive-hardening.md").read_text(encoding="utf-8")


class Stage10EAccessibilityResponsiveHardeningTests(unittest.TestCase):
    def test_primary_score_view_has_skip_link_focus_target_and_fixture_description(self) -> None:
        self.assertIn('<a class="skip-link" href="#score-view">Skip to Score View</a>', HTML)
        self.assertRegex(HTML, r'<section id="score-view"[^>]*tabindex="-1"')
        self.assertIn('aria-describedby="score-authority-note"', HTML)
        self.assertIn('id="score-authority-note" class="sr-only"', HTML)

    def test_issue_list_exposes_keyboard_help_and_textual_status(self) -> None:
        self.assertIn('id="issue-keyboard-help" class="sr-only"', HTML)
        self.assertIn('aria-describedby="issue-keyboard-help"', HTML)
        self.assertRegex(HTML, r'id="issue-count"[^>]*role="status"[^>]*aria-live="polite"')
        self.assertIn("severity.textContent = issue.severity", APP)
        self.assertIn("button.setAttribute('aria-label'", APP)

    def test_issue_keyboard_navigation_is_bounded_and_local(self) -> None:
        for key in ("ArrowDown", "ArrowUp", "Home", "End"):
            self.assertIn(f"'{key}'", APP)
        self.assertIn("event.preventDefault()", APP)
        self.assertIn("selectIssue(visible[nextIndex].id, 'issue')", APP)
        self.assertIn("Math.min(currentIndex + 1, visible.length - 1)", APP)
        self.assertIn("Math.max(currentIndex - 1, 0)", APP)

    def test_edit_controls_are_programmatically_labeled_and_described(self) -> None:
        for field_id in ("edit-operation", "edit-value", "edit-reason"):
            self.assertIn(f'for="{field_id}"', HTML)
            self.assertRegex(HTML, rf'id="{field_id}"[^>]*aria-describedby="edit-intent-help"')
        self.assertIn('id="edit-intent-help" class="sr-only"', HTML)
        self.assertRegex(HTML, r'id="intent-status"[^>]*role="status"[^>]*aria-live="polite"')
        self.assertRegex(HTML, r'id="intent-preview"[^>]*role="status"[^>]*aria-live="polite"')

    def test_touch_long_identifier_and_focus_hardening_exist(self) -> None:
        self.assertIn("min-height: 44px", CSS)
        self.assertIn("overflow-wrap: anywhere", CSS)
        self.assertIn(".issue-button:focus-visible", CSS)
        self.assertIn("#score-view:focus-visible", CSS)
        self.assertIn(".sr-only", CSS)

    def test_contrast_forced_colors_and_reduced_motion_are_supported(self) -> None:
        self.assertIn("@media (prefers-contrast: more)", CSS)
        self.assertIn("@media (forced-colors: active)", CSS)
        self.assertIn("forced-color-adjust", CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", BASE_CSS)

    def test_narrow_layout_preserves_score_view_priority(self) -> None:
        self.assertIn("@media (max-width: 520px)", CSS)
        self.assertIn("@media (max-width: 760px)", BASE_CSS)
        self.assertIn(".score-panel { order: 1; }", BASE_CSS)
        self.assertIn("Score View remains the first application workspace on narrow layouts.", README)

    def test_accessibility_changes_do_not_add_runtime_authority(self) -> None:
        combined = APP + "\n" + CSS
        banned_patterns = {
            "fetch": r"\bfetch\s*\(",
            "xhr": r"XMLHttpRequest",
            "websocket": r"WebSocket",
            "eventsource": r"EventSource",
            "localStorage": r"localStorage",
            "sessionStorage": r"sessionStorage",
            "indexedDB": r"indexedDB",
            "cookie": r"document\.cookie",
            "clipboard": r"navigator\.clipboard",
            "download": r"\.download\s*=",
            "windowLocation": r"\bwindow\.location\b",
            "documentLocation": r"\bdocument\.location\b",
            "innerHTML": r"innerHTML",
            "eval": r"\beval\s*\(",
        }
        for name, pattern in banned_patterns.items():
            self.assertIsNone(re.search(pattern, combined), name)
        for marker in (
            "no Teacher Review server write",
            "no ScoreEditCommand",
            "no TeacherScoreRevision",
            "no approval execution",
            "no publication execution",
            "no playback",
            "no production infrastructure",
        ):
            self.assertIn(marker, DOC)


if __name__ == "__main__":
    unittest.main()
