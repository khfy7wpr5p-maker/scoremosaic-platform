from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
)
from scoremosaic_gateway.controlled_staging_trusted_plan_store import (
    _plan_path,
    persist_controlled_staging_trusted_receiver_plan,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


class ControlledStagingTrustedPlanStoreRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        fixture.setUp()
        admission = fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.key = b"R" * 32
        self.provider = StagingUploadProvider(
            self.root,
            state_integrity_key=self.key,
        )
        self.minimum_slice = run_minimum_staging_vertical_slice(
            admission=admission,
            session_policy=fixture.session_policy,
            payload=helpers.PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=admission.evaluated_at_epoch_s,
            provider=self.provider,
        )
        run_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
        )

    def test_existing_exact_plan_replays_after_queue_and_restart_without_mutation(self) -> None:
        first = persist_controlled_staging_trusted_receiver_plan(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
        )
        self.assertEqual(first.persistence_state, "written")
        path = _plan_path(self.provider, job_id=self.minimum_slice.binding.job_id)
        before = path.read_bytes()

        queued = queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="homr",
        )
        self.assertEqual((queued.state, queued.revision), ("queued", 1))

        restarted = StagingUploadProvider(
            self.root,
            state_integrity_key=self.key,
        )
        replay = persist_controlled_staging_trusted_receiver_plan(
            minimum_slice=self.minimum_slice,
            provider=restarted,
        )
        self.assertEqual(replay.persistence_state, "replay")
        self.assertEqual(replay.job_id, first.job_id)
        self.assertEqual(replay.canonical_plan_sha256, first.canonical_plan_sha256)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
