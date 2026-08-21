from __future__ import annotations

import json
from pathlib import Path
import tomllib
import unittest

TEST_FILE = Path(__file__).resolve()
REPO_ROOT = TEST_FILE.parents[3]


class Stage7AcceptanceContractTests(unittest.TestCase):
    def test_candidate_safety_policy_is_identical_across_all_three_engines(self) -> None:
        paths = (
            REPO_ROOT / "services/audiveris-service/src/scoremosaic_audiveris/candidate_safety.py",
            REPO_ROOT / "services/homr-service/src/scoremosaic_homr/candidate_safety.py",
            REPO_ROOT / "services/clarity-service/src/scoremosaic_clarity/candidate_safety.py",
        )
        documents = tuple(path.read_bytes() for path in paths)
        self.assertTrue(all(document == documents[0] for document in documents[1:]))
        policy = documents[0].decode("utf-8")
        required_markers = (
            'POLICY_VERSION = "candidate-safety-v1"',
            "MAX_ARTIFACT_BYTES = 128 * 1024 * 1024",
            "MAX_XML_BYTES = 64 * 1024 * 1024",
            "MAX_ZIP_ENTRIES = 128",
            "MAX_XML_DEPTH = 64",
            "MAX_XML_ELEMENTS = 500_000",
            "MAX_COMPRESSION_RATIO = 200",
            "def validate_musicxml_bytes(document: bytes)",
            "def validate_musicxml_file(path: Path)",
            "def validate_mxl_file(path: Path)",
            'CandidateSafetyError("musicxml_invalid_xml")',
        )
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, policy)

    def test_stage7_decision_boundaries_remain_locked(self) -> None:
        config = tomllib.loads(
            (REPO_ROOT / "services/ensemble-service/pyproject.toml").read_text(
                encoding="utf-8"
            )
        )["tool"]["scoremosaic"]
        for key in (
            "comparison-enabled",
            "evaluation-runtime-enabled",
            "aggregate-score-enabled",
            "general-accuracy-claim-enabled",
            "engine-ranking-enabled",
            "winner-selection-enabled",
            "automatic-merge-enabled",
            "automatic-correction-enabled",
            "teacher-approval-enabled",
            "public-api-enabled",
        ):
            with self.subTest(key=key):
                self.assertIs(config[key], False)

    def test_ui_readiness_contract_is_closed_and_keeps_live_backend_locked(self) -> None:
        path = REPO_ROOT / "contracts/stage7-ui-readiness.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(payload),
            {
                "version",
                "stage",
                "status",
                "contractReadiness",
                "liveBackendReadiness",
                "safeUiStartMode",
                "backendWorkRemaining",
                "stage8TeacherReviewContractsRequired",
                "lockedFeatures",
            },
        )
        self.assertEqual(payload["version"], "scoremosaic-ui-readiness-v1")
        self.assertEqual(payload["stage"], 7)
        self.assertEqual(payload["status"], "UI_READY_WITH_LOCKED_FEATURES")
        self.assertEqual(payload["safeUiStartMode"], "contract-first-mock-read-only")
        self.assertTrue(all(payload["contractReadiness"].values()))
        self.assertFalse(any(payload["liveBackendReadiness"].values()))
        self.assertIn("winner selection", payload["lockedFeatures"])
        self.assertIn("writable review UI", payload["lockedFeatures"])
        self.assertGreaterEqual(len(payload["stage8TeacherReviewContractsRequired"]), 7)

    def test_current_architecture_addendum_preserves_runtime_truth(self) -> None:
        document = (
            REPO_ROOT / "docs/architecture-stage5-7-current.md"
        ).read_text(encoding="utf-8")
        for required in (
            "authoritative current-activation addendum for Stage 5-7",
            "Engine/AI output is evidence",
            "Stage 5 is complete at controlled-staging/integration level",
            "Stage 6 is complete at authenticated ingestion/persistence integration level",
            "Stage 7 convergence is complete at repository contract/hermetic-integration level",
            "does **not** prove live HOMR/Clarity/Audiveris production model execution",
            "UI_READY_WITH_LOCKED_FEATURES",
            "TeacherScoreRevision",
        ):
            with self.subTest(required=required):
                self.assertIn(required, document)


if __name__ == "__main__":
    unittest.main()
