from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REQUEST = json.loads((ROOT / "contracts" / "stage11-edit-intent-request-v1.schema.json").read_text(encoding="utf-8"))
RESPONSE = json.loads((ROOT / "contracts" / "stage11-edit-intent-response-v1.schema.json").read_text(encoding="utf-8"))
ADAPTER = (ROOT / "prototypes" / "stage11-ui-application-contracts" / "edit-intent-adapter.js").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "stage11c-edit-intent-contract-local-adapter.md").read_text(encoding="utf-8")


class Stage11CEditIntentContractLocalAdapterTests(unittest.TestCase):
    def test_request_schema_is_closed_and_bound(self) -> None:
        self.assertFalse(REQUEST["additionalProperties"])
        self.assertEqual("editIntent.prepare", REQUEST["properties"]["kind"]["const"])
        self.assertTrue(REQUEST["$defs"])
        authority = REQUEST["$defs"]["authority"]["properties"]
        for name in (
            "authoritativeCapability",
            "serverAuthorizationIncluded",
            "oldValuePreconditionIncluded",
            "commandIdentityIncluded",
            "networkSubmissionAllowed",
        ):
            self.assertIs(authority[name]["const"], False)

    def test_operation_subset_reuses_canonical_score_edit_definitions(self) -> None:
        refs = [entry["$ref"] for entry in REQUEST["$defs"]["operation"]["oneOf"]]
        self.assertEqual(
            [
                "score-edit-command-v1.schema.json#/$defs/setPitch",
                "score-edit-command-v1.schema.json#/$defs/setEffectiveDuration",
                "score-edit-command-v1.schema.json#/$defs/setDots",
                "score-edit-command-v1.schema.json#/$defs/removeEvent",
            ],
            refs,
        )

    def test_response_local_intent_explicitly_denies_authority(self) -> None:
        authority = RESPONSE["$defs"]["authority"]["properties"]
        for name in (
            "authoritativeCapability",
            "serverAuthorizationIncluded",
            "oldValuePreconditionIncluded",
            "commandIdentityIncluded",
            "networkSubmissionAllowed",
            "canCreateScoreEditCommand",
            "canCreateRevision",
            "canApprove",
            "canPublish",
        ):
            self.assertIs(authority[name]["const"], False)

    def test_adapter_rejects_stale_target_operation_and_authority_claims(self) -> None:
        for marker in (
            "REVISION_MISMATCH",
            "ISSUE_NOT_FOUND",
            "TARGET_MISMATCH",
            "OPERATION_INVALID",
            "AUTHORITY_INVALID",
        ):
            self.assertIn(marker, ADAPTER)

    def test_adapter_contains_no_live_transport_or_persistence_apis(self) -> None:
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
                self.assertIsNone(re.search(pattern, ADAPTER))

    def test_adapter_never_manufactures_server_proof_fields(self) -> None:
        for forbidden_property in (
            "authorizationDecisionId:",
            "oldValueSha256:",
            "commandSha256:",
            "commandId:",
            "teacherScoreRevisionId:",
            "approvalRecordId:",
            "publicationRecordId:",
        ):
            self.assertNotIn(forbidden_property, ADAPTER)

    def test_document_preserves_stage11d_boundary(self) -> None:
        self.assertIn("Local intent preparation only", DOC)
        self.assertIn("A local intent is evidence of user intent only", DOC)
        self.assertIn("Stage 11-D", DOC)
        self.assertIn("Live networking remains disabled", DOC)


if __name__ == "__main__":
    unittest.main()
