from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototypes" / "stage10-ui-application-experience"
HTML = (PROTOTYPE / "index.html").read_text(encoding="utf-8")
SCRIPT = (PROTOTYPE / "edit-intent.js").read_text(encoding="utf-8")
README = (PROTOTYPE / "README.md").read_text(encoding="utf-8")


class Stage10DDisconnectedEditIntentUxTests(unittest.TestCase):
    def test_closed_operation_subset_matches_existing_stage8h_vocabulary(self) -> None:
        for operation in (
            "set_pitch",
            "set_effective_duration",
            "set_dots",
            "remove_event",
        ):
            self.assertIn(f"'{operation}'", SCRIPT)
            self.assertIn(f'value="{operation}"', HTML)
        for forbidden in (
            "freeform_operation",
            "raw_musicxml",
            "execute_command",
        ):
            self.assertNotIn(forbidden, SCRIPT.lower())

    def test_local_intent_explicitly_denies_server_authority(self) -> None:
        for marker in (
            "authoritativeCapability: false",
            "serverAuthorizationIncluded: false",
            "oldValuePreconditionIncluded: false",
            "commandIdentityIncluded: false",
            "networkSubmissionAllowed: false",
            "canCreateScoreEditCommand: false",
            "canCreateRevision: false",
            "canApprove: false",
            "canPublish: false",
        ):
            self.assertIn(marker, SCRIPT)

    def test_local_intent_does_not_manufacture_server_proof_fields(self) -> None:
        forbidden_property_names = (
            "oldValueSha256",
            "authorizationGrant",
            "commandSha256",
            "commandId",
            "teacherScoreRevisionId",
            "approvalRecordId",
            "publicationRecordId",
        )
        for field in forbidden_property_names:
            pattern = rf"(?:\b{re.escape(field)}\s*:|['\"]{re.escape(field)}['\"]\s*:)"
            self.assertIsNone(re.search(pattern, SCRIPT), field)

    def test_input_domains_are_bounded(self) -> None:
        self.assertIn("PITCH_RE", SCRIPT)
        self.assertIn("DURATION_RE", SCRIPT)
        self.assertIn("octave < -2 || octave > 12", SCRIPT)
        self.assertIn("dots < 0 || dots > 8", SCRIPT)
        self.assertIn("note.length > 300", SCRIPT)
        self.assertIn('maxlength="300"', HTML)

    def test_preview_is_text_only_and_never_submitted(self) -> None:
        self.assertIn("preview.textContent = JSON.stringify(intent, null, 2)", SCRIPT)
        self.assertIn('id="intent-preview"', HTML)
        self.assertIn('aria-live="polite"', HTML)
        self.assertNotIn("innerHTML", SCRIPT)
        self.assertNotIn("insertAdjacentHTML", SCRIPT)

    def test_script_has_no_network_persistence_clipboard_download_or_navigation_authority(self) -> None:
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
            "blobUrl": r"URL\.createObjectURL",
            "download": r"\.download\s*=",
            "windowLocation": r"\bwindow\.location\b",
            "documentLocation": r"\bdocument\.location\b",
            "eval": r"\beval\s*\(",
            "Function": r"new\s+Function",
        }
        for name, pattern in banned_patterns.items():
            self.assertIsNone(re.search(pattern, SCRIPT), name)

    def test_html_keeps_local_action_separate_from_authority_controls(self) -> None:
        self.assertIn('id="prepare-intent"', HTML)
        self.assertIn('data-local-action="prepare-intent"', HTML)
        self.assertIn('id="clear-intent"', HTML)
        for label in ("Play", "Pause", "Stop", "Loop measure"):
            self.assertRegex(HTML, rf'<button type="button" disabled>{re.escape(label)}</button>')
        self.assertIn("Approval</strong> unavailable", HTML)

    def test_readme_states_disconnected_non_authoritative_boundary(self) -> None:
        for marker in (
            "bounded disconnected edit-intent draft",
            "no server authority",
            "It cannot contain or create a server authorization, old-value precondition, command identity, ScoreEditCommand, TeacherScoreRevision, approval, or publication.",
            "not submitted, downloaded, copied to persistent storage, or sent over a network",
        ):
            self.assertIn(marker, README)


if __name__ == "__main__":
    unittest.main()
