from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.authenticated_request import (
    MAX_FUTURE_SKEW_SECONDS,
    MAX_REQUEST_AGE_SECONDS,
    REQUEST_AUTH_ALGORITHM,
    REQUEST_AUTH_VERSION,
    RequestAuthError,
    sign_authenticated_request,
    verify_authenticated_request,
)
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
    resolve_engine_credential,
)


class AuthenticatedRequestContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoints = {
            "audiveris": EngineEndpoint(
                "audiveris", "http://audiveris-foundation:8082"
            ),
            "homr": EngineEndpoint("homr", "http://homr-foundation:8080"),
            "clarity": EngineEndpoint(
                "clarity", "http://clarity-foundation:8081"
            ),
        }
        self.timestamp = 1_800_000_000
        self.nonce = "0123456789abcdef0123456789abcdef"
        self.payload = b"deterministic-safe-intake-payload"

    def credential(self, engine: str = "homr", environment: str = "staging"):
        binding = build_engine_auth_binding(self.endpoints[engine], environment)
        secret = (engine + ":" + environment).encode("ascii")
        padded = (secret * (MIN_CREDENTIAL_BYTES // len(secret) + 1))[
            :MIN_CREDENTIAL_BYTES
        ]
        return resolve_engine_credential(binding, lambda key: padded)

    def sign(self, *, engine: str = "homr", environment: str = "staging"):
        return sign_authenticated_request(
            self.credential(engine, environment),
            method="POST",
            path="/internal/v1/engine-request",
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
        )

    def test_valid_envelope_verifies_and_reserves_nonce_after_auth(self) -> None:
        credential = self.credential()
        envelope = sign_authenticated_request(
            credential,
            method="POST",
            path="/internal/v1/engine-request",
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
        )
        seen: list[tuple[str, int]] = []

        def replay_checker(binding, nonce: str, timestamp: int) -> bool:
            self.assertEqual(binding, credential.binding)
            seen.append((nonce, timestamp))
            return True

        verify_authenticated_request(
            credential,
            envelope,
            payload=self.payload,
            now_seconds=self.timestamp,
            replay_checker=replay_checker,
        )

        self.assertEqual(seen, [(self.nonce, self.timestamp)])
        self.assertEqual(envelope.version, REQUEST_AUTH_VERSION)
        self.assertEqual(envelope.algorithm, REQUEST_AUTH_ALGORITHM)

    def test_payload_change_is_rejected_before_replay_reservation(self) -> None:
        credential = self.credential()
        envelope = sign_authenticated_request(
            credential,
            method="POST",
            path="/internal/v1/engine-request",
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
        )
        replay_calls = 0

        def replay_checker(binding, nonce: str, timestamp: int) -> bool:
            nonlocal replay_calls
            replay_calls += 1
            return True

        changed = b"deterministic-safe-intake-payloae"
        self.assertEqual(len(changed), len(self.payload))
        with self.assertRaisesRegex(RequestAuthError, "payload_digest_mismatch"):
            verify_authenticated_request(
                credential,
                envelope,
                payload=changed,
                now_seconds=self.timestamp,
                replay_checker=replay_checker,
            )

        self.assertEqual(replay_calls, 0)

    def test_path_change_invalidates_signature_before_replay_reservation(self) -> None:
        credential = self.credential()
        envelope = self.sign()
        tampered = replace(envelope, path="/internal/v1/other-request")
        replay_calls = 0

        def replay_checker(binding, nonce: str, timestamp: int) -> bool:
            nonlocal replay_calls
            replay_calls += 1
            return True

        with self.assertRaisesRegex(RequestAuthError, "signature_invalid"):
            verify_authenticated_request(
                credential,
                tampered,
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=replay_checker,
            )

        self.assertEqual(replay_calls, 0)

    def test_non_post_method_is_rejected(self) -> None:
        with self.assertRaisesRegex(RequestAuthError, "method_not_allowed"):
            sign_authenticated_request(
                self.credential(),
                method="GET",
                path="/internal/v1/engine-request",
                timestamp=self.timestamp,
                nonce=self.nonce,
                payload=self.payload,
            )

    def test_ambiguous_or_encoded_paths_are_rejected(self) -> None:
        invalid_paths = (
            "internal/v1/request",
            "//internal/v1/request",
            "/internal/../request",
            "/internal/%2e%2e/request",
            "/internal/request?x=1",
            "/internal/request#fragment",
            "/internal\\request",
        )
        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(RequestAuthError, "path_invalid"):
                    sign_authenticated_request(
                        self.credential(),
                        method="POST",
                        path=path,
                        timestamp=self.timestamp,
                        nonce=self.nonce,
                        payload=self.payload,
                    )

    def test_request_version_and_algorithm_tampering_are_rejected(self) -> None:
        credential = self.credential()
        envelope = self.sign()

        with self.assertRaisesRegex(
            RequestAuthError, "request_auth_version_mismatch"
        ):
            verify_authenticated_request(
                credential,
                replace(envelope, version="scoremosaic-s2s-request-v0"),
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=lambda binding, nonce, timestamp: True,
            )

        with self.assertRaisesRegex(
            RequestAuthError, "request_auth_algorithm_mismatch"
        ):
            verify_authenticated_request(
                credential,
                replace(envelope, algorithm="none"),
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=lambda binding, nonce, timestamp: True,
            )

    def test_caller_audience_and_engine_tampering_are_rejected(self) -> None:
        credential = self.credential()
        envelope = self.sign()
        cases = (
            (replace(envelope, caller_identity="other-caller"), "caller_identity_mismatch"),
            (
                replace(envelope, audience_identity="other-audience"),
                "audience_identity_mismatch",
            ),
            (replace(envelope, engine="clarity"), "engine_identity_mismatch"),
        )

        for tampered, category in cases:
            with self.subTest(category=category):
                with self.assertRaisesRegex(RequestAuthError, category):
                    verify_authenticated_request(
                        credential,
                        tampered,
                        payload=self.payload,
                        now_seconds=self.timestamp,
                        replay_checker=lambda binding, nonce, timestamp: True,
                    )

    def test_cross_environment_envelope_is_rejected(self) -> None:
        staging_credential = self.credential(environment="staging")
        production_envelope = self.sign(environment="production")

        with self.assertRaisesRegex(RequestAuthError, "environment_mismatch"):
            verify_authenticated_request(
                staging_credential,
                production_envelope,
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=lambda binding, nonce, timestamp: True,
            )

    def test_credential_key_tampering_is_rejected(self) -> None:
        credential = self.credential()
        envelope = self.sign()
        tampered = replace(envelope, credential_key="foreign-key")

        with self.assertRaisesRegex(RequestAuthError, "credential_key_mismatch"):
            verify_authenticated_request(
                credential,
                tampered,
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=lambda binding, nonce, timestamp: True,
            )

    def test_expired_and_future_timestamps_are_rejected(self) -> None:
        credential = self.credential()
        envelope = self.sign()

        with self.assertRaisesRegex(RequestAuthError, "timestamp_expired"):
            verify_authenticated_request(
                credential,
                envelope,
                payload=self.payload,
                now_seconds=self.timestamp + MAX_REQUEST_AGE_SECONDS + 1,
                replay_checker=lambda binding, nonce, timestamp: True,
            )

        with self.assertRaisesRegex(RequestAuthError, "timestamp_in_future"):
            verify_authenticated_request(
                credential,
                envelope,
                payload=self.payload,
                now_seconds=self.timestamp - MAX_FUTURE_SKEW_SECONDS - 1,
                replay_checker=lambda binding, nonce, timestamp: True,
            )

    def test_nonce_format_is_strict_and_noncanonical_values_are_rejected(self) -> None:
        invalid_nonces = (
            "",
            "A" * 32,
            "g" * 32,
            "0" * 31,
            "0" * 33,
        )
        for nonce in invalid_nonces:
            with self.subTest(nonce=nonce):
                with self.assertRaisesRegex(RequestAuthError, "nonce_invalid"):
                    sign_authenticated_request(
                        self.credential(),
                        method="POST",
                        path="/internal/v1/engine-request",
                        timestamp=self.timestamp,
                        nonce=nonce,
                        payload=self.payload,
                    )

    def test_replayed_nonce_fails_closed(self) -> None:
        credential = self.credential()
        envelope = self.sign()

        with self.assertRaisesRegex(RequestAuthError, "replay_detected"):
            verify_authenticated_request(
                credential,
                envelope,
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=lambda binding, nonce, timestamp: False,
            )

    def test_replay_store_failure_is_mapped_to_stable_error(self) -> None:
        credential = self.credential()
        envelope = self.sign()
        leaked_value = "private-replay-store-diagnostic"

        def replay_checker(binding, nonce: str, timestamp: int) -> bool:
            raise RuntimeError(leaked_value)

        with self.assertRaises(RequestAuthError) as context:
            verify_authenticated_request(
                credential,
                envelope,
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=replay_checker,
            )

        self.assertEqual(context.exception.category, "replay_check_unavailable")
        self.assertNotIn(leaked_value, str(context.exception))

    def test_invalid_signature_is_checked_before_replay_store(self) -> None:
        credential = self.credential()
        envelope = self.sign()
        invalid = replace(envelope, signature="0" * 64)
        replay_calls = 0

        def replay_checker(binding, nonce: str, timestamp: int) -> bool:
            nonlocal replay_calls
            replay_calls += 1
            return True

        with self.assertRaisesRegex(RequestAuthError, "signature_invalid"):
            verify_authenticated_request(
                credential,
                invalid,
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=replay_checker,
            )

        self.assertEqual(replay_calls, 0)

    def test_signature_is_redacted_from_repr_and_safe_diagnostics(self) -> None:
        envelope = self.sign()
        representation = repr(envelope)
        safe = envelope.as_safe_dict()

        self.assertNotIn(envelope.signature, representation)
        self.assertIn("signature=<redacted>", representation)
        self.assertNotIn("signature", safe)
        self.assertTrue(safe["signaturePresent"])

    def test_signing_is_deterministic_for_identical_inputs(self) -> None:
        credential = self.credential()
        first = sign_authenticated_request(
            credential,
            method="POST",
            path="/internal/v1/engine-request",
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
        )
        second = sign_authenticated_request(
            credential,
            method="POST",
            path="/internal/v1/engine-request",
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first.payload_sha256), 64)
        self.assertEqual(len(first.signature), 64)


if __name__ == "__main__":
    unittest.main()
