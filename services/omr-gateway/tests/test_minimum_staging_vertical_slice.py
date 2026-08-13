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

    def test_slice_is_staging_only_and_does_not_activate_http_or_dispatch_authority(self) -> None:
        object.__setattr__(self.admission, "environment", "production")

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_environment_required")
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
