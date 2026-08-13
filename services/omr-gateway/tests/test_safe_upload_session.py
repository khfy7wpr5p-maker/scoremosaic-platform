from __future__ import annotations

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
    SAFE_UPLOAD_SESSION_OPERATION_ID,
    SafeUploadSessionError,
    SafeUploadSessionPolicy,
    SafeUploadSessionReservationReceipt,
    reserve_safe_upload_session,
)


class SafeUploadSessionConvergenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        self.operation = SAFE_UPLOAD_SESSION_OPERATION_ID
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
                subject_id="private-subject-upload-convergence",
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
    def rate_receipt(request):
        return ExternalRateReservationReceipt(
            reservation_key=request.reservation_key,
            window_start_epoch_s=request.window_start_epoch_s,
            window_end_epoch_s=request.window_end_epoch_s,
            max_requests=request.max_requests,
            outcome="reserved",
        )

    @staticmethod
    def idempotency_receipt(request):
        return ExternalIdempotencyReservationReceipt(
            slot_id=request.slot_id,
            request_sha256=request.request_sha256,
            request_bytes=request.request_bytes,
            outcome="reserved",
        )

    def admission(self):
        return compose_external_admission(
            rate_policy=self.rate_policy,
            principal=self.principal,
            authorization=self.authorization,
            operation_id=self.operation,
            client_idempotency_key="request-key-convergence-01",
            request_payload=b"exact upload-session metadata request",
            observed_at_epoch_s=self.now + 3,
            rate_reserver=self.rate_receipt,
            idempotency_reserver=self.idempotency_receipt,
        )

    @staticmethod
    def receipt_for(request, *, outcome="reserved"):
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
            created_at_epoch_s=request.requested_at_epoch_s,
            expires_at_epoch_s=request.requested_at_epoch_s + request.session_ttl_seconds,
            outcome=outcome,
        )

    def reserve(self, *, admission=None, observed_at_epoch_s=None, reserver=None):
        checked_admission = self.admission() if admission is None else admission
        return reserve_safe_upload_session(
            policy=self.policy,
            admission=checked_admission,
            observed_at_epoch_s=(
                checked_admission.evaluated_at_epoch_s
                if observed_at_epoch_s is None
                else observed_at_epoch_s
            ),
            reserver=self.receipt_for if reserver is None else reserver,
        )

    def test_stale_admission_cannot_open_a_new_session_later(self) -> None:
        admission = self.admission()
        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_time_mismatch"):
            self.reserve(
                admission=admission,
                observed_at_epoch_s=admission.evaluated_at_epoch_s + 1,
            )

    def test_adapter_cannot_mutate_server_owned_budget_and_self_validate(self) -> None:
        original_max_bytes = self.policy.max_bytes

        def mutating_reserver(request):
            object.__setattr__(request, "max_bytes", original_max_bytes + 1)
            return self.receipt_for(request)

        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_receipt_invalid"):
            self.reserve(reserver=mutating_reserver)
        self.assertEqual(self.policy.max_bytes, original_max_bytes)

    def test_adapter_cannot_mutate_policy_mid_call_and_widen_session_budget(self) -> None:
        original_max_bytes = self.policy.max_bytes

        def mutating_reserver(request):
            object.__setattr__(self.policy, "max_bytes", original_max_bytes + 1)
            object.__setattr__(request, "max_bytes", original_max_bytes + 1)
            return self.receipt_for(request)

        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_authority_mutated"):
            self.reserve(reserver=mutating_reserver)

    def test_adapter_cannot_replace_admission_binding_and_choose_session_identity(self) -> None:
        admission = self.admission()

        def mutating_reserver(request):
            object.__setattr__(admission, "binding_id", "f" * 64)
            object.__setattr__(request, "admission_binding_id", "f" * 64)
            return self.receipt_for(request)

        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_authority_mutated"):
            self.reserve(admission=admission, reserver=mutating_reserver)

    def test_provider_receives_a_defensive_request_copy(self) -> None:
        seen = []

        def mutating_reserver(request):
            seen.append(request)
            object.__setattr__(request, "max_pages", request.max_pages - 1)
            return self.receipt_for(request)

        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_receipt_invalid"):
            self.reserve(reserver=mutating_reserver)
        self.assertEqual(self.policy.max_pages, 120)
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
