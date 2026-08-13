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
    SafeUploadSessionError,
    SafeUploadSessionPolicy,
    SafeUploadSessionReservationReceipt,
    reserve_safe_upload_session,
)


class SafeUploadSessionOperationBindingTests(unittest.TestCase):
    def test_unrelated_admitted_operation_cannot_reserve_upload_session(self) -> None:
        now = 2_000_000_000
        unrelated_operation = "platform.operation.alpha"
        principal = authenticate_external_principal(
            policy=ExternalAuthPolicy(
                version=EXTERNAL_AUTH_CONTRACT_VERSION,
                environment="staging",
                allowed_provider_ids=("test-provider",),
            ),
            provider_id="test-provider",
            credential=b"opaque-authentication-credential",
            verifier=lambda provider_id, credential: VerifiedExternalIdentity(
                provider_id=provider_id,
                subject_id="private-subject-cross-operation",
                issued_at_epoch_s=now - 60,
                expires_at_epoch_s=now + 600,
            ),
            observed_at_epoch_s=now,
        )
        authorization = authorize_external_operation(
            policy=ExternalAuthorizationPolicy(
                version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
                environment="staging",
                grants=(
                    ExternalAuthorizationGrant(
                        principal_id=principal.principal_id,
                        operation_id=unrelated_operation,
                    ),
                ),
            ),
            principal=principal,
            operation_id=unrelated_operation,
            observed_at_epoch_s=now + 1,
        )
        rate_policy = ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=(ExternalRateLimitRule(unrelated_operation, 60, 5),),
        )

        def rate_reserver(request):
            return ExternalRateReservationReceipt(
                reservation_key=request.reservation_key,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s,
                max_requests=request.max_requests,
                outcome="reserved",
            )

        def idempotency_reserver(request):
            return ExternalIdempotencyReservationReceipt(
                slot_id=request.slot_id,
                request_sha256=request.request_sha256,
                request_bytes=request.request_bytes,
                outcome="reserved",
            )

        admission = compose_external_admission(
            rate_policy=rate_policy,
            principal=principal,
            authorization=authorization,
            operation_id=unrelated_operation,
            client_idempotency_key="cross-operation-request-01",
            request_payload=b"unrelated operation request",
            observed_at_epoch_s=now + 3,
            rate_reserver=rate_reserver,
            idempotency_reserver=idempotency_reserver,
        )
        policy = SafeUploadSessionPolicy(
            version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
            environment="staging",
            session_ttl_seconds=300,
            max_bytes=25 * 1024 * 1024,
            max_pages=100,
            allowed_media_types=SAFE_INTAKE_MEDIA_TYPES,
        )

        def session_reserver(request):
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
                outcome="reserved",
            )

        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_operation_mismatch"):
            reserve_safe_upload_session(
                policy=policy,
                admission=admission,
                observed_at_epoch_s=admission.evaluated_at_epoch_s,
                reserver=session_reserver,
            )


if __name__ == "__main__":
    unittest.main()
