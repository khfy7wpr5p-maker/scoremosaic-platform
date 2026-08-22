from __future__ import annotations

import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "services" / "teacher-review-service" / "pyproject.toml"
WRITE_MODULE = (
    ROOT
    / "services"
    / "teacher-review-service"
    / "src"
    / "scoremosaic_teacher_review"
    / "write_boundary.py"
)
REQUEST_SCHEMA = ROOT / "contracts" / "teacher-review-write-request-v1.schema.json"


class Stage8GActivationLockTests(unittest.TestCase):
    def test_foundation_flag_does_not_activate_live_authority(self):
        config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        project = config["project"]
        flags = config["tool"]["scoremosaic"]
        self.assertEqual([], project["dependencies"])
        self.assertTrue(flags["server-write-boundary-foundation-enabled"])
        for name in (
            "write-api-enabled",
            "public-api-enabled",
            "approval-enabled",
            "publication-enabled",
            "corrected-musicxml-materialization-enabled",
            "production-durable-store-enabled",
        ):
            self.assertFalse(flags[name], name)

    def test_write_module_registers_no_network_or_framework_surface(self):
        source = WRITE_MODULE.read_text(encoding="utf-8")
        lowered = source.lower()
        for forbidden in (
            "fastapi",
            "flask",
            "django",
            "starlette",
            "aiohttp",
            "requests.",
            "urllib.",
            "http.server",
            "@app.",
            "@router.",
            "socket.",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_request_schema_is_closed_and_reuses_score_edit_command(self):
        schema = json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            ["schemaVersion", "command", "requestSha256"],
            schema["required"],
        )
        self.assertEqual(
            "scoremosaic-teacher-review-write-request-v1",
            schema["properties"]["schemaVersion"]["const"],
        )
        self.assertEqual(
            "score-edit-command-v1.schema.json",
            schema["properties"]["command"]["$ref"],
        )
        self.assertEqual(
            "^[0-9a-f]{64}$",
            schema["properties"]["requestSha256"]["pattern"],
        )


if __name__ == "__main__":
    unittest.main()
