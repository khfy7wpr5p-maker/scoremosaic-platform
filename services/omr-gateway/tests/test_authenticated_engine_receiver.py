from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.authenticated_engine_receiver import (
    AuthenticatedEngineReceiverError,
    authenticate_controlled_staging_engine_receiver,
)
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_staging_dispatch_intent import (
    persist_controlled_staging_dispatch_intent,
)
from scoremosaic_gateway.controlled_staging_dispatch_wire import (
    WIRE_HEADER_NAMES,
    serialize_controlled_staging_dispatch_wire,
)
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
)
from scoremosaic_gateway.controlled_staging_trusted_plan_store import (
    persist_controlled_staging_trusted_receiver_plan,
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
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
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


class AuthenticatedEngineReceiverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.provider = StagingUploadProvider(
            self.root,
            state_integrity_key=b"A" * 32,
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
        persist_controlled_staging_trusted_receiver_plan(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
        )

        self.endpoint = EngineEndpoint(
            "audiveris",
            APPROVED_ENGINE_ORIGINS["staging"]["audiveris"],
        )
        queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine=self.endpoint.name,
        )
        self.intent = persist_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint,
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
        self.capsule = build_dispatch_input_capsule(
            self.plan,
            self.identity,
            [helpers.PNG_1X1],
        )

        self.timestamp = 1_800_200_000
        self.now_seconds = self.timestamp
        self.nonce = "abcdefabcdefabcdefabcdefabcdefab"
        self.generation_id = "gen-2026-08-authenticated-receiver"
        self.secret = b"Q" * MIN_CREDENTIAL_BYTES
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
        self.wire = serialize_controlled_staging_dispatch_wire(
            target=self.target,
            request=self.request,
            payload=self.payload,
        )

    def _receive(self, **overrides):
        values = {
            "minimum_slice": self.minimum_slice,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "rotation": self.rotation,
            "capsule": self.capsule,
            "headers": self.wire.headers,
            "body": self.wire.body,
            "observed_method": "POST",
            "observed_path": "/internal/transcribe",
            "now_seconds": self.now_seconds,
        }
        values.update(overrides)
        return authenticate_controlled_staging_engine_receiver(**values)

    def _replay_files(self):
        root = self.root / "state" / "replay_reservations"
        return [] if not root.exists() else sorted(root.rglob("*.json"))

    @staticmethod
    def _replace_header(headers, name: str, value: str):
        return tuple(
            (key, value if key.lower() == name else observed)
            for key, observed in headers
        )

    def test_exact_receiver_converges_only_after_auth_and_grants_no_runtime_authority(self) -> None:
        result = self._receive()

        self.assertEqual(result.job_id, self.identity.job_id)
        self.assertEqual(result.engine, self.identity.engine)
        self.assertEqual(result.run_id, self.identity.run_id)
        self.assertEqual(result.dispatch_identity_sha256, self.identity.identity_sha256)
        self.assertEqual(result.source_sha256, self.identity.source_sha256)
        self.assertTrue(result.receiver_authenticated)
        self.assertTrue(result.trusted_plan_converged)
        self.assertTrue(result.capsule_authenticated)
        self.assertTrue(result.replay_reserved)
        self.assertEqual(len(self._replay_files()), 1)

        for attribute in (
            "credential_export_allowed",
            "raw_input_export_allowed",
            "job_state_mutation_allowed",
            "network_dispatch_allowed",
            "retry_allowed",
            "engine_execution_allowed",
        ):
            self.assertIs(getattr(result, attribute), False)

        safe = result.as_safe_dict()
        for sensitive in (
            self.nonce,
            self.secret.decode("ascii"),
            self.request.envelope.signature,
            self.request.generation_signature,
            helpers.PNG_1X1.hex(),
        ):
            self.assertNotIn(sensitive, repr(safe))
        self.assertFalse(safe["networkDispatchAllowed"])
        self.assertFalse(safe["engineExecutionAllowed"])

        with self.assertRaises(AuthenticatedEngineReceiverError):
            replace(result, _seal=object())

    def test_exact_replay_is_permanently_rejected(self) -> None:
        self._receive()
        for attempt in range(5):
            with self.subTest(attempt=attempt + 1):
                with self.assertRaises(AuthenticatedEngineReceiverError) as context:
                    self._receive()
                self.assertEqual(context.exception.category, "replay_detected")
        self.assertEqual(len(self._replay_files()), 1)

    def test_concurrent_same_receiver_request_has_exactly_one_winner(self) -> None:
        def attempt(_):
            try:
                return ("accepted", self._receive().replay_reservation_key)
            except AuthenticatedEngineReceiverError as exc:
                return (exc.category, None)

        with ThreadPoolExecutor(max_workers=8) as pool:
            observed = list(pool.map(attempt, range(8)))

        self.assertEqual(sum(item[0] == "accepted" for item in observed), 1)
        self.assertEqual(sum(item[0] == "replay_detected" for item in observed), 7)
        self.assertEqual(len(self._replay_files()), 1)

    def test_duplicate_missing_and_unexpected_metadata_fail_before_replay(self) -> None:
        duplicated = list(self.wire.headers)
        duplicated[1] = (duplicated[0][0].upper(), duplicated[1][1])
        variants = (
            tuple(duplicated),
            self.wire.headers[:-1],
            self.wire.headers[:-1] + (("x-scoremosaic-unexpected", "x"),),
        )
        for headers in variants:
            with self.subTest(headers=headers):
                with self.assertRaisesRegex(
                    AuthenticatedEngineReceiverError,
                    "authenticated_receiver_wire_invalid",
                ):
                    self._receive(headers=headers)
                self.assertEqual(self._replay_files(), [])

    def test_malformed_framing_and_wrong_observed_target_fail_before_replay(self) -> None:
        with self.assertRaisesRegex(
            AuthenticatedEngineReceiverError,
            "authenticated_receiver_wire_invalid",
        ):
            self._receive(body=self.payload + b"x")
        self.assertEqual(self._replay_files(), [])

        for method, path in (
            ("GET", "/internal/transcribe"),
            ("POST", "/internal/other"),
        ):
            with self.subTest(method=method, path=path):
                with self.assertRaisesRegex(
                    AuthenticatedEngineReceiverError,
                    "authenticated_receiver_wire_invalid",
                ):
                    self._receive(observed_method=method, observed_path=path)
                self.assertEqual(self._replay_files(), [])

    def test_wrong_generation_and_invalid_authentication_proofs_fail_before_replay(self) -> None:
        generation = self._replace_header(
            self.wire.headers,
            WIRE_HEADER_NAMES[0],
            "gen-2026-08-wrong",
        )
        request_signature = self._replace_header(
            self.wire.headers,
            WIRE_HEADER_NAMES[5],
            "0" * 64,
        )
        generation_signature = self._replace_header(
            self.wire.headers,
            WIRE_HEADER_NAMES[6],
            "0" * 64,
        )
        for headers in (generation, request_signature, generation_signature):
            with self.subTest(headers=headers):
                with self.assertRaises(AuthenticatedEngineReceiverError):
                    self._receive(headers=headers)
                self.assertEqual(self._replay_files(), [])

    def test_cross_engine_wrong_target_and_identity_confusion_fail_before_replay(self) -> None:
        clarity_endpoint = EngineEndpoint(
            "clarity",
            APPROVED_ENGINE_ORIGINS["staging"]["clarity"],
        )
        with self.assertRaises(AuthenticatedEngineReceiverError):
            self._receive(endpoint=clarity_endpoint)
        self.assertEqual(self._replay_files(), [])

        clarity_identity = build_dispatch_identity(self.plan, "clarity")
        clarity_capsule = build_dispatch_input_capsule(
            self.plan,
            clarity_identity,
            [helpers.PNG_1X1],
        )
        with self.assertRaisesRegex(
            AuthenticatedEngineReceiverError,
            "authenticated_receiver_convergence_failed",
        ):
            self._receive(capsule=clarity_capsule)
        self.assertEqual(self._replay_files(), [])

    def test_source_tamper_fails_before_trusted_or_replay_side_effect(self) -> None:
        tampered = bytearray(self.capsule.source_bytes)
        tampered[-1] ^= 1
        with self.assertRaisesRegex(
            AuthenticatedEngineReceiverError,
            "authenticated_receiver_capsule_invalid",
        ):
            self._receive(capsule=replace(self.capsule, source_bytes=bytes(tampered)))
        self.assertEqual(self._replay_files(), [])

    def test_valid_but_different_incoming_plan_cannot_become_trusted(self) -> None:
        other_source = self.minimum_slice.binding
        other_plan = build_orchestration_plan(
            "job_receiverconfusion01",
            source_artifact_ref=other_source.source_artifact_ref,
            source_sha256=other_source.document_sha256,
            source_size_bytes=other_source.source_size_bytes,
            source_media_type=other_source.source_media_type,
            requested_engines=ENGINE_NAMES,
        ).as_dict()
        other_identity = build_dispatch_identity(other_plan, self.endpoint.name)
        other_capsule = build_dispatch_input_capsule(
            other_plan,
            other_identity,
            [helpers.PNG_1X1],
        )

        with self.assertRaisesRegex(
            AuthenticatedEngineReceiverError,
            "authenticated_receiver_convergence_failed",
        ):
            self._receive(capsule=other_capsule)
        self.assertEqual(self._replay_files(), [])

    def test_tampered_receiver_owned_trusted_plan_state_fails_before_replay(self) -> None:
        path = (
            self.root
            / "state"
            / "trusted_receiver_plans"
            / f"{self.identity.job_id}.json"
        )
        original = path.read_bytes()
        path.write_bytes(original[:-1] + (b"0" if original[-1:] != b"0" else b"1"))

        with self.assertRaisesRegex(
            AuthenticatedEngineReceiverError,
            "authenticated_receiver_trusted_plan_invalid",
        ):
            self._receive()
        self.assertEqual(self._replay_files(), [])


if __name__ == "__main__":
    unittest.main()
