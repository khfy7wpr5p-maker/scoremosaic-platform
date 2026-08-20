from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    ControlledStagingJobLifecycleError,
    recover_controlled_staging_job_lifecycle,
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
)
from scoremosaic_gateway.controlled_staging_terminal_cancellation import (
    ControlledStagingTerminalCancellationError,
    cancel_controlled_staging_queued_run,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


class ControlledStagingTerminalCancellationRecoveryGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.provider = StagingUploadProvider(
            self.root,
            state_integrity_key=b"G" * 32,
        )
        self.minimum_slice = run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.fixture.session_policy,
            payload=helpers.PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=self.provider,
        )
        run_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
        )

    def test_revision_two_alone_still_supersedes_planned_job_recovery(self) -> None:
        queued = queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )
        cancel_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )

        revision_one = (
            self.root
            / "state"
            / "job_transitions"
            / queued.job_id
            / f"{queued.run_id}-revision-1.json"
        )
        revision_two = revision_one.with_name(f"{queued.run_id}-revision-2.json")
        self.assertTrue(revision_one.exists())
        self.assertTrue(revision_two.exists())
        revision_one.chmod(0o600)
        revision_one.unlink()

        with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
            recover_controlled_staging_job_lifecycle(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
            )
        self.assertEqual(
            raised.exception.category,
            "staging_job_recovery_superseded",
        )

    def test_corrupt_initial_record_is_normalized_to_cancellation_error(self) -> None:
        queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )
        lifecycle_path = self.provider._job_lifecycle_path(
            self.minimum_slice.binding.job_id
        )
        stored = json.loads(lifecycle_path.read_text(encoding="utf-8"))
        stored["environment"] = "tampered"
        lifecycle_path.chmod(0o600)
        lifecycle_path.write_text(
            json.dumps(
                stored,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        with self.assertRaises(ControlledStagingTerminalCancellationError) as raised:
            cancel_controlled_staging_queued_run(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
                engine="audiveris",
            )
        self.assertEqual(
            raised.exception.category,
            "staging_cancellation_state_invalid",
        )


if __name__ == "__main__":
    unittest.main()
