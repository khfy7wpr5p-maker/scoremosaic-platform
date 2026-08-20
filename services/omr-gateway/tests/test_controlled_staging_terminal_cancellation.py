from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_staging_dispatch_preflight import (
    ControlledStagingDispatchPreflightError,
    build_controlled_staging_dispatch_preflight,
)
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    ControlledStagingQueuedTransitionError,
    queue_controlled_staging_run,
    recover_controlled_staging_queued_run,
)
from scoremosaic_gateway.controlled_staging_terminal_cancellation import (
    CANCELLATION_REASON_CODE,
    ControlledStagingTerminalCancellationError,
    ControlledStagingTerminalCancellationResult,
    cancel_controlled_staging_queued_run,
    recover_controlled_staging_cancelled_run,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


AUDIVERIS_STAGING = EngineEndpoint(
    "audiveris",
    "http://audiveris-foundation:8082",
)


class ControlledStagingTerminalCancellationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.integrity_key = b"C" * 32
        self.provider = StagingUploadProvider(
            self.root,
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

    def queue(self, *, engine: str = "audiveris", provider=None):
        return queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            engine=engine,
        )

    def cancel(self, *, engine: str = "audiveris", provider=None):
        return cancel_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            engine=engine,
        )

    def recover_cancelled(self, *, engine: str = "audiveris", provider=None):
        return recover_controlled_staging_cancelled_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            engine=engine,
        )

    def cancellation_path(self, result):
        return (
            self.root
            / "state"
            / "job_transitions"
            / result.job_id
            / f"{result.run_id}-revision-2.json"
        )

    def test_cancel_converges_job_candidate_and_artifacts_terminal(self) -> None:
        queued = self.queue()
        source_path = self.root / "objects" / self.minimum_slice.binding.source_storage_key
        source_before = source_path.read_bytes()

        result = self.cancel()

        self.assertEqual(result.job_id, queued.job_id)
        self.assertEqual(result.run_id, queued.run_id)
        self.assertEqual(result.dispatch_identity_sha256, queued.dispatch_identity_sha256)
        self.assertEqual(result.reason_code, CANCELLATION_REASON_CODE)
        self.assertEqual(result.state, "cancelled")
        self.assertEqual(result.revision, 2)
        self.assertEqual(result.idempotency_record_count, 2)
        self.assertEqual(result.provenance_record_count, 3)
        self.assertEqual(result.persistence_state, "written")
        self.assertEqual(source_path.read_bytes(), source_before)

        decision = self.recover_cancelled()
        self.assertEqual(decision.state, "cancelled")
        self.assertEqual(decision.revision, 2)
        self.assertEqual(decision.disposition, "terminal_preserved")
        self.assertTrue(decision.terminal)
        self.assertFalse(decision.reconciliation_required)
        self.assertFalse(decision.automatic_execution_allowed)
        self.assertFalse(decision.retry_allowed)
        self.assertFalse(decision.network_dispatch_allowed)
        self.assertFalse(decision.state_mutation_allowed)

        stored = json.loads(self.cancellation_path(result).read_text(encoding="utf-8"))
        self.assertIn("cancellation_integrity_mac", stored)
        lifecycle = stored["candidate_lifecycle"]
        candidate = next(
            item for item in lifecycle["candidates"] if item["engine"] == "audiveris"
        )
        self.assertEqual(candidate["state"], "cancelled")
        self.assertEqual(candidate["reasonCode"], CANCELLATION_REASON_CODE)
        self.assertEqual(
            [item["kind"] for item in candidate["artifacts"]],
            ["raw_engine_result", "musicxml", "diagnostic"],
        )
        for artifact in candidate["artifacts"]:
            self.assertEqual(artifact["state"], "abandoned")
            self.assertEqual(artifact["reasonCode"], CANCELLATION_REASON_CODE)
            self.assertIsNone(artifact["sha256"])
            self.assertIsNone(artifact["sizeBytes"])
            self.assertIsNone(artifact["mediaType"])

        manifest = stored["storage_manifest"]
        self.assertEqual(len(manifest["records"]), 1)
        self.assertEqual(manifest["records"][0]["kind"], "source")
        self.assertEqual(stored["job_state"]["state"], "cancelled")
        self.assertEqual(stored["job_state"]["revision"], 2)
        self.assertEqual(stored["recovery"]["disposition"], "terminal_preserved")

        safe = result.as_safe_dict()
        for key in (
            "cancellationAllowed",
            "queueRuntimeAllowed",
            "workerAllowed",
            "credentialResolutionAllowed",
            "requestSigningAllowed",
            "networkDispatchAllowed",
            "orchestrationAllowed",
            "engineExecutionAllowed",
            "retryAllowed",
            "outputStorageWriteAllowed",
            "sourceMutationAllowed",
            "artifactDeleteAllowed",
            "teacherReviewAllowed",
            "approvalAllowed",
            "publicationAllowed",
        ):
            self.assertIs(safe[key], False)
        self.assertNotIn("credential", safe)
        self.assertNotIn("signature", safe)
        self.assertNotIn("payload", safe)

    def test_exact_replay_is_deterministic_ten_times_across_restart(self) -> None:
        self.queue()
        first = self.cancel()
        self.assertEqual(first.persistence_state, "written")

        observed = []
        for _ in range(10):
            restarted = StagingUploadProvider(
                self.root,
                state_integrity_key=self.integrity_key,
            )
            replay = self.cancel(provider=restarted)
            decision = self.recover_cancelled(provider=restarted)
            self.assertEqual(replay.persistence_state, "replay")
            self.assertEqual(decision.state, "cancelled")
            self.assertEqual(decision.revision, 2)
            self.assertEqual(decision.disposition, "terminal_preserved")
            observed.append(
                (
                    replay.lifecycle_sha256,
                    replay.storage_manifest_sha256,
                    replay.provenance_chain_sha256,
                )
            )

        self.assertEqual(len(set(observed)), 1)
        self.assertEqual(observed[0][0], first.lifecycle_sha256)
        self.assertEqual(observed[0][1], first.storage_manifest_sha256)
        self.assertEqual(observed[0][2], first.provenance_chain_sha256)

    def test_cancel_requires_exact_queued_run(self) -> None:
        with self.assertRaises(ControlledStagingTerminalCancellationError) as raised:
            self.cancel()
        self.assertEqual(
            raised.exception.category,
            "staging_cancellation_queued_missing",
        )

        self.queue(engine="audiveris")
        with self.assertRaises(ControlledStagingTerminalCancellationError) as raised:
            self.cancel(engine="homr")
        self.assertEqual(
            raised.exception.category,
            "staging_cancellation_queued_missing",
        )

    def test_cancelled_revision_supersedes_queue_replay_recovery_and_preflight(self) -> None:
        self.queue()
        self.cancel()

        with self.assertRaises(ControlledStagingQueuedTransitionError) as raised:
            self.queue()
        self.assertEqual(raised.exception.category, "staging_transition_superseded")

        with self.assertRaises(ControlledStagingQueuedTransitionError) as raised:
            recover_controlled_staging_queued_run(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
                engine="audiveris",
            )
        self.assertEqual(raised.exception.category, "staging_transition_superseded")

        with self.assertRaises(ControlledStagingDispatchPreflightError) as raised:
            build_controlled_staging_dispatch_preflight(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
                endpoint=AUDIVERIS_STAGING,
            )
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_preflight_queued_invalid",
        )

    def test_source_substitution_after_queue_fails_before_cancellation_publish(self) -> None:
        queued = self.queue()
        source_path = self.root / "objects" / self.minimum_slice.binding.source_storage_key
        source_path.chmod(0o600)
        source_path.write_bytes(b"X" * self.minimum_slice.binding.source_size_bytes)

        with self.assertRaises(ControlledStagingTerminalCancellationError) as raised:
            self.cancel()
        self.assertEqual(
            raised.exception.category,
            "staging_cancellation_source_invalid",
        )
        self.assertFalse(self.cancellation_path(queued).exists())

    def test_modified_cancellation_mac_fails_closed(self) -> None:
        self.queue()
        result = self.cancel()
        path = self.cancellation_path(result)
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["cancellation_integrity_mac"] = "0" * 64
        path.chmod(0o600)
        path.write_text(
            json.dumps(
                stored,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        with self.assertRaises(ControlledStagingTerminalCancellationError) as raised:
            self.recover_cancelled()
        self.assertEqual(
            raised.exception.category,
            "staging_cancellation_state_invalid",
        )

    def test_result_exact_types_fail_closed(self) -> None:
        self.queue()
        result = self.cancel()

        class State(str):
            pass

        base = {
            "job_id": result.job_id,
            "source_artifact_id": result.source_artifact_id,
            "engine": result.engine,
            "run_id": result.run_id,
            "dispatch_identity_sha256": result.dispatch_identity_sha256,
            "reason_code": result.reason_code,
            "state": result.state,
            "revision": result.revision,
            "idempotency_record_count": result.idempotency_record_count,
            "provenance_record_count": result.provenance_record_count,
            "lifecycle_sha256": result.lifecycle_sha256,
            "storage_manifest_sha256": result.storage_manifest_sha256,
            "provenance_chain_sha256": result.provenance_chain_sha256,
            "persistence_state": result.persistence_state,
        }
        base["state"] = State(result.state)
        with self.assertRaises(ControlledStagingTerminalCancellationError) as raised:
            ControlledStagingTerminalCancellationResult(**base)
        self.assertEqual(
            raised.exception.category,
            "staging_cancellation_result_invalid",
        )


if __name__ == "__main__":
    unittest.main()
