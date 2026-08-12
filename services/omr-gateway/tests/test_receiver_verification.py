from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.app import route_request
from scoremosaic_gateway.config import EngineEndpoint, load_config
from scoremosaic_gateway.credential_rotation import (
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_target import build_engine_dispatch_target
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.receiver_verification import (
    RECEIVER_VERIFICATION_CONTRACT_VERSION,
    ReceiverVerificationError,
    verify_receiver_dispatch_request,
)
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


class ReceiverVerificationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoint = EngineEndpoint("homr", "http://homr-foundation:8080")
        self.binding = build_engine_auth_binding(self.endpoint, "staging")
        self.generation = "gen-2026-08-c"
        self.secret = b"R" * MIN_CREDENTIAL_BYTES
        self.timestamp = 1_800_100_000
        self.nonce = "abcdef0123456789abcdef0123456789"
        self.plan = build_orchestration_plan(
            "job_c2eadapter01",
            source_artifact_ref="sources/job_c2eadapter01/source.pdf",
            source_sha256="3" * 64,
            source_size_bytes=8192,
            source_media_type="application/pdf",
        ).as_dict()
        self.generation_credential = resolve_engine_credential_generation(
            self.binding,
            self.generation,
            lambda credential_key, generation_id: (
                self.secret
                if credential_key == self.binding.credential_key
                and generation_id == self.generation
                else None
            ),
        )
        self.rotation = build_rotation_set(
            current=self.generation_credential,
            previous=None,
            rotation_started_at=self.timestamp,
            previous_valid_until=None,
        )
        self.target = build_engine_dispatch_target(self.binding, self.endpoint)
        self.identity = build_dispatch_identity(self.plan, "homr")
        self.payload = dispatch_identity_payload(self.identity)
        self.request = sign_rotation_authenticated_request(
            self.rotation,
            method=self.target.method,
            path=self.target.path,
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
            now_seconds=self.timestamp,
        )

    def verify(self, *, replay_checker):
        return verify_receiver_dispatch_request(
            self.plan,
            self.target,
            self.rotation,
            self.request,
            observed_method="POST",
            observed_path="/internal/transcribe",
            payload=self.payload,
            now_seconds=self.timestamp,
            replay_checker=replay_checker,
        )

    def test_valid_request_converges_to_one_typed_verified_dispatch(self) -> None:
        seen: list[tuple[str, str, str, int]] = []

        def replay_checker(binding, generation_id: str, nonce: str, timestamp: int):
            self.assertEqual(binding, self.binding)
            seen.append((binding.engine, generation_id, nonce, timestamp))
            return True

        verified = self.verify(replay_checker=replay_checker)

        self.assertEqual(verified.version, RECEIVER_VERIFICATION_CONTRACT_VERSION)
        self.assertEqual(verified.target, self.target)
        self.assertEqual(verified.dispatch_identity, self.identity)
        self.assertEqual(
            verified.generation_credential.generation_id,
            self.generation,
        )
        self.assertEqual(verified.request_timestamp, self.timestamp)
        self.assertEqual(verified.nonce, self.nonce)
        self.assertEqual(verified.payload_sha256, self.request.envelope.payload_sha256)
        self.assertEqual(
            seen,
            [("homr", self.generation, self.nonce, self.timestamp)],
        )
        self.assertFalse(hasattr(verified, "payload"))

    def test_semantic_identity_mismatch_fails_before_replay_reservation(self) -> None:
        other_plan = build_orchestration_plan(
            "job_c2eadapter02",
            source_artifact_ref="sources/job_c2eadapter02/source.pdf",
            source_sha256="4" * 64,
            source_size_bytes=8192,
            source_media_type="application/pdf",
        ).as_dict()
        other_payload = dispatch_identity_payload(
            build_dispatch_identity(other_plan, "homr")
        )
        request = sign_rotation_authenticated_request(
            self.rotation,
            method=self.target.method,
            path=self.target.path,
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=other_payload,
            now_seconds=self.timestamp,
        )
        replay_calls = 0

        def replay_checker(binding, generation_id, nonce, timestamp):
            nonlocal replay_calls
            replay_calls += 1
            return True

        with self.assertRaisesRegex(
            ReceiverVerificationError,
            "dispatch_identity_payload_mismatch",
        ):
            verify_receiver_dispatch_request(
                self.plan,
                self.target,
                self.rotation,
                request,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=other_payload,
                now_seconds=self.timestamp,
                replay_checker=replay_checker,
            )

        self.assertEqual(replay_calls, 0)

    def test_generation_proof_tamper_fails_before_replay_reservation(self) -> None:
        tampered = replace(self.request, generation_signature="0" * 64)
        replay_calls = 0

        def replay_checker(binding, generation_id, nonce, timestamp):
            nonlocal replay_calls
            replay_calls += 1
            return True

        with self.assertRaisesRegex(
            ReceiverVerificationError,
            "generation_request_signature_invalid",
        ):
            verify_receiver_dispatch_request(
                self.plan,
                self.target,
                self.rotation,
                tampered,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=replay_checker,
            )

        self.assertEqual(replay_calls, 0)

    def test_observed_method_and_path_are_exact_and_fail_before_replay(self) -> None:
        for method, path, category in (
            ("GET", "/internal/transcribe", "request_method_mismatch"),
            ("POST", "/internal/other", "request_path_mismatch"),
        ):
            with self.subTest(method=method, path=path):
                replay_calls = 0

                def replay_checker(binding, generation_id, nonce, timestamp):
                    nonlocal replay_calls
                    replay_calls += 1
                    return True

                with self.assertRaisesRegex(ReceiverVerificationError, category):
                    verify_receiver_dispatch_request(
                        self.plan,
                        self.target,
                        self.rotation,
                        self.request,
                        observed_method=method,
                        observed_path=path,
                        payload=self.payload,
                        now_seconds=self.timestamp,
                        replay_checker=replay_checker,
                    )

                self.assertEqual(replay_calls, 0)

    def test_cross_engine_target_is_rejected_before_replay(self) -> None:
        clarity_endpoint = EngineEndpoint(
            "clarity",
            "http://clarity-foundation:8081",
        )
        clarity_binding = build_engine_auth_binding(clarity_endpoint, "staging")
        clarity_target = build_engine_dispatch_target(clarity_binding, clarity_endpoint)
        replay_calls = 0

        def replay_checker(binding, generation_id, nonce, timestamp):
            nonlocal replay_calls
            replay_calls += 1
            return True

        with self.assertRaises(ReceiverVerificationError):
            verify_receiver_dispatch_request(
                self.plan,
                clarity_target,
                self.rotation,
                self.request,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=replay_checker,
            )

        self.assertEqual(replay_calls, 0)

    def test_mutable_or_wrong_payload_type_is_rejected_before_replay(self) -> None:
        replay_calls = 0

        def replay_checker(binding, generation_id, nonce, timestamp):
            nonlocal replay_calls
            replay_calls += 1
            return True

        with self.assertRaisesRegex(
            ReceiverVerificationError,
            "dispatch_identity_payload_invalid",
        ):
            verify_receiver_dispatch_request(
                self.plan,
                self.target,
                self.rotation,
                self.request,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=bytearray(self.payload),
                now_seconds=self.timestamp,
                replay_checker=replay_checker,
            )

        self.assertEqual(replay_calls, 0)

    def test_replay_rejection_and_store_failure_fail_closed(self) -> None:
        with self.assertRaisesRegex(ReceiverVerificationError, "replay_detected"):
            self.verify(
                replay_checker=lambda binding, generation_id, nonce, timestamp: False
            )

        def unavailable(binding, generation_id, nonce, timestamp):
            raise RuntimeError("private replay backend detail")

        with self.assertRaises(ReceiverVerificationError) as context:
            self.verify(replay_checker=unavailable)
        self.assertEqual(context.exception.category, "replay_check_unavailable")
        self.assertNotIn("private replay backend detail", str(context.exception))

    def test_safe_diagnostics_redact_credentials_and_authentication_proofs(self) -> None:
        verified = self.verify(
            replay_checker=lambda binding, generation_id, nonce, timestamp: True
        )
        safe = verified.as_safe_dict()
        secret_text = self.secret.decode("ascii")

        self.assertNotIn(secret_text, repr(verified))
        self.assertNotIn(secret_text, repr(safe))
        self.assertNotIn(self.request.generation_signature, repr(verified))
        self.assertNotIn(self.request.generation_signature, repr(safe))
        self.assertNotIn(self.request.envelope.signature, repr(verified))
        self.assertNotIn(self.request.envelope.signature, repr(safe))
        self.assertEqual(safe["credentialGenerationId"], self.generation)
        self.assertEqual(safe["dispatchIdentity"]["identitySha256"], self.identity.identity_sha256)

    def test_receiver_adapter_does_not_register_internal_transcribe_route(self) -> None:
        response = route_request("POST", "/internal/transcribe", load_config({}))
        self.assertEqual(response.status, 405)
        self.assertEqual(response.allow, "GET")
        self.assertEqual(response.payload, {"error": "method_not_allowed"})


if __name__ == "__main__":
    unittest.main()
