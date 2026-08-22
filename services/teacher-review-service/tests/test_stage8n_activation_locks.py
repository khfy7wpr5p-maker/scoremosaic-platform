from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "services" / "teacher-review-service" / "pyproject.toml"
SCHEMA = ROOT / "contracts" / "teacher-review-publication-eligibility-v1.schema.json"


class Stage8NActivationLockTests(unittest.TestCase):
    def test_publication_eligibility_foundation_does_not_activate_publication(self):
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn("publication-eligibility-foundation-enabled = true", text)
        for locked in (
            "publication-enabled = false",
            "approval-enabled = false",
            "write-api-enabled = false",
            "public-api-enabled = false",
            "production-durable-store-enabled = false",
        ):
            with self.subTest(locked=locked):
                self.assertIn(locked, text)

    def test_schema_distinguishes_handoff_candidate_from_production_publication(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        eligibility = schema["properties"]["eligibility"]["properties"]
        self.assertTrue(eligibility["candidateEligibleForPublicationHandoff"]["const"])
        self.assertFalse(eligibility["productionPublicationEligible"]["const"])
        authority = schema["properties"]["authority"]["properties"]
        for key in (
            "publicationGranted", "publisherAuthority", "writeGranted", "mutationGranted",
            "productionPersistence", "authoritativeMusicalTruth",
        ):
            self.assertFalse(authority[key]["const"])


if __name__ == "__main__":
    unittest.main()
