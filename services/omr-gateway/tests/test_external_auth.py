from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.external_auth import (
    EXTERNAL_AUTH_CONTRACT_VERSION,
    MAX_CREDENTIAL_BYTES,
    AuthenticatedExternalPrincipal,
    ExternalAuthError,
    ExternalAuthPolicy,
    VerifiedExternalIdentity,
    authenticate_external_principal,
)
from scoremosaic_gateway.service_auth import build_engine_auth_binding


class ExternalPrincipalAuthenticationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ExternalAuthPolicy(
            version=EXTERNAL_AUTH_CONTRACT_VERSION,
            environment="staging",
            allowed_provider_ids=("test-provider",),
        )
        self.credential = b"secret-token-material"
        self.now = 2_000_000_000

    def verified_identity(
        self,
        *,
        provider_id: str = "test-provider",
        subject_id: str = "user-123",
        issued_at_epoch_s: int | None = None,
        expires_at_epoch_s: int | None = None,
    ) -> VerifiedExternalIdentity:
        return VerifiedExternalIdentity(
            provider_id=provider_id,
            subject_id=subject_id,
            issued_at_epoch_s=(
                self.now - 60 if issued_at_epoch_s is None else issued_at_epoch_s
            ),
            expires_at_epoch_s=(
                self.now + 300 if expires_at_epoch_s is None else expires_at_epoch_s
            ),
        )

    def authenticate(self, verifier):
        return authenticate_external_principal(
            policy=self.policy,
            provider_id="test-provider",
            credential=self.credential,
            verifier=verifier,
            observed_at_epoch_s=self.now,
        )

    def test_valid_verified_identity_builds_bounded_principal(self) -> None:
        principal = self.authenticate(lambda provider_id, credential: self.verified_identity())

        self.assertIsInstance(principal, AuthenticatedExternalPrincipal)
        self.assertEqual(principal.version, EXTERNAL_AUTH_CONTRACT_VERSION)
        self.assertEqual(principal.environment, "staging")
        self.assertEqual(principal.provider_id, "test-provider")
        self.assertEqual(principal.subject_id, "user-123")
        self.assertEqual(len(principal.principal_id), 64)
        self.assertTrue(all(ch in "0123456789abcdef" for ch in principal.principal_id))

    def test_safe_evidence_contains_no_credential_or_raw_subject(self) -> None:
        secret = b"credential-value-that-must-not-leak"
        principal = authenticate_external_principal(
            policy=self.policy,
            provider_id="test-provider",
            credential=secret,
            verifier=lambda provider_id, credential: self.verified_identity(
                subject_id="private-user-subject"
            ),
            observed_at_epoch_s=self.now,
        )

        evidence = principal.as_safe_dict()
        serialized = repr(evidence)
        self.assertNotIn(secret.decode("ascii"), serialized)
        self.assertNotIn("private-user-subject", serialized)
        self.assertEqual(evidence["principalId"], principal.principal_id)
        self.assertEqual(evidence["providerId"], "test-provider")
        self.assertEqual(evidence["authenticationState"], "authenticated")

    def test_authenticated_principal_grants_no_authority(self) -> None:
        principal = self.authenticate(lambda provider_id, credential: self.verified_identity())
        evidence = principal.as_safe_dict()

        self.assertFalse(evidence["authorizationGranted"])
        self.assertFalse(evidence["uploadAllowed"])
        self.assertFalse(evidence["jobCreationAllowed"])
        self.assertFalse(evidence["networkDispatchAllowed"])
        self.assertFalse(evidence["orchestrationAllowed"])

    def test_authentication_api_has_no_caller_supplied_authenticated_flag(self) -> None:
        signature = inspect.signature(authenticate_external_principal)
        self.assertNotIn("authenticated", signature.parameters)
        self.assertNotIn("authorization_granted", signature.parameters)
        self.assertNotIn("upload_allowed", signature.parameters)

    def test_unknown_provider_fails_before_verifier(self) -> None:
        calls: list[tuple[str, bytes]] = []

        def verifier(provider_id: str, credential: bytes) -> VerifiedExternalIdentity:
            calls.append((provider_id, credential))
            return self.verified_identity(provider_id=provider_id)

        with self.assertRaisesRegex(ExternalAuthError, "provider_not_allowed"):
            authenticate_external_principal(
                policy=self.policy,
                provider_id="unknown-provider",
                credential=self.credential,
                verifier=verifier,
                observed_at_epoch_s=self.now,
            )

        self.assertEqual(calls, [])

    def test_noncanonical_provider_is_rejected(self) -> None:
        for provider_id in ("", "TEST-PROVIDER", " test-provider ", "../provider"):
            with self.subTest(provider_id=provider_id):
                with self.assertRaisesRegex(ExternalAuthError, "provider_invalid"):
                    authenticate_external_principal(
                        policy=self.policy,
                        provider_id=provider_id,
                        credential=self.credential,
                        verifier=lambda provider_id, credential: self.verified_identity(),
                        observed_at_epoch_s=self.now,
                    )

    def test_credential_type_and_size_are_bounded(self) -> None:
        invalid_values = (
            "token-as-text",
            b"",
            b"x" * (MAX_CREDENTIAL_BYTES + 1),
            bytearray(b"x" * (MAX_CREDENTIAL_BYTES + 1)),
        )

        for value in invalid_values:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(ExternalAuthError, "credential_invalid"):
                    authenticate_external_principal(
                        policy=self.policy,
                        provider_id="test-provider",
                        credential=value,
                        verifier=lambda provider_id, credential: self.verified_identity(),
                        observed_at_epoch_s=self.now,
                    )

    def test_credential_subclasses_are_rejected(self) -> None:
        class MisleadingBytes(bytes):
            pass

        with self.assertRaisesRegex(ExternalAuthError, "credential_invalid"):
            authenticate_external_principal(
                policy=self.policy,
                provider_id="test-provider",
                credential=MisleadingBytes(self.credential),
                verifier=lambda provider_id, credential: self.verified_identity(),
                observed_at_epoch_s=self.now,
            )

    def test_released_memoryview_is_rejected_stably(self) -> None:
        released = memoryview(self.credential)
        released.release()

        with self.assertRaises(ExternalAuthError) as context:
            authenticate_external_principal(
                policy=self.policy,
                provider_id="test-provider",
                credential=released,
                verifier=lambda provider_id, credential: self.verified_identity(),
                observed_at_epoch_s=self.now,
            )

        self.assertEqual(context.exception.category, "credential_invalid")
        self.assertEqual(str(context.exception), "credential_invalid")

    def test_verifier_receives_defensive_bytes_copy(self) -> None:
        presented = bytearray(self.credential)
        seen: list[bytes] = []

        def verifier(provider_id: str, credential: bytes) -> VerifiedExternalIdentity:
            seen.append(credential)
            self.assertIs(type(credential), bytes)
            return self.verified_identity()

        authenticate_external_principal(
            policy=self.policy,
            provider_id="test-provider",
            credential=presented,
            verifier=verifier,
            observed_at_epoch_s=self.now,
        )

        presented[:] = b"X" * len(presented)
        self.assertEqual(seen, [self.credential])

    def test_unverifiable_credential_fails_closed(self) -> None:
        with self.assertRaisesRegex(ExternalAuthError, "authentication_failed"):
            self.authenticate(lambda provider_id, credential: None)

    def test_verifier_exception_is_redacted(self) -> None:
        leaked = "provider-secret-diagnostic"

        def verifier(provider_id: str, credential: bytes) -> VerifiedExternalIdentity:
            raise RuntimeError(leaked)

        with self.assertRaises(ExternalAuthError) as context:
            self.authenticate(verifier)

        self.assertEqual(context.exception.category, "authentication_unavailable")
        self.assertNotIn(leaked, str(context.exception))

    def test_verifier_must_return_exact_verified_identity_type(self) -> None:
        internal_binding = build_engine_auth_binding(
            EngineEndpoint("homr", "http://homr-foundation:8080"),
            "staging",
        )

        with self.assertRaisesRegex(ExternalAuthError, "verification_invalid"):
            self.authenticate(lambda provider_id, credential: internal_binding)

        class DerivedVerifiedIdentity(VerifiedExternalIdentity):
            pass

        derived = DerivedVerifiedIdentity(
            provider_id="test-provider",
            subject_id="user-123",
            issued_at_epoch_s=self.now - 10,
            expires_at_epoch_s=self.now + 10,
        )
        with self.assertRaisesRegex(ExternalAuthError, "verification_invalid"):
            self.authenticate(lambda provider_id, credential: derived)

    def test_verified_provider_confusion_is_rejected(self) -> None:
        with self.assertRaisesRegex(ExternalAuthError, "provider_identity_mismatch"):
            self.authenticate(
                lambda provider_id, credential: self.verified_identity(
                    provider_id="other-provider"
                )
            )

    def test_subject_must_be_exact_bounded_canonical_text(self) -> None:
        invalid_subjects = (
            "",
            " user-123 ",
            "user name",
            "user\nname",
            "x" * 129,
        )
        for subject_id in invalid_subjects:
            with self.subTest(subject_id=subject_id):
                with self.assertRaisesRegex(ExternalAuthError, "subject_invalid"):
                    self.authenticate(
                        lambda provider_id, credential, value=subject_id: self.verified_identity(
                            subject_id=value
                        )
                    )

    def test_expired_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ExternalAuthError, "credential_expired"):
            self.authenticate(
                lambda provider_id, credential: self.verified_identity(
                    expires_at_epoch_s=self.now
                )
            )

    def test_future_issued_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ExternalAuthError, "credential_not_yet_valid"):
            self.authenticate(
                lambda provider_id, credential: self.verified_identity(
                    issued_at_epoch_s=self.now + 1
                )
            )

    def test_invalid_verification_time_shape_is_rejected(self) -> None:
        invalid = replace(
            self.verified_identity(),
            issued_at_epoch_s=True,
        )
        with self.assertRaisesRegex(ExternalAuthError, "verification_invalid"):
            self.authenticate(lambda provider_id, credential: invalid)

        inverted = replace(
            self.verified_identity(),
            issued_at_epoch_s=self.now + 100,
            expires_at_epoch_s=self.now + 50,
        )
        with self.assertRaisesRegex(ExternalAuthError, "verification_invalid"):
            self.authenticate(lambda provider_id, credential: inverted)

    def test_policy_rejects_duplicate_or_noncanonical_provider_ids(self) -> None:
        invalid_provider_sets = (
            ("test-provider", "test-provider"),
            ("TEST-PROVIDER",),
            ("../provider",),
            (),
        )
        for providers in invalid_provider_sets:
            with self.subTest(providers=providers):
                with self.assertRaises(ExternalAuthError):
                    ExternalAuthPolicy(
                        version=EXTERNAL_AUTH_CONTRACT_VERSION,
                        environment="staging",
                        allowed_provider_ids=providers,
                    )

    def test_policy_is_environment_and_version_bound(self) -> None:
        with self.assertRaisesRegex(ExternalAuthError, "auth_contract_version_mismatch"):
            ExternalAuthPolicy(
                version="scoremosaic-external-auth-v0",
                environment="staging",
                allowed_provider_ids=("test-provider",),
            )

        with self.assertRaisesRegex(ExternalAuthError, "environment_not_allowed"):
            ExternalAuthPolicy(
                version=EXTERNAL_AUTH_CONTRACT_VERSION,
                environment="dev",
                allowed_provider_ids=("test-provider",),
            )


if __name__ == "__main__":
    unittest.main()
