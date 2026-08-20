from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.app import route_request
from scoremosaic_gateway.authenticated_request import MAX_REQUEST_AGE_SECONDS
from scoremosaic_gateway.config import EngineEndpoint, load_config
from scoremosaic_gateway.controlled_staging_dispatch_intent import (
    persist_controlled_staging_dispatch_intent,
)
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
)
from scoremosaic_gateway.controlled_staging_receiver_preflight import (
    ControlledStagingReceiverPreflightError,
    ControlledStagingReceiverPreflightResult,
    verify_controlled_staging_receiver_preflight,
)
from scoremosaic_gateway.controlled_staging_terminal_cancellation import (
    cancel_controlled_staging_queued_run,
)
from scoremosaic_gateway.credential_rotation import (
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    build_engine_dispatch_target,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)
from scoremosaic_gateway.orchestration import ENGINE_NAMES, build_orchestration_plan
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


class ControlledStagingReceiverPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.integrity_key = b"R" * 32
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
        self.endpoint = EngineEndpoint(
            "audiveris",
            APPROVED_ENGINE_ORIGINS["staging"]["audiveris"],
        )
        self.queued = queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )
        self.intent = persist_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint,
        )
        self.timestamp = 1_800_000_000
        self.now_seconds = self.timestamp
        self.nonce = "0123456789abcdef0123456789abcdef"
        self.secret = b"V" * MIN_CREDENTIAL_BYTES
        self.generation_id = "gen-2026-08-receiver"
        self.binding = build_engine_auth_binding(self.endpoint, "staging")
        credential = resolve_engine_credential_generation(
            self.binding,
            self.generation_id,
            lambda credential_key, generation_id: (
                self.secret
                if credential_key == self.binding.credential_key
                and generation_id == self.generation_id
                else None
            ),
        )
        self.rotation = build_rotation_set(
            current=credential,
            previous=None,
            rotation_started_at=self.timestamp - 1,
            previous_valid_until=None,
        )
        source = self.minimum_slice.binding
        self.plan = build_orchestration_plan(
            source.job_id,
            source_artifact_ref=source.source_artifact_ref,
            source_sha256=source.document_sha256,
            source_size_bytes=source.source_size_bytes,
            source_media_type=source.source_media_type,
            requested_engines=ENGINE_NAMES,
        ).as_dict()
        self.identity = build_dispatch_identity(self.plan, self.endpoint.name)
        self.payload = dispatch_identity_payload(self.identity)
        self.target = build_engine_dispatch_target(self.binding, self.endpoint)
        self.request = sign_rotation_authenticated_request(
            self.rotation,
            method=self.target.method,
            path=self.target.path,
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
            now_seconds=self.now_seconds,
        )

    def _preflight(self, **overrides):
        values = {
            "minimum_slice": self.minimum_slice,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "rotation": self.rotation,
            "request": self.request,
            "payload": self.payload,
            "observed_method": "POST",
            "observed_path": "/internal/transcribe",
            "now_seconds": self.now_seconds,
        }
        values.update(overrides)
        return verify_controlled_staging_receiver_preflight(**values)

    def _replay_files(self):
        root = self.root / "state" / "replay_reservations"
        return [] if not root.exists() else sorted(root.rglob("*.json"))

    def _intent_path(self) -> Path:
        return (
            self.root
            / "state"
            / "dispatch_intents"
            / self.intent.job_id
            / f"{self.intent.run_id}.json"
        )

    def _lock_path(self) -> Path:
        return self.provider._job_lock_path(self.intent.job_id)

    def _source_path(self) -> Path:
        return self.provider._source_path(self.minimum_slice.binding)

    def test_accepts_exact_signed_request_and_returns_only_safe_receiver_evidence(self) -> None:
        result = self._preflight()

        self.assertEqual(result.job_id, self.intent.job_id)
        self.assertEqual(result.source_artifact_id, self.intent.source_artifact_id)
        self.assertEqual(result.engine, self.intent.engine)
        self.assertEqual(result.run_id, self.intent.run_id)
        self.assertEqual(
            result.dispatch_identity_sha256,
            self.intent.dispatch_identity_sha256,
        )
        self.assertEqual(result.credential_generation_id, self.generation_id)
        self.assertEqual(result.request_timestamp, self.timestamp)
        self.assertEqual(result.payload_sha256, self.intent.identity_payload_sha256)
        self.assertEqual(result.payload_bytes, self.intent.identity_payload_bytes)
        self.assertEqual(result.target_origin, self.intent.target_origin)
        self.assertEqual(result.target_method, "POST")
        self.assertEqual(result.target_path, "/internal/transcribe")
        self.assertEqual((result.state, result.revision), ("queued", 1))
        self.assertTrue(result.receiver_verified)
        self.assertTrue(result.replay_reserved)
        self.assertEqual(len(self._replay_files()), 1)

        for attribute in (
            "credential_export_allowed",
            "raw_nonce_export_allowed",
            "signed_request_export_allowed",
            "payload_export_allowed",
            "job_state_mutation_allowed",
            "queue_runtime_allowed",
            "worker_allowed",
            "network_dispatch_allowed",
            "dispatch_attempt_allowed",
            "orchestration_allowed",
            "engine_execution_allowed",
            "retry_allowed",
            "replay_cleanup_allowed",
        ):
            self.assertIs(getattr(result, attribute), False)

        self.assertFalse(hasattr(result, "nonce"))
        self.assertFalse(hasattr(result, "signature"))
        self.assertFalse(hasattr(result, "generation_signature"))
        self.assertFalse(hasattr(result, "payload"))
        self.assertFalse(hasattr(result, "credential"))
        safe = result.as_safe_dict()
        self.assertNotIn(self.nonce, repr(safe))
        self.assertNotIn(self.secret.decode("ascii"), repr(safe))
        self.assertNotIn(self.request.envelope.signature, repr(safe))
        self.assertNotIn(self.request.generation_signature, repr(safe))
        self.assertNotIn("nonce", safe)
        self.assertNotIn("credential", safe)
        self.assertFalse(safe["networkDispatchAllowed"])
        self.assertFalse(safe["engineExecutionAllowed"])

    def test_same_request_is_rejected_as_replay_ten_of_ten(self) -> None:
        self._preflight()
        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
                    self._preflight()
                self.assertEqual(context.exception.category, "replay_detected")
        self.assertEqual(len(self._replay_files()), 1)

    def test_concurrent_same_request_has_exactly_one_receiver_acceptance(self) -> None:
        def attempt(_):
            try:
                result = self._preflight()
                return ("accepted", result.replay_reservation_key)
            except ControlledStagingReceiverPreflightError as exc:
                return (exc.category, None)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))

        accepted = [item for item in results if item[0] == "accepted"]
        replayed = [item for item in results if item[0] == "replay_detected"]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(replayed), 7)
        self.assertEqual(len(self._replay_files()), 1)

    def test_invalid_generation_proof_fails_before_replay_persistence(self) -> None:
        tampered = replace(self.request, generation_signature="0" * 64)
        with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
            self._preflight(request=tampered)
        self.assertEqual(context.exception.category, "generation_request_signature_invalid")
        self.assertEqual(self._replay_files(), [])

    def test_expired_request_fails_before_replay_persistence(self) -> None:
        with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
            self._preflight(now_seconds=self.timestamp + MAX_REQUEST_AGE_SECONDS + 1)
        self.assertEqual(context.exception.category, "timestamp_expired")
        self.assertEqual(self._replay_files(), [])

    def test_wrong_observed_target_fails_before_replay_persistence(self) -> None:
        for method, path, category in (
            ("GET", "/internal/transcribe", "request_method_mismatch"),
            ("POST", "/internal/other", "request_path_mismatch"),
        ):
            with self.subTest(method=method, path=path):
                with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
                    self._preflight(observed_method=method, observed_path=path)
                self.assertEqual(context.exception.category, category)
                self.assertEqual(self._replay_files(), [])

    def test_terminal_cancellation_supersedes_before_replay_persistence(self) -> None:
        cancel_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine=self.endpoint.name,
        )
        with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
            self._preflight()
        self.assertEqual(context.exception.category, "staging_receiver_preflight_superseded")
        self.assertEqual(self._replay_files(), [])

    def test_missing_intent_fails_before_replay_persistence(self) -> None:
        self._intent_path().unlink()
        with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
            self._preflight()
        self.assertEqual(context.exception.category, "staging_receiver_preflight_intent_missing")
        self.assertEqual(self._replay_files(), [])

    def test_tampered_intent_fails_before_replay_persistence(self) -> None:
        path = self._intent_path()
        path.chmod(0o600)
        payload = bytearray(path.read_bytes())
        payload[-2] = ord("0") if payload[-2] != ord("0") else ord("1")
        path.write_bytes(bytes(payload))
        with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
            self._preflight()
        self.assertIn(
            context.exception.category,
            {"staging_receiver_preflight_intent_invalid", "staging_receiver_preflight_state_invalid"},
        )
        self.assertEqual(self._replay_files(), [])

    def test_source_substitution_fails_before_replay_persistence(self) -> None:
        path = self._source_path()
        path.chmod(0o600)
        path.write_bytes(b"tampered-source")
        with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
            self._preflight()
        self.assertEqual(context.exception.category, "staging_receiver_preflight_source_invalid")
        self.assertEqual(self._replay_files(), [])

    def test_missing_lock_fails_without_recreation_or_replay_persistence(self) -> None:
        lock_path = self._lock_path()
        lock_path.unlink()
        self.assertFalse(lock_path.exists())
        with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
            self._preflight()
        self.assertEqual(context.exception.category, "staging_receiver_preflight_lock_invalid")
        self.assertFalse(lock_path.exists())
        self.assertEqual(self._replay_files(), [])

    def test_replay_tombstone_survives_provider_restart(self) -> None:
        self._preflight()
        restarted = StagingUploadProvider(
            self.root,
            state_integrity_key=self.integrity_key,
        )
        with self.assertRaises(ControlledStagingReceiverPreflightError) as context:
            self._preflight(provider=restarted)
        self.assertEqual(context.exception.category, "replay_detected")
        self.assertEqual(len(self._replay_files()), 1)

    def test_persisted_replay_state_contains_no_raw_request_or_secret_material(self) -> None:
        self._preflight()
        raw = self._replay_files()[0].read_text("utf-8")
        self.assertNotIn(self.nonce, raw)
        self.assertNotIn(self.generation_id, raw)
        self.assertNotIn(self.binding.credential_key, raw)
        self.assertNotIn(self.secret.decode("ascii"), raw)
        self.assertNotIn(self.request.envelope.signature, raw)
        self.assertNotIn(self.request.generation_signature, raw)
        self.assertNotIn(self.payload.decode("ascii"), raw)

    def test_result_exact_type_and_authority_boundaries_fail_closed(self) -> None:
        result = self._preflight()
        for field, value in (
            ("request_timestamp", True),
            ("payload_bytes", True),
            ("replay_expires_at", True),
            ("target_origin", "http://example.invalid"),
            ("state", "dispatching"),
            ("revision", True),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ControlledStagingReceiverPreflightError):
                    replace(result, **{field: value})

    def test_internal_transcribe_http_route_remains_disabled(self) -> None:
        response = route_request("POST", "/internal/transcribe", load_config({}))
        self.assertEqual(response.status, 405)
        self.assertEqual(response.allow, "GET")
        self.assertEqual(response.payload, {"error": "method_not_allowed"})


if __name__ == "__main__":
    unittest.main()
