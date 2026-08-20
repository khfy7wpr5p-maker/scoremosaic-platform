from __future__ import annotations

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
    ControlledStagingDispatchPreflightResult,
    build_controlled_staging_dispatch_preflight,
)
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
    recover_controlled_staging_queued_run,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


AUDIVERIS_STAGING = EngineEndpoint(
    "audiveris",
    "http://audiveris-foundation:8082",
)
HOMR_STAGING = EngineEndpoint(
    "homr",
    "http://homr-foundation:8080",
)


class ControlledStagingDispatchPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.integrity_key = b"P" * 32
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

    def queue(self, *, engine: str = "audiveris"):
        return queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine=engine,
        )

    def preflight(self, *, endpoint: EngineEndpoint = AUDIVERIS_STAGING):
        return build_controlled_staging_dispatch_preflight(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=endpoint,
        )

    def snapshot_files(self) -> dict[str, bytes | str]:
        snapshot: dict[str, bytes | str] = {}
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root).as_posix()
            if path.is_symlink():
                snapshot[relative] = "symlink:" + str(path.readlink())
            elif path.is_file():
                snapshot[relative] = path.read_bytes()
        return snapshot

    def test_exact_queued_preflight_is_read_only_and_non_authoritative(self) -> None:
        queued = self.queue()
        before = self.snapshot_files()

        result = self.preflight()

        after = self.snapshot_files()
        self.assertEqual(before, after)
        self.assertEqual(result.job_id, queued.job_id)
        self.assertEqual(result.source_artifact_id, queued.source_artifact_id)
        self.assertEqual(result.engine, "audiveris")
        self.assertEqual(result.run_id, queued.run_id)
        self.assertEqual(
            result.dispatch_identity_sha256,
            queued.dispatch_identity_sha256,
        )
        self.assertEqual(result.state, "queued")
        self.assertEqual(result.revision, 1)
        self.assertEqual(result.target_origin, "http://audiveris-foundation:8082")
        self.assertEqual(result.target_method, "POST")
        self.assertEqual(result.target_path, "/internal/transcribe")
        self.assertGreater(result.identity_payload_bytes, 0)

        self.assertFalse(result.credential_resolution_allowed)
        self.assertFalse(result.request_signing_allowed)
        self.assertFalse(result.queue_runtime_allowed)
        self.assertFalse(result.worker_allowed)
        self.assertFalse(result.network_dispatch_allowed)
        self.assertFalse(result.state_mutation_allowed)
        self.assertFalse(result.orchestration_allowed)
        self.assertFalse(result.engine_execution_allowed)

        safe = result.as_safe_dict()
        self.assertNotIn("credentialKey", safe)
        self.assertNotIn("signature", safe)
        self.assertNotIn("payload", safe)
        self.assertIs(safe["credentialResolutionAllowed"], False)
        self.assertIs(safe["requestSigningAllowed"], False)
        self.assertIs(safe["networkDispatchAllowed"], False)
        self.assertIs(safe["stateMutationAllowed"], False)

        recovered = recover_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )
        self.assertEqual(recovered.state, "queued")
        self.assertEqual(recovered.revision, 1)

    def test_planned_only_run_cannot_preflight(self) -> None:
        with self.assertRaises(ControlledStagingDispatchPreflightError) as raised:
            self.preflight()
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_preflight_queued_invalid",
        )

    def test_cross_engine_without_exact_queued_transition_fails_closed(self) -> None:
        self.queue(engine="audiveris")

        with self.assertRaises(ControlledStagingDispatchPreflightError) as raised:
            self.preflight(endpoint=HOMR_STAGING)
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_preflight_queued_invalid",
        )

    def test_non_allowlisted_origin_fails_closed(self) -> None:
        self.queue()
        endpoint = EngineEndpoint("audiveris", "http://attacker.invalid:8082")

        with self.assertRaises(ControlledStagingDispatchPreflightError) as raised:
            self.preflight(endpoint=endpoint)
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_preflight_target_invalid",
        )

    def test_source_substitution_after_queue_fails_closed(self) -> None:
        self.queue()
        source_path = self.root / "objects" / self.minimum_slice.binding.source_storage_key
        source_path.chmod(0o600)
        source_path.write_bytes(
            b"X" * self.minimum_slice.binding.source_size_bytes
        )

        with self.assertRaises(ControlledStagingDispatchPreflightError) as raised:
            self.preflight()
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_preflight_queued_invalid",
        )

    def test_endpoint_subclass_fails_closed(self) -> None:
        self.queue()

        class Endpoint(EngineEndpoint):
            pass

        endpoint = Endpoint("audiveris", "http://audiveris-foundation:8082")
        with self.assertRaises(ControlledStagingDispatchPreflightError) as raised:
            self.preflight(endpoint=endpoint)
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_preflight_input_invalid",
        )

    def test_result_identity_subclasses_fail_closed(self) -> None:
        self.queue()
        result = self.preflight()

        class RunId(str):
            pass

        base = {
            "job_id": result.job_id,
            "source_artifact_id": result.source_artifact_id,
            "engine": result.engine,
            "run_id": result.run_id,
            "dispatch_identity_sha256": result.dispatch_identity_sha256,
            "state": result.state,
            "revision": result.revision,
            "target_origin": result.target_origin,
            "target_method": result.target_method,
            "target_path": result.target_path,
            "identity_payload_bytes": result.identity_payload_bytes,
        }
        invalid = dict(base)
        invalid["run_id"] = RunId(result.run_id)
        with self.assertRaises(ControlledStagingDispatchPreflightError) as raised:
            ControlledStagingDispatchPreflightResult(**invalid)
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_preflight_result_invalid",
        )


if __name__ == "__main__":
    unittest.main()
