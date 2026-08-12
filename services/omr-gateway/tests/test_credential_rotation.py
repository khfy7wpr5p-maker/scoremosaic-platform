from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.authenticated_request import (
    MAX_REQUEST_AGE_SECONDS,
    RequestAuthError,
    sign_authenticated_request,
    verify_authenticated_request,
)
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.credential_rotation import (
    CredentialRotationError,
    build_replay_reservation,
    build_rotation_set,
    resolve_engine_credential_generation,
    select_signing_credential,
    select_verification_credential,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    build_dispatch_result_identity,
    require_dispatch_result_identity,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


class CredentialRotationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoint = EngineEndpoint("homr", "http://homr-foundation:8080")
        self.binding = build_engine_auth_binding(self.endpoint, "staging")
        self.current_generation = "gen-2026-08-b"
        self.previous_generation = "gen-2026-08-a"
        self.current_secret = b"C" * MIN_CREDENTIAL_BYTES
        self.previous_secret = b"P" * MIN_CREDENTIAL_BYTES
        self.timestamp = 1_800_000_000
        self.nonce = "0123456789abcdef0123456789abcdef"
        self.payload = b"c2d-generation-bound-payload"

    def resolver(self, credential_key: str, generation_id: str):
        self.assertEqual(credential_key, self.binding.credential_key)
        if generation_id == self.current_generation:
            return self.current_secret
        if generation_id == self.previous_generation:
            return self.previous_secret
        return None

    def credential(self, generation_id: str):
        return resolve_engine_credential_generation(
            self.binding,
            generation_id,
            self.resolver,
        )

    def rotation_set(self, *, previous_valid_until: int | None = None):
        return build_rotation_set(
            current=self.credential(self.current_generation),
            previous=self.credential(self.previous_generation),
            previous_valid_until=(
                self.timestamp + 60
                if previous_valid_until is None
                else previous_valid_until
            ),
        )

    def test_generation_id_is_validated_before_provider_lookup(self) -> None:
        requested: list[tuple[str, str]] = []

        def resolver(credential_key: str, generation_id: str):
            requested.append((credential_key, generation_id))
            return self.current_secret

        invalid = (
            "",
            "CURRENT",
            " current",
            "current ",
            "../current",
            "current/next",
            "current:next",
            "x" * 65,
        )
        for generation_id in invalid:
            with self.subTest(generation_id=generation_id):
                with self.assertRaisesRegex(
                    CredentialRotationError,
                    "credential_generation_invalid",
                ):
                    resolve_engine_credential_generation(
                        self.binding,
                        generation_id,
                        resolver,
                    )

        self.assertEqual(requested, [])

    def test_provider_lookup_is_scoped_by_logical_key_and_generation(self) -> None:
        requested: list[tuple[str, str]] = []

        def resolver(credential_key: str, generation_id: str):
            requested.append((credential_key, generation_id))
            return self.current_secret

        credential = resolve_engine_credential_generation(
            self.binding,
            self.current_generation,
            resolver,
        )

        self.assertEqual(
            requested,
            [(self.binding.credential_key, self.current_generation)],
        )
        self.assertEqual(credential.binding, self.binding)
        self.assertEqual(credential.generation_id, self.current_generation)
        self.assertNotIn(self.current_secret.decode("ascii"), repr(credential))

    def test_rotation_set_requires_distinct_current_and_previous_generations(self) -> None:
        current = self.credential(self.current_generation)

        with self.assertRaisesRegex(
            CredentialRotationError,
            "credential_generation_collision",
        ):
            build_rotation_set(
                current=current,
                previous=current,
                previous_valid_until=self.timestamp + 60,
            )

    def test_previous_generation_requires_bounded_grace_deadline(self) -> None:
        current = self.credential(self.current_generation)
        previous = self.credential(self.previous_generation)

        with self.assertRaisesRegex(
            CredentialRotationError,
            "rotation_grace_invalid",
        ):
            build_rotation_set(
                current=current,
                previous=previous,
                previous_valid_until=None,
            )

        with self.assertRaisesRegex(
            CredentialRotationError,
            "rotation_grace_invalid",
        ):
            build_rotation_set(
                current=current,
                previous=None,
                previous_valid_until=self.timestamp + 60,
            )

    def test_new_signatures_always_use_current_generation(self) -> None:
        rotation = self.rotation_set()
        selected = select_signing_credential(rotation)

        self.assertEqual(selected.generation_id, self.current_generation)
        self.assertEqual(selected.secret_bytes_for_transport(), self.current_secret)

    def test_receiver_selects_exact_generation_without_secret_fallback(self) -> None:
        rotation = self.rotation_set()

        current = select_verification_credential(
            rotation,
            self.current_generation,
            now_seconds=self.timestamp,
        )
        previous = select_verification_credential(
            rotation,
            self.previous_generation,
            now_seconds=self.timestamp,
        )

        self.assertEqual(current.generation_id, self.current_generation)
        self.assertEqual(previous.generation_id, self.previous_generation)

        with self.assertRaisesRegex(
            CredentialRotationError,
            "credential_generation_unknown",
        ):
            select_verification_credential(
                rotation,
                "gen-2026-08-unknown",
                now_seconds=self.timestamp,
            )

    def test_previous_generation_expires_fail_closed_at_deadline(self) -> None:
        deadline = self.timestamp + 60
        rotation = self.rotation_set(previous_valid_until=deadline)

        accepted = select_verification_credential(
            rotation,
            self.previous_generation,
            now_seconds=deadline - 1,
        )
        self.assertEqual(accepted.generation_id, self.previous_generation)

        with self.assertRaisesRegex(
            CredentialRotationError,
            "credential_generation_expired",
        ):
            select_verification_credential(
                rotation,
                self.previous_generation,
                now_seconds=deadline,
            )

    def test_request_signature_binds_credential_generation(self) -> None:
        credential = self.credential(self.current_generation)
        envelope = sign_authenticated_request(
            credential,
            method="POST",
            path="/internal/transcribe",
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
        )

        self.assertEqual(
            envelope.credential_generation_id,
            self.current_generation,
        )
        safe = envelope.as_safe_dict()
        self.assertEqual(
            safe["credentialGenerationId"],
            self.current_generation,
        )

        tampered = replace(
            envelope,
            credential_generation_id=self.previous_generation,
        )
        with self.assertRaisesRegex(
            RequestAuthError,
            "credential_generation_mismatch",
        ):
            verify_authenticated_request(
                credential,
                tampered,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=lambda binding, generation_id, nonce, timestamp: True,
            )

    def test_replay_checker_receives_generation_and_nonce(self) -> None:
        credential = self.credential(self.current_generation)
        envelope = sign_authenticated_request(
            credential,
            method="POST",
            path="/internal/transcribe",
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
        )
        seen: list[tuple[str, str, int]] = []

        def replay_checker(binding, generation_id: str, nonce: str, timestamp: int):
            self.assertEqual(binding, self.binding)
            seen.append((generation_id, nonce, timestamp))
            return True

        verify_authenticated_request(
            credential,
            envelope,
            observed_method="POST",
            observed_path="/internal/transcribe",
            payload=self.payload,
            now_seconds=self.timestamp,
            replay_checker=replay_checker,
        )

        self.assertEqual(
            seen,
            [(self.current_generation, self.nonce, self.timestamp)],
        )

    def test_replay_reservation_key_excludes_timestamp_and_is_generation_scoped(self) -> None:
        first = build_replay_reservation(
            self.binding,
            self.current_generation,
            self.nonce,
            request_timestamp=self.timestamp,
            max_request_age_seconds=MAX_REQUEST_AGE_SECONDS,
        )
        same_nonce_later_timestamp = build_replay_reservation(
            self.binding,
            self.current_generation,
            self.nonce,
            request_timestamp=self.timestamp + 1,
            max_request_age_seconds=MAX_REQUEST_AGE_SECONDS,
        )
        previous_generation = build_replay_reservation(
            self.binding,
            self.previous_generation,
            self.nonce,
            request_timestamp=self.timestamp,
            max_request_age_seconds=MAX_REQUEST_AGE_SECONDS,
        )

        self.assertEqual(first.key, same_nonce_later_timestamp.key)
        self.assertNotEqual(first.key, previous_generation.key)
        self.assertEqual(
            first.expires_at,
            self.timestamp + MAX_REQUEST_AGE_SECONDS,
        )
        self.assertEqual(
            same_nonce_later_timestamp.expires_at,
            self.timestamp + 1 + MAX_REQUEST_AGE_SECONDS,
        )

    def test_result_identity_binds_same_credential_generation(self) -> None:
        plan = build_orchestration_plan(
            job_id="job-c2d-rotation-0001",
            source_artifact_id="artifact-source-c2d-0001",
            source_sha256="1" * 64,
        )
        identity = build_dispatch_identity(plan, "homr")
        credential = self.credential(self.current_generation)
        result_payload = b"<score-partwise version='4.0'/>"
        result = build_dispatch_result_identity(
            credential,
            identity,
            result_payload,
        )

        self.assertEqual(
            result.credential_generation_id,
            self.current_generation,
        )
        require_dispatch_result_identity(
            credential,
            identity,
            result,
            result_payload,
        )

        forged = replace(
            result,
            credential_generation_id=self.previous_generation,
        )
        with self.assertRaisesRegex(
            Exception,
            "result_auth_binding_mismatch",
        ):
            require_dispatch_result_identity(
                credential,
                identity,
                forged,
                result_payload,
            )


if __name__ == "__main__":
    unittest.main()
