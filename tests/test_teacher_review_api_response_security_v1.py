from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REVISION_RESULT = json.loads(
    (ROOT / "contracts" / "teacher-review-api-revision-result-v1.schema.json").read_text(encoding="utf-8")
)
READ_RESULT = json.loads(
    (ROOT / "contracts" / "teacher-review-api-read-result-v1.schema.json").read_text(encoding="utf-8")
)


class TeacherReviewApiResponseSecurityV1Tests(unittest.TestCase):
    def test_success_parent_lineage_is_explicit_base_or_revision_branch(self) -> None:
        parent = REVISION_RESULT["$defs"]["parent"]
        self.assertEqual(
            {"#/$defs/baseParent", "#/$defs/revisionParent"},
            {entry["$ref"] for entry in parent["oneOf"]},
        )

        base = REVISION_RESULT["$defs"]["baseParent"]
        self.assertEqual("null", base["properties"]["revisionId"]["type"])
        self.assertEqual("null", base["properties"]["revisionSha256"]["type"])
        self.assertEqual("#/$defs/sha256", base["properties"]["stateSha256"]["$ref"])

        revision = REVISION_RESULT["$defs"]["revisionParent"]
        self.assertEqual("^rev_[0-9a-f]{32}$", revision["properties"]["revisionId"]["pattern"])
        self.assertEqual("#/$defs/sha256", revision["properties"]["revisionSha256"]["$ref"])
        self.assertEqual("#/$defs/sha256", revision["properties"]["stateSha256"]["$ref"])

    def test_revision_error_states_expose_no_parsed_or_resolved_identity(self) -> None:
        rule = next(
            entry
            for entry in REVISION_RESULT["allOf"]
            if set(entry["if"]["properties"]["state"].get("enum", []))
            == {"rejected", "stale", "conflict", "unavailable"}
        )
        for field in ("requestId", "documentId", "parent", "revision"):
            self.assertEqual("null", rule["then"]["properties"][field]["type"])

    def test_read_error_states_expose_no_resolved_document_revision_or_data(self) -> None:
        rule = next(
            entry
            for entry in READ_RESULT["allOf"]
            if set(entry["if"]["properties"]["state"].get("enum", []))
            == {"rejected", "unavailable"}
        )
        for field in ("documentId", "revisionId", "data"):
            self.assertEqual("null", rule["then"]["properties"][field]["type"])


if __name__ == "__main__":
    unittest.main()
