from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError,
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


class MinimumStagingVerticalSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.provider = StagingUploadProvider(Path(self.temp_dir.name))

    def run_slice(self, *, payload=helpers.PNG_1X1, filename="scan.png", media_type="image/png"):
        return run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.fixture.session_policy,
            payload=payload,
            original_filename=filename,
            declared_media_type=media_type,
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=self.provider,
        )

    def test_exact_document_runs_e4a_e4b_e4c_and_writes_one_immutable_source(self) -> None:
        result = self.run_slice()

        self.assertFalse(result.session.replayed)
        self.assertFalse(result.finalization.replayed)
        self.assertEqual(result.source_write_state, "written")
        self.assertEqual(result.binding.document_sha256, result.finalization.document_sha256)
        self.assertEqual(result.binding.job_id, result.job_id)
        self.assertEqual(result.binding.source_artifact_id, result.source_artifact_id)
        self.assertEqual(
            self.provider.read_source(result.binding),
            helpers.PNG_1X1,
        )
        self.assertFalse(result.network_dispatch_allowed)
        self.assertFalse(result.orchestration_allowed)

    def test_exact_replay_reuses_session_finalization_job_and_source_without_overwrite(self) -> None:
        first = self.run_slice()
        replay = self.run_slice()

        self.assertTrue(replay.session.replayed)
        self.assertTrue(replay.finalization.replayed)
        self.assertEqual(replay.source_write_state, "replay")
        self.assertEqual(replay.job_id, first.job_id)
        self.assertEqual(replay.source_artifact_id, first.source_artifact_id)
        self.assertEqual(
            self.provider.read_source(replay.binding),
            helpers.PNG_1X1,
        )

    def test_same_session_with_different_document_fails_closed_and_preserves_original(self) -> None:
        first = self.run_slice()

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice(
                payload=helpers.JPEG_1X1,
                filename="scan.jpg",
                media_type="image/jpeg",
            )
        self.assertEqual(raised.exception.category, "staging_upload_finalization_conflict")
        self.assertEqual(self.provider.read_source(first.binding), helpers.PNG_1X1)

    def test_provider_rejects_payload_that_does_not_match_verified_binding(self) -> None:
        result = self.run_slice()

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.provider.write_source(
                binding=result.binding,
                finalization=result.finalization,
                payload=helpers.JPEG_1X1,
            )
        self.assertEqual(raised.exception.category, "staging_source_payload_mismatch")
        self.assertEqual(self.provider.read_source(result.binding), helpers.PNG_1X1)

    def test_corrupt_persisted_session_fails_closed_without_touching_source(self) -> None:
        first = self.run_slice()
        session_path = (
            Path(self.temp_dir.name)
            / "state"
            / "sessions"
            / f"{first.session.session_id}.json"
        )
        session_path.write_text("{}", encoding="utf-8")

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_upload_session_failed")
        self.assertEqual(self.provider.read_source(first.binding), helpers.PNG_1X1)

    def test_preexisting_symlink_state_directory_cannot_escape_staging_root(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        root = Path(self.temp_dir.name)
        (root / "state").symlink_to(Path(outside.name), target_is_directory=True)

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_upload_session_failed")
        self.assertEqual(list(Path(outside.name).rglob("*")), [])

    def test_existing_tampered_source_is_never_overwritten_on_replay(self) -> None:
        first = self.run_slice()
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / Path(first.binding.source_storage_key)
        )
        tampered = b"X" * len(helpers.PNG_1X1)
        source_path.write_bytes(tampered)

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_source_collision")
        self.assertEqual(source_path.read_bytes(), tampered)

    def test_slice_is_staging_only_and_does_not_activate_http_or_dispatch_authority(self) -> None:
        object.__setattr__(self.admission, "environment", "production")

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_environment_required")
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
