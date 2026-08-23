from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REQUEST = json.loads((ROOT / "contracts" / "stage11-read-request-v1.schema.json").read_text(encoding="utf-8"))
RESPONSE = json.loads((ROOT / "contracts" / "stage11-read-response-v1.schema.json").read_text(encoding="utf-8"))
ADAPTER = (ROOT / "prototypes" / "stage11-ui-application-contracts" / "read-adapter.js").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "stage11b-read-contracts-local-adapter.md").read_text(encoding="utf-8")


class Stage11BReadContractsLocalAdapterTests(unittest.TestCase):
    def test_request_schema_is_closed_and_exact(self) -> None:
        self.assertFalse(REQUEST["additionalProperties"])
        self.assertEqual(
            ["schemaVersion", "requestId", "kind", "documentId", "revision"],
            REQUEST["required"],
        )
        self.assertEqual(
            ["review.read", "issues.read", "sourceEvidence.read", "validation.read"],
            REQUEST["properties"]["kind"]["enum"],
        )

    def test_response_schema_is_closed_and_preserves_rejected_unknown_kind(self) -> None:
        self.assertFalse(RESPONSE["additionalProperties"])
        self.assertIn("unknown", RESPONSE["properties"]["kind"]["enum"])
        self.assertEqual(["success", "empty", "rejected", "unavailable"], RESPONSE["properties"]["state"]["enum"])
        self.assertIs(RESPONSE["$defs"]["validationData"]["properties"]["authoritative"]["const"], False)

    def test_adapter_is_explicitly_local_and_non_authoritative(self) -> None:
        for marker in (
            "productionAdapter: false",
            "authoritative: false",
            "networkCapable: false",
            "persistent: false",
        ):
            self.assertIn(marker, ADAPTER)

    def test_adapter_exactly_binds_document_revision_and_shape(self) -> None:
        for marker in (
            "REQUEST_SHAPE_INVALID",
            "DOCUMENT_MISMATCH",
            "REVISION_MISMATCH",
            "REQUEST_KIND_INVALID",
            "REQUIRED_KEYS",
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

    def test_validation_read_never_claims_authority(self) -> None:
        self.assertIn("authoritative: false", ADAPTER)
        self.assertIn("approvalEligible: fixture.validation.approvalEligible", ADAPTER)
        self.assertIn("publicationEligible: fixture.validation.publicationEligible", ADAPTER)

    def test_document_preserves_stage11c_boundary(self) -> None:
        self.assertIn("No network transport or production data source is activated", DOC)
        self.assertIn("Stage 11-C", DOC)
        self.assertIn("distinct from ScoreEditCommand creation", DOC)


if __name__ == "__main__":
    unittest.main()
