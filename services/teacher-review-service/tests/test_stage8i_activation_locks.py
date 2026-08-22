from __future__ import annotations

import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "services" / "teacher-review-service" / "pyproject.toml"
TIMELINE = (
    ROOT
    / "services"
    / "teacher-review-service"
    / "src"
    / "scoremosaic_teacher_review"
    / "review_timeline.py"
)
SCHEMA = ROOT / "contracts" / "teacher-review-timeline-v1.schema.json"


class Stage8ITimelineActivationLockTests(unittest.TestCase):
    def test_timeline_foundation_does_not_activate_live_authority(self):
        config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        project = config["project"]
        flags = config["tool"]["scoremosaic"]
        self.assertEqual([], project["dependencies"])
        self.assertTrue(flags["read-only-rational-timeline-foundation-enabled"])
        for name in (
            "write-api-enabled",
            "public-api-enabled",
            "approval-enabled",
            "publication-enabled",
            "corrected-musicxml-materialization-enabled",
            "production-durable-store-enabled",
        ):
            self.assertFalse(flags[name], name)

    def test_timeline_module_has_no_audio_network_or_mutation_framework(self):
        source = TIMELINE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastapi",
            "flask",
            "django",
            "starlette",
            "aiohttp",
            "requests.",
            "urllib.",
            "http.server",
            "socket.",
            "websocket",
            "midi",
            "soundfont",
            "audio",
            "subprocess",
            "os.system",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_schema_capabilities_remain_non_playing_and_non_mutating(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertTrue(schema["$defs"])
        caps = schema["$defs"]["capabilities"]["properties"]
        self.assertTrue(caps["readOnly"]["const"])
        self.assertTrue(caps["cursorNavigation"]["const"])
        self.assertTrue(caps["canSeek"]["const"])
        for name in (
            "canLoop",
            "canPlay",
            "canMutate",
            "canApprove",
            "canPublish",
            "authoritativeTruth",
        ):
            self.assertFalse(caps[name]["const"], name)

    def test_schema_excludes_stale_derived_observed_duration(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        measure = schema["$defs"]["measure"]
        self.assertNotIn("observedDuration", measure["required"])
        self.assertNotIn("observedDuration", measure["properties"])
        self.assertIn("eventExtentEnd", measure["required"])


if __name__ == "__main__":
    unittest.main()
