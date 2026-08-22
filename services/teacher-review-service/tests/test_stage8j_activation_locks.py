from __future__ import annotations

import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "services" / "teacher-review-service" / "pyproject.toml"
PLAN_SCHEMA = ROOT / "contracts" / "teacher-review-transport-plan-v1.schema.json"
STATE_SCHEMA = ROOT / "contracts" / "teacher-review-transport-state-v1.schema.json"
MODULE = (
    ROOT
    / "services"
    / "teacher-review-service"
    / "src"
    / "scoremosaic_teacher_review"
    / "review_transport.py"
)


class Stage8JTransportActivationLockTests(unittest.TestCase):
    def test_foundation_flag_does_not_enable_audio_or_live_authority(self):
        config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        project = config["project"]
        flags = config["tool"]["scoremosaic"]
        self.assertEqual([], project["dependencies"])
        self.assertTrue(flags["transport-state-machine-foundation-enabled"])
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

    def test_plan_and_state_schemas_are_closed_and_execution_locked(self):
        plan = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
        state = json.loads(STATE_SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(plan["additionalProperties"])
        self.assertFalse(state["additionalProperties"])
        self.assertTrue(plan["$defs"])
        self.assertTrue(state["$defs"])
        plan_caps = plan["$defs"]["capabilities"]["properties"]
        self.assertTrue(plan_caps["presentationOnly"]["const"])
        for name in (
            "loopExecutionAllowed",
            "audioExecutionAllowed",
            "mutationAllowed",
            "approvalAllowed",
            "publicationAllowed",
        ):
            self.assertFalse(plan_caps[name]["const"], name)
        for name in (
            "executionAllowed",
            "audioEmissionAllowed",
            "loopExecutionAllowed",
            "mutationAllowed",
            "approvalAllowed",
            "publicationAllowed",
        ):
            self.assertFalse(state["properties"][name]["const"], name)

    def test_transport_module_has_no_live_runtime_dependencies(self):
        source = MODULE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastapi", "flask", "django", "starlette", "aiohttp",
            "requests.", "urllib.", "http.server", "socket.", "websocket",
            "subprocess", "os.system", "midi", "soundfont", "pyaudio",
            "sounddevice", "time.sleep", "perf_counter", "monotonic(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
