from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    ControlledStagingQueuedTransitionError,
    queue_controlled_staging_run,
    recover_controlled_staging_queued_run,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


class ControlledStagingQueuedTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.integrity_key = b"Q" * 32
        self.provider = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=self.integrity_key,
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

    def queue(self, *, engine="audiveris", provider=None):
        return queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            engine=engine,
        )

    def recover(self, *, engine="audiveris", provider=None):
        return recover_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            engine=engine,
        )

    def test_persists_only_planned_to_queued_revision(self) -> None:
        result = self.queue()

        self.assertEqual(result.engine, "audiveris")
        self.assertEqual(result.state, "queued")
        self.assertEqual(result.revision, 1)
        self.assertEqual(result.idempotency_record_count, 1)
        self.assertEqual(result.provenance_record_count, 2)
        self.assertEqual(result.persistence_state, "written")
        self.assertFalse(result.worker_allowed)
        self.assertFalse(result.network_dispatch_allowed)
        self.assertFalse(result.orchestration_allowed)
        self.assertFalse(result.engine_execution_allowed)

        recovered = self.recover()
        self.assertEqual(recovered.state, "queued")
        self.assertEqual(recovered.revision, 1)
        self.assertEqual(recovered.disposition, "pre_dispatch_candidate")
        self.assertFalse(recovered.automatic_execution_allowed)
        self.assertFalse(recovered.retry_allowed)
        self.assertFalse(recovered.network_dispatch_allowed)
        self.assertFalse(recovered.state_mutation_allowed)

    def test_exact_replay_and_restart_do_not_duplicate_revision(self) -> None:
        first = self.queue()
        replay = self.queue()
        restarted = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=self.integrity_key,
        )
        after_restart = self.queue(provider=restarted)
        recovered = self.recover(provider=restarted)

        self.assertEqual(first.persistence_state, "written")
        self.assertEqual(replay.persistence_state, "replay")
        self.assertEqual(after_restart.persistence_state, "replay")
        self.assertEqual(first.state, replay.state)
        self.assertEqual(first.revision, replay.revision)
        self.assertEqual(first.provenance_chain_sha256, replay.provenance_chain_sha256)
        self.assertEqual(first.provenance_chain_sha256, after_restart.provenance_chain_sha256)
        self.assertEqual(recovered.state, "queued")
        self.assertEqual(recovered.revision, 1)

    def test_replay_rechecks_source_after_existing_transition_is_verified(self) -> None:
        self.queue()
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / self.minimum_slice.binding.source_storage_key
        )
        original_atomic_create = StagingUploadProvider._atomic_create

        def replace_source_after_replay_check(
            provider,
            path,
            payload,
            *,
            prepublish_check=None,
            postpublish_check=None,
        ):
            created = original_atomic_create(
                provider,
                path,
                payload,
                prepublish_check=prepublish_check,
                postpublish_check=postpublish_check,
            )
            if "job_transitions" in path.parts and not created:
                source_path.chmod(0o600)
                source_path.write_bytes(
                    b"X" * self.minimum_slice.binding.source_size_bytes
                )
            return created

        with mock.patch.object(
            StagingUploadProvider,
            "_atomic_create",
            new=replace_source_after_replay_check,
        ):
            with self.assertRaises(ControlledStagingQueuedTransitionError) as raised:
                self.queue()
        self.assertEqual(raised.exception.category, "staging_transition_source_invalid")

    def test_transition_is_scoped_to_one_engine_run(self) -> None:
        audiveris = self.queue(engine="audiveris")
        homr = self.queue(engine="homr")

        self.assertNotEqual(audiveris.run_id, homr.run_id)
        self.assertEqual(self.recover(engine="audiveris").state, "queued")
        self.assertEqual(self.recover(engine="homr").state, "queued")
        with self.assertRaises(ControlledStagingQueuedTransitionError) as raised:
            self.recover(engine="clarity")
        self.assertEqual(raised.exception.category, "staging_transition_missing")

    def test_modified_source_fails_closed_before_transition_write(self) -> None:
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / self.minimum_slice.binding.source_storage_key
        )
        source_path.chmod(0o600)
        source_path.write_bytes(
            b"X" * self.minimum_slice.binding.source_size_bytes
        )

        with self.assertRaises(ControlledStagingQueuedTransitionError) as raised:
            self.queue()
        self.assertEqual(raised.exception.category, "staging_transition_source_invalid")

    def test_restart_with_wrong_integrity_key_fails_closed(self) -> None:
        self.queue()
        wrong_key = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=b"W" * 32,
        )

        with self.assertRaises(ControlledStagingQueuedTransitionError) as raised:
            self.recover(provider=wrong_key)
        self.assertEqual(raised.exception.category, "staging_transition_state_invalid")

    def test_invalid_engine_type_fails_closed(self) -> None:
        class EngineName(str):
            pass

        with self.assertRaises(ControlledStagingQueuedTransitionError) as raised:
            self.queue(engine=EngineName("audiveris"))
        self.assertEqual(raised.exception.category, "staging_transition_engine_invalid")


if __name__ == "__main__":
    unittest.main()
