from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts" / "stage11-ui-application-state-v1.schema.json").read_text(encoding="utf-8"))
REDUCER = (ROOT / "prototypes" / "stage11-ui-application-contracts" / "application-state.js").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "stage11d-application-state-error-model.md").read_text(encoding="utf-8")


class Stage11DApplicationStateErrorModelTests(unittest.TestCase):
    def test_state_schema_is_closed_and_phase_bounded(self) -> None:
        self.assertFalse(SCHEMA["additionalProperties"])
        self.assertEqual(
            ["idle", "loading", "ready", "empty", "rejected", "unavailable"],
            SCHEMA["properties"]["phase"]["enum"],
        )
        self.assertTrue(SCHEMA["$defs"])

    def test_state_schema_never_grants_authority(self) -> None:
        authority = SCHEMA["$defs"]["authority"]["properties"]
        for name in ("authoritative", "canWrite", "canApprove", "canPublish", "canPlayback"):
            self.assertIs(authority[name]["const"], False)

    def test_error_categories_are_closed(self) -> None:
        self.assertEqual(
            ["invalid_request", "stale_context", "not_found", "protocol", "unavailable", "unknown"],
            SCHEMA["$defs"]["error"]["properties"]["category"]["enum"],
        )

    def test_reducer_requires_exact_response_correlation(self) -> None:
        for marker in (
            "RESPONSE_SCHEMA_MISMATCH",
            "RESPONSE_REQUEST_ID_MISMATCH",
            "RESPONSE_KIND_MISMATCH",
            "RESPONSE_DOCUMENT_MISMATCH",
            "RESPONSE_REVISION_MISMATCH",
            "RESPONSE_STATE_INVALID",
        ):
            self.assertIn(marker, REDUCER)

    def test_success_empty_and_error_invariants_are_explicit(self) -> None:
        for marker in (
            "RESPONSE_SUCCESS_INVALID",
            "RESPONSE_EMPTY_INVALID",
            "RESPONSE_ERROR_INVALID",
        ):
            self.assertIn(marker, REDUCER)

    def test_reducer_has_no_live_transport_or_persistence_apis(self) -> None:
        banned = {
            "fetch": r"\bfetch\s*\(",
            "xhr": r"XMLHttpRequest",
            "websocket": r"WebSocket",
            "eventsource": r"EventSource",
            "localStorage": r"localStorage",
            "sessionStorage": r"sessionStorage",
            "indexedDB": r"indexedDB",
            "cookie": r"document\.cookie",
            "clipboard": r"navigator\.clipboard",
            "navigation": r"\b(?:window|document)\.location\b",
            "innerHTML": r"innerHTML",
            "eval": r"\beval\s*\(",
            "Function": r"new\s+Function",
        }
        for name, pattern in banned.items():
            with self.subTest(api=name):
                self.assertIsNone(re.search(pattern, REDUCER))

    def test_document_preserves_stage11e_disconnected_boundary(self) -> None:
        self.assertIn("Pure local state reduction only", DOC)
        self.assertIn("A mismatched response is never silently rendered", DOC)
        self.assertIn("Stage 11-E", DOC)
        self.assertIn("live API/auth/server-write activation stays locked", DOC)


if __name__ == "__main__":
    unittest.main()
