from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.external_auth import (
    EXTERNAL_AUTH_CONTRACT_VERSION,
    ExternalAuthPolicy,
    VerifiedExternalIdentity,
    authenticate_external_principal,
)
from scoremosaic_gateway.external_authorization import (
    EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
    ExternalAuthorizationGrant,
    ExternalAuthorizationPolicy,
    authorize_external_operation,
)
from scoremosaic_gateway.external_rate_limit import (
    EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
    ExternalRateLimitPolicy,
    ExternalRateLimitRule,
    ExternalRateReservationReceipt,
)
from scoremosaic_gateway.external_idempotency import ExternalIdempotencyReservationReceipt
from scoremosaic_gateway.external_admission import compose_external_admission
from scoremosaic_gateway.safe_intake import SAFE_INTAKE_MEDIA_TYPES
from scoremosaic_gateway.safe_upload_session import (
    SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
    SafeUploadSessionDecision,
    SafeUploadSessionError,
    SafeUploadSessionPolicy,
    SafeUploadSessionReservationReceipt,
    reserve_safe_upload_session,
)


class SafeUploadSessionReservationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        self.operation = "platform.operation.alpha"
        self.principal = authenticate_external_principal(
            policy=ExternalAuthPolicy(
                version=EXTERNAL_AUTH_CONTRACT_VERSION,
                environment="staging",
                allowed_provider_ids=("test-provider",),
            ),
            provider_id="test-provider",
            credential=b"opaque-authentication-credential",
            verifier=lambda provider_id, credential: VerifiedExternalIdentity(
                provider_id=provider_id,
                subject_id="private-subject-alpha",
                issued_at_epoch_s=self.now - 60,
                expires_at_epoch_s=self.now + 600,
            ),
            observed_at_epoch_s=self.now,
        )
        self.authorization = authorize_external_operation(
            policy=ExternalAuthorizationPolicy(
                version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
                environment="staging",
                grants=(
                    ExternalAuthorizationGrant(
                        principal_id=self.principal.principal_id,
                        operation_id=self.operation,
                    ),
                ),
            ),
            principal=self.principal,
            operation_id=self.operation,
            observed_at_epoch_s=self.now + 1,
        )
        self.rate_policy = ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=(ExternalRateLimitRule(self.operation, 60, 5),),
        )
        self.policy = SafeUploadSessionPolicy(
            version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
            environment="staging",
            session_ttl_seconds=300,
            max_bytes=25 * 1024 * 1024,
            max_pages=120,
            allowed_media_types=SAFE_INTAKE_MEDIA_TYPES,
        )

    @staticmethod
    def rate_receipt(request, outcome: str = "reserved"):
        return ExternalRateReservationReceipt(
            reservation_key=request.reservation_key,
            window_start_epoch_s=request.window_start_epoch_s,
            window_end_epoch_s=request.window_end_epoch_s,
            max_requests=request.max_requests,
            outcome=outcome,
        )

    @staticmethod
    def idempotency_receipt(request, outcome: str = "reserved"):
        return ExternalIdempotencyReservationReceipt(
            slot_id=request.slot_id,
            request_sha256=request.request_sha256,
            request_bytes=request.request_bytes,
            outcome=outcome,
        )

    def admission(self, *, key: str = "request-key-00000001", payload: bytes = b"metadata"):
        return compose_external_admission(
            rate_policy=self.rate_policy,
            principal=self.principal,
            authorization=self.authorization,
            operation_id=self.operation,
            client_idempotency_key=key,
            request_payload=payload,
            observed_at_epoch_s=self.now + 3,
            rate_reserver=self.rate_receipt,
            idempotency_reserver=self.idempotency_receipt,
        )

    @staticmethod
    def receipt(request, *, outcome: str = "reserved", created_at: int | None = None):
        created = request.requested_at_epoch_s if created_at is None else created_at
        return SafeUploadSessionReservationReceipt(
            session_id=request.session_id,
            admission_binding_id=request.admission_binding_id,
            principal_id=request.principal_id,
            environment=request.environment,
            operation_id=request.operation_id,
            request_sha256=request.request_sha256,
            request_bytes=request.request_bytes,
            max_bytes=request.max_bytes,
            max_pages=request.max_pages,
            allowed_media_types=request.allowed_media_types,
            created_at_epoch_s=created,
            expires_at_epoch_s=created + request.session_ttl_seconds,
            outcome=outcome,
        )

    def reserve(self, *, admission=None, reserver=None, observed_at_epoch_s=None):
        decision = self.admission() if admission is None else admission
        return reserve_safe_upload_session(
            policy=self.policy,
            admission=decision,
            observed_at_epoch_s=(
                decision.evaluated_at_epoch_s
                if observed_at_epoch_s is None
                else observed_at_epoch_s
            ),
            reserver=self.receipt if reserver is None else reserver,
        )

    def test_reserved_session_is_server_derived_and_carries_no_runtime_authority(self) -> None:
        seen = []

        def reserver(request):
            seen.append(request)
            return self.receipt(request)

        decision = self.reserve(reserver=reserver)
        self.assertIs(type(decision), SafeUploadSessionDecision)
        self.assertEqual(decision.state, "reserved")
        self.assertFalse(decision.replayed)
        self.assertRegex(decision.session_id, r"^upload_[0-9a-f]{40}$")
        self.assertEqual(decision.admission_binding_id, seen[0].admission_binding_id)
        self.assertEqual(decision.created_at_epoch_s, self.now + 3)
        self.assertEqual(decision.expires_at_epoch_s, self.now + 303)
        evidence = decision.as_safe_dict()
        for key in (
            "uploadAllowed",
            "operationExecutionAllowed",
            "jobCreationAllowed",
            "storageWriteAllowed",
            "networkDispatchAllowed",
            "orchestrationAllowed",
        ):
            self.assertFalse(evidence[key])

    def test_exact_replay_returns_same_session_and_original_expiry_without_extension(self) -> None:
        stored = {}

        def reserver(request):
            if not stored:
                receipt = self.receipt(request)
                stored["receipt"] = receipt
                return receipt
            first = stored["receipt"]
            return SafeUploadSessionReservationReceipt(
                session_id=first.session_id,
                admission_binding_id=first.admission_binding_id,
                principal_id=first.principal_id,
                environment=first.environment,
                operation_id=first.operation_id,
                request_sha256=first.request_sha256,
                request_bytes=first.request_bytes,
                max_bytes=first.max_bytes,
                max_pages=first.max_pages,
                allowed_media_types=first.allowed_media_types,
                created_at_epoch_s=first.created_at_epoch_s,
                expires_at_epoch_s=first.expires_at_epoch_s,
                outcome="replay",
            )

        admission = self.admission()
        first = self.reserve(admission=admission, reserver=reserver)
        replay = self.reserve(admission=admission, reserver=reserver)
        self.assertEqual(first.session_id, replay.session_id)
        self.assertEqual(first.created_at_epoch_s, replay.created_at_epoch_s)
        self.assertEqual(first.expires_at_epoch_s, replay.expires_at_epoch_s)
        self.assertTrue(replay.replayed)

    def test_different_exact_admission_binding_produces_different_session(self) -> None:
        first = self.reserve(admission=self.admission(key="request-key-00000001"))
        second = self.reserve(admission=self.admission(key="request-key-00000002"))
        third = self.reserve(admission=self.admission(payload=b"different metadata"))
        self.assertEqual(len({first.session_id, second.session_id, third.session_id}), 3)

    def test_expired_replay_fails_closed_and_cannot_extend_ttl(self) -> None:
        admission = self.admission()
        old_created = admission.evaluated_at_epoch_s - self.policy.session_ttl_seconds

        def expired(request):
            return self.receipt(request, outcome="replay", created_at=old_created)

        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_expired"):
            self.reserve(admission=admission, reserver=expired)

    def test_receipt_cannot_change_session_identity_or_policy_budget(self) -> None:
        def wrong_session(request):
            receipt = self.receipt(request)
            object.__setattr__(receipt, "session_id", "upload_" + "f" * 40)
            return receipt

        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_receipt_invalid"):
            self.reserve(reserver=wrong_session)

        def wrong_budget(request):
            receipt = self.receipt(request)
            object.__setattr__(receipt, "max_bytes", request.max_bytes + 1)
            return receipt

        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_receipt_invalid"):
            self.reserve(reserver=wrong_budget)

    def test_provider_failure_fails_closed_without_private_error_text(self) -> None:
        def broken(_request):
            raise RuntimeError("redis://private-host:6379 secret-value")

        with self.assertRaises(SafeUploadSessionError) as caught:
            self.reserve(reserver=broken)
        self.assertEqual(caught.exception.category, "upload_session_unavailable")
        self.assertNotIn("private-host", str(caught.exception))
        self.assertNotIn("secret-value", str(caught.exception))

    def test_callback_is_atomic_single_invocation(self) -> None:
        calls = 0

        def reserver(request):
            nonlocal calls
            calls += 1
            return self.receipt(request)

        self.reserve(reserver=reserver)
        self.assertEqual(calls, 1)

    def test_admission_time_must_match_the_exact_request_evaluation(self) -> None:
        admission = self.admission()
        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_time_mismatch"):
            self.reserve(
                admission=admission,
                observed_at_epoch_s=admission.evaluated_at_epoch_s + 1,
            )

    def test_policy_is_bounded_and_uses_only_safe_intake_media_types(self) -> None:
        with self.assertRaises(SafeUploadSessionError):
            SafeUploadSessionPolicy(
                version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
                environment="staging",
                session_ttl_seconds=0,
                max_bytes=25 * 1024 * 1024,
                max_pages=120,
                allowed_media_types=SAFE_INTAKE_MEDIA_TYPES,
            )
        with self.assertRaises(SafeUploadSessionError):
            SafeUploadSessionPolicy(
                version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
                environment="staging",
                session_ttl_seconds=300,
                max_bytes=25 * 1024 * 1024,
                max_pages=120,
                allowed_media_types=("application/octet-stream",),
            )

    def test_decision_direct_construction_and_caller_authority_parameters_are_forbidden(self) -> None:
        with self.assertRaisesRegex(
            SafeUploadSessionError,
            "upload_session_decision_construction_forbidden",
        ):
            SafeUploadSessionDecision(
                version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
                environment="staging",
                principal_id=self.principal.principal_id,
                operation_id=self.operation,
                state="reserved",
                replayed=False,
                session_id="upload_" + "a" * 40,
                admission_binding_id="b" * 64,
                request_sha256="c" * 64,
                request_bytes=8,
                created_at_epoch_s=self.now,
                expires_at_epoch_s=self.now + 300,
            )

        signature = inspect.signature(reserve_safe_upload_session)
        for name in (
            "upload_allowed",
            "storage_write_allowed",
            "job_creation_allowed",
            "session_id",
            "expires_at_epoch_s",
        ):
            self.assertNotIn(name, signature.parameters)


if __name__ == "__main__":
    unittest.main()
