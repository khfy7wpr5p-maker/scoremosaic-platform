from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "services" / "teacher-review-service" / "pyproject.toml"
SCHEMA = ROOT / "contracts" / "teacher-review-human-approval-record-v1.schema.json"


class Stage8MActivationLockTests(unittest.TestCase):
    def test_approval_record_foundation_is_enabled_without_live_authority(self):
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn("human-approval-record-foundation-enabled = true", text)
        for locked in (
            "approval-enabled = false",
            "publication-enabled = false",
            "write-api-enabled = false",
            "public-api-enabled = false",
            "production-durable-store-enabled = false",
            "corrected-musicxml-materialization-enabled = false",
            "audio-playback-enabled = false",
        ):
            with self.subTest(locked=locked):
                self.assertIn(locked, text)

    def test_schema_is_closed_and_publication_remains_false(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual("scoremosaic-human-approval-record-v1", schema["properties"]["schemaVersion"]["const"])
        publication = schema["properties"]["publication"]
        self.assertFalse(publication["additionalProperties"])
        self.assertFalse(publication["properties"]["eligible"]["const"])
        self.assertFalse(publication["properties"]["granted"]["const"])
        caps = schema["properties"]["capabilities"]
        self.assertTrue(caps["properties"]["humanApprovalCaptured"]["const"])
        for key in ("canPublish", "canMutate", "canWrite", "productionPersistence", "authoritativeMusicalTruth"):
            self.assertFalse(caps["properties"][key]["const"])


if __name__ == "__main__":
    unittest.main()
