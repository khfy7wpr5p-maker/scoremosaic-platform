from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "services" / "teacher-review-service" / "pyproject.toml"
SCHEMA = ROOT / "contracts" / "teacher-review-publication-handoff-v1.schema.json"
MODULE = ROOT / "services" / "teacher-review-service" / "src" / "scoremosaic_teacher_review" / "publication_handoff.py"


class Stage8OActivationLockTests(unittest.TestCase):
    def test_handoff_foundation_does_not_activate_publication(self):
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn("publication-handoff-foundation-enabled = true", text)
        for locked in (
            "publication-enabled = false",
            "write-api-enabled = false",
            "public-api-enabled = false",
            "production-durable-store-enabled = false",
        ):
            with self.subTest(locked=locked):
                self.assertIn(locked, text)

    def test_schema_allows_presentation_but_forbids_execution(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        caps = schema["properties"]["capabilities"]["properties"]
        self.assertTrue(caps["canPresentForPublicationExecution"]["const"])
        for key in ("canExecutePublication", "canWriteExternal", "canPersistProduction", "canMutate", "publicationGranted", "authoritativeMusicalTruth"):
            self.assertFalse(caps[key]["const"])
        self.assertFalse(schema["properties"]["authorization"]["properties"]["productionPublicationAuthority"]["const"])

    def test_module_has_no_live_transport_or_storage_dependencies(self):
        source = MODULE.read_text(encoding="utf-8").lower()
        for forbidden in ("fastapi", "flask", "requests.", "urllib.", "socket.", "subprocess", "sqlite3", "psycopg", "boto3", "redis"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
