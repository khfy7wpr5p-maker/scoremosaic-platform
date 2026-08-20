from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_staging_dispatch_intent import (
    ControlledStagingDispatchIntentError,
    ControlledStagingDispatchIntentResult,
    persist_controlled_staging_dispatch_intent,
    recover_controlled_staging_dispatch_intent,
)
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
    cancel_controlled_staging_queued_run,
)
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


class ControlledStagingDispatchIntentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.integrity_key = b"I" * 32
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

    def endpoint(self, engine: str = "audiveris") -> EngineEndpoint:
        return EngineEndpoint(engine, APPROVED_ENGINE_ORIGINS["staging"][engine])

    def queue(self, engine: str = "audiveris"):
        return queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine=engine,
        )

    def persist(self, engine: str = "audiveris", provider=None, endpoint=None):
        return persist_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            endpoint=self.endpoint(engine) if endpoint is None else endpoint,
        )

    def recover(self, engine: str = "audiveris", provider=None):
        return recover_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            endpoint=self.endpoint(engine),
        )

    @staticmethod
    def _all_keys(value):
        if isinstance(value, dict):
            keys = set(value)
            for nested in value.values():
                keys.update(ControlledStagingDispatchIntentTests._all_keys(nested))
            return keys
        if isinstance(value, list):
            keys = set()
            for nested in value:
                keys.update(ControlledStagingDispatchIntentTests._all_keys(nested))
            return keys
        return set()

    def test_persists_exact_preflight_intent_without_execution_authority(self) -> None:
        self.queue()
        preflight = build_controlled_staging_dispatch_preflight(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint(),
        )

        result = self.persist()
        recovered = self.recover()
        queued = recover_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )

        self.assertEqual(result.persistence_state, "written")
        self.assertEqual(recovered.persistence_state, "replay")
        self.assertEqual(result.job_id, preflight.job_id)
        self.assertEqual(result.source_artifact_id, preflight.source_artifact_id)
        self.assertEqual(result.engine, preflight.engine)
        self.assertEqual(result.run_id, preflight.run_id)
        self.assertEqual(
            result.dispatch_identity_sha256,
            preflight.dispatch_identity_sha256,
        )
        self.assertEqual(result.identity_payload_bytes, preflight.identity_payload_bytes)
        self.assertEqual(result.target_origin, preflight.target_origin)
        self.assertEqual(result.target_method, preflight.target_method)
        self.assertEqual(result.target_path, preflight.target_path)
        self.assertEqual(result.state, "queued")
        self.assertEqual(result.revision, 1)
        self.assertEqual(queued.state, "queued")
        self.assertEqual(queued.revision, 1)
        self.assertEqual(result.intent_sha256, recovered.intent_sha256)

        for attribute in (
            "job_state_mutation_allowed",
            "credential_resolution_allowed",
            "request_signing_allowed",
            "nonce_allocation_allowed",
            "timestamp_allocation_allowed",
            "queue_runtime_allowed",
            "worker_allowed",
            "network_dispatch_allowed",
            "dispatch_attempt_allowed",
            "orchestration_allowed",
            "engine_execution_allowed",
            "retry_allowed",
        ):
            self.assertIs(getattr(result, attribute), False)

        safe = result.as_safe_dict()
        self.assertFalse(safe["jobStateMutationAllowed"])
        self.assertFalse(safe["networkDispatchAllowed"])
        self.assertFalse(safe["dispatchAttemptAllowed"])
        self.assertNotIn("credentialKey", safe)
        self.assertNotIn("nonce", safe)
        self.assertNotIn("timestamp", safe)
        self.assertNotIn("signature", safe)
        self.assertNotIn("payload", safe)

        intent_path = (
            self.root
            / "state"
            / "dispatch_intents"
            / result.job_id
            / f"{result.run_id}.json"
        )
        stored = json.loads(intent_path.read_text(encoding="utf-8"))
        keys = self._all_keys(stored)
        self.assertNotIn("credential_key", keys)
        self.assertNotIn("credentialKey", keys)
        self.assertNotIn("nonce", keys)
        self.assertNotIn("timestamp", keys)
        self.assertNotIn("signature", keys)
        self.assertNotIn("payload", keys)
        self.assertIn("dispatch_intent_integrity_mac", keys)

    def test_exact_replay_is_byte_identical_ten_of_ten_across_restart(self) -> None:
        self.queue()
        first = self.persist()
        path = (
            self.root
            / "state"
            / "dispatch_intents"
            / first.job_id
            / f"{first.run_id}.json"
        )
        original_bytes = path.read_bytes()
        restarted = StagingUploadProvider(
            self.root,
            state_integrity_key=self.integrity_key,
        )

        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                replay = self.persist(provider=restarted)
                recovered = self.recover(provider=restarted)
                self.assertEqual(replay.persistence_state, "replay")
                self.assertEqual(recovered.persistence_state, "replay")
                self.assertEqual(replay.intent_sha256, first.intent_sha256)
                self.assertEqual(recovered.intent_sha256, first.intent_sha256)
                self.assertEqual(path.read_bytes(), original_bytes)

    def test_terminal_cancellation_supersedes_existing_intent_and_old_queued_paths(self) -> None:
        self.queue()
        self.persist()
        cancel_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )

        for operation in (self.recover, self.persist):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(ControlledStagingDispatchIntentError) as raised:
                    operation()
                self.assertEqual(
                    raised.exception.category,
                    "staging_dispatch_intent_superseded",
                )

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
                endpoint=self.endpoint(),
            )
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_preflight_queued_invalid",
        )

    def test_cancellation_before_intent_blocks_intent_creation(self) -> None:
        self.queue()
        cancelled = cancel_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )

        with self.assertRaises(ControlledStagingDispatchIntentError) as raised:
            self.persist()
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_intent_superseded",
        )
        intent_path = (
            self.root
            / "state"
            / "dispatch_intents"
            / cancelled.job_id
            / f"{cancelled.run_id}.json"
        )
        self.assertFalse(intent_path.exists())

    def test_wrong_origin_and_cross_engine_without_queue_fail_before_intent(self) -> None:
        self.queue()
        wrong = EngineEndpoint("audiveris", "http://attacker.invalid:9999")
        with self.assertRaises(ControlledStagingDispatchIntentError) as raised:
            self.persist(endpoint=wrong)
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_intent_contract_invalid",
        )

        with self.assertRaises(ControlledStagingDispatchIntentError) as raised:
            self.persist(engine="homr")
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_intent_queued_missing",
        )

    def test_modified_source_fails_closed_before_intent_write(self) -> None:
        queued = self.queue()
        source_path = self.root / "objects" / self.minimum_slice.binding.source_storage_key
        source_path.chmod(0o600)
        source_path.write_bytes(b"X" * self.minimum_slice.binding.source_size_bytes)

        with self.assertRaises(ControlledStagingDispatchIntentError) as raised:
            self.persist()
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_intent_source_invalid",
        )
        intent_path = (
            self.root
            / "state"
            / "dispatch_intents"
            / queued.job_id
            / f"{queued.run_id}.json"
        )
        self.assertFalse(intent_path.exists())

    def test_intent_mac_tamper_and_symlink_fail_closed(self) -> None:
        self.queue()
        result = self.persist()
        path = (
            self.root
            / "state"
            / "dispatch_intents"
            / result.job_id
            / f"{result.run_id}.json"
        )
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["dispatch_intent_integrity_mac"] = "0" * 64
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
        with self.assertRaises(ControlledStagingDispatchIntentError) as raised:
            self.recover()
        self.assertEqual(
            raised.exception.category,
            "staging_dispatch_intent_state_invalid",
        )

        path.unlink()
        outside = self.root / "outside-intent.json"
        outside.write_text("{}", encoding="utf-8")
        os.symlink(outside, path)
        with self.assertRaises(ControlledStagingDispatchIntentError) as raised:
            self.recover()
        self.assertIn(
            raised.exception.category,
            {
                "staging_dispatch_intent_missing",
                "staging_dispatch_intent_state_invalid",
            },
        )

    def test_result_string_subclasses_fail_closed(self) -> None:
        self.queue()
        result = self.persist()

        class State(str):
            pass

        class RunId(str):
            pass

        base = {
            "job_id": result.job_id,
            "source_artifact_id": result.source_artifact_id,
            "engine": result.engine,
            "run_id": result.run_id,
            "dispatch_identity_sha256": result.dispatch_identity_sha256,
            "identity_payload_sha256": result.identity_payload_sha256,
            "identity_payload_bytes": result.identity_payload_bytes,
            "state": result.state,
            "revision": result.revision,
            "caller_identity": result.caller_identity,
            "audience_identity": result.audience_identity,
            "target_origin": result.target_origin,
            "target_method": result.target_method,
            "target_path": result.target_path,
            "intent_sha256": result.intent_sha256,
            "persistence_state": result.persistence_state,
        }
        for field, invalid in (
            ("state", State("queued")),
            ("run_id", RunId(result.run_id)),
        ):
            with self.subTest(field=field):
                kwargs = dict(base)
                kwargs[field] = invalid
                with self.assertRaises(ControlledStagingDispatchIntentError) as raised:
                    ControlledStagingDispatchIntentResult(**kwargs)
                self.assertEqual(
                    raised.exception.category,
                    "staging_dispatch_intent_result_invalid",
                )


if __name__ == "__main__":
    unittest.main()
