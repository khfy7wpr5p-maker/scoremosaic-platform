from __future__ import annotations

import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "services" / "teacher-review-service" / "pyproject.toml"
SCHEMA = ROOT / "contracts" / "teacher-review-approval-eligibility-v1.schema.json"
MODULE = (
    ROOT
    / "services"
    / "teacher-review-service"
    / "src"
    / "scoremosaic_teacher_review"
    / "approval_eligibility.py"
)


class Stage8KApprovalEligibilityActivationLockTests(unittest.TestCase):
    def test_eligibility_foundation_does_not_enable_approval_or_publication(self):
        config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        project = config["project"]
        flags = config["tool"]["scoremosaic"]
        self.assertEqual([], project["dependencies"])
        self.assertTrue(flags["approval-eligibility-foundation-enabled"])
        for name in (
            "audio-playback-enabled",
            "write-api-enabled",
            "public-api-enabled",
            "approval-enabled",
            "publication-enabled",
            "corrected-musicxml-materialization-enabled",
            "production-durable-store-enabled",
        ):
            self.assertFalse(flags[name], name)

    def test_schema_is_closed_and_authority_is_fixed_false(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertTrue(schema["$defs"])
        authority = schema["$defs"]["authority"]
        self.assertFalse(authority["additionalProperties"])
        for name in (
            "approvalGranted",
            "publicationGranted",
            "mutationGranted",
            "writeGranted",
            "authoritativeTruth",
        ):
            self.assertFalse(authority["properties"][name]["const"], name)

    def test_eligibility_module_has_no_live_transport_or_execution_runtime(self):
        source = MODULE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastapi", "flask", "django", "starlette", "aiohttp",
            "requests.", "urllib.", "http.server", "socket.", "websocket",
            "subprocess", "os.system", "midi", "soundfont", "pyaudio",
            "sounddevice", "time.sleep", "perf_counter", "monotonic(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertNotIn("approvalgranted\": true", source)
        self.assertNotIn("publicationgranted\": true", source)


if __name__ == "__main__":
    unittest.main()
