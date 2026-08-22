from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "services" / "teacher-review-service" / "pyproject.toml"
SCHEMA = ROOT / "contracts" / "teacher-review-human-approval-handoff-v1.schema.json"
SOURCE = ROOT / "services" / "teacher-review-service" / "src" / "scoremosaic_teacher_review" / "approval_handoff.py"


class Stage8LActivationLockTests(unittest.TestCase):
    def test_handoff_foundation_does_not_enable_approval_publication_or_live_write(self) -> None:
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn("approval-handoff-foundation-enabled = true", text)
        self.assertIn("approval-enabled = false", text)
        self.assertIn("publication-enabled = false", text)
        self.assertIn("write-api-enabled = false", text)
        self.assertIn("public-api-enabled = false", text)
        self.assertIn("production-durable-store-enabled = false", text)

    def test_schema_requires_human_decision_and_forbids_recording_authority(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        requirements = schema["properties"]["requirements"]["properties"]
        capabilities = schema["properties"]["capabilities"]["properties"]
        state = schema["properties"]["state"]["properties"]
        self.assertTrue(requirements["humanDecisionRequired"]["const"])
        self.assertTrue(capabilities["canPresentForHumanApproval"]["const"])
        for key in ("canRecordApproval", "canPublish", "canMutate", "canWrite", "authoritativeTruth"):
            self.assertFalse(capabilities[key]["const"])
        self.assertEqual("awaiting_human_decision", state["status"]["const"])
        self.assertEqual("null", state["approvalDecision"]["type"])
        self.assertEqual("null", state["approvalRecordId"]["type"])
        self.assertEqual("null", state["publicationRecordId"]["type"])

    def test_handoff_module_is_repository_only_and_non_executing(self) -> None:
        source = SOURCE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastapi", "flask", "django", "starlette", "aiohttp",
            "socket", "subprocess", "os.system", "requests.", "urllib.",
            "sqlite3", "boto", "s3", "redis", "postgres", "sqlalchemy",
            "midi", "soundfont", "pyaudio", "sounddevice",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
