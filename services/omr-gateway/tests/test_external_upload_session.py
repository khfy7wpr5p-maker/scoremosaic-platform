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
    SAFE_UPLOAD_SESSION_OPERATION_ID,
    SafeUploadSessionDecision,
    SafeUploadSessionError,
    SafeUploadSessionPolicy,
    SafeUploadSessionReservationReceipt,
    reserve_safe_upload_session,
)


class SafeUploadSessionReservationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        self.operation = SAFE_UPLOAD_SESSION_OPERATION_ID
        self.client_key = "request-key-00000001"
        self.payload = b"exact immutable upload request bytes"
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
                subject_id="private-subject-upload-alpha",
                issued_at_epoch_s=self.now - 60,
                expires_at_epoch_s=self.now + 1_000,
            ),
            observed_at_epoch_s=self.now,
        )
        self.authorization = authorize_external_operation(
            policy=ExternalAuthorizationPolicy(
                version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
                environment="staging",
                grants=(ExternalAuthorizationGrant(
                    principal_id=self.principal.principal_id,
                    operation_id=self.operation,
                ),),
            ),
            principal=self.principal,
            operation_id=self.operation,
            observed_at_epoch_s=self.now + 1,
        )
        self.rate_policy = ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=(ExternalRateLimitRule(self.operation, 60, 10),),
        )
        self.policy = SafeUploadSessionPolicy(
            version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
            environment="staging",
            session_ttl_seconds=300,
            max_bytes=25 * 1024 * 1024,
            max_pages=100,
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
    def idempotency_receipt(request, *, outcome="reserved"):
        return ExternalIdempotencyReservationReceipt(
            slot_id=request.slot_id,
            request_sha256=request.request_sha256,
            request_bytes=request.request_bytes,
            outcome=outcome,
        )

    def admission(self, *, key=None, payload=None, observed=None, outcome="reserved"):
        return compose_external_admission(
            rate_policy=self.rate_policy,
            principal=self.principal,
            authorization=self.authorization,
            operation_id=self.operation,
            client_idempotency_key=self.client_key if key is None else key,
            request_payload=self.payload if payload is None else payload,
            observed_at_epoch_s=self.now + 3 if observed is None else observed,
            rate_reserver=self.rate_receipt,
            idempotency_reserver=lambda request: self.idempotency_receipt(request, outcome=outcome),
        )

    @staticmethod
    def receipt(request, *, outcome="reserved"):
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

    def reserve(self, admission, *, reserver=None):
        return reserve_safe_upload_session(
            policy=self.policy,
            admission=admission,
            observed_at_epoch_s=admission.evaluated_at_epoch_s,
            reserver=self.receipt if reserver is None else reserver,
        )

    def test_exact_admission_reserves_server_derived_bounded_session(self) -> None:
        admission = self.admission()
        decision = self.reserve(admission)
        self.assertIs(type(decision), SafeUploadSessionDecision)
        self.assertRegex(decision.session_id, r"^upload_[0-9a-f]{40}$")
        self.assertEqual(decision.admission_binding_id, admission.binding_id)
        self.assertEqual(decision.created_at_epoch_s, admission.evaluated_at_epoch_s)
        self.assertEqual(decision.expires_at_epoch_s, admission.evaluated_at_epoch_s + 300)
        self.assertFalse(decision.replayed)
        safe = decision.as_safe_dict()
        for key in (
            "uploadAllowed", "operationExecutionAllowed", "jobCreationAllowed",
            "storageWriteAllowed", "networkDispatchAllowed", "orchestrationAllowed",
        ):
            self.assertFalse(safe[key])
        self.assertNotIn("admissionBindingId", safe)
        self.assertNotIn("requestSha256", safe)

    def test_exact_replay_returns_same_session_without_extending_ttl(self) -> None:
        stored = None
        def stateful(request):
            nonlocal stored
            if stored is None:
                stored = self.receipt(request)
                return stored
            return SafeUploadSessionReservationReceipt(
                session_id=stored.session_id,
                admission_binding_id=stored.admission_binding_id,
                principal_id=request.principal_id,
                environment=request.environment,
                operation_id=request.operation_id,
                request_sha256=request.request_sha256,
                request_bytes=request.request_bytes,
                max_bytes=stored.max_bytes,
                max_pages=stored.max_pages,
                allowed_media_types=stored.allowed_media_types,
                created_at_epoch_s=stored.created_at_epoch_s,
                expires_at_epoch_s=stored.expires_at_epoch_s,
                outcome="replay",
            )
        first = self.reserve(self.admission(), reserver=stateful)
        replay = self.reserve(self.admission(observed=self.now + 10, outcome="replay"), reserver=stateful)
        self.assertEqual(first.session_id, replay.session_id)
        self.assertEqual(first.created_at_epoch_s, replay.created_at_epoch_s)
        self.assertEqual(first.expires_at_epoch_s, replay.expires_at_epoch_s)
        self.assertTrue(replay.replayed)

    def test_session_identity_isolated_by_exact_admission_binding(self) -> None:
        first = self.reserve(self.admission())
        by_key = self.reserve(self.admission(key="request-key-00000002"))
        by_payload = self.reserve(self.admission(payload=b"different immutable request bytes"))
        self.assertEqual(len({first.session_id, by_key.session_id, by_payload.session_id}), 3)

    def test_expired_replay_fails_closed(self) -> None:
        admission = self.admission()
        def expired(request):
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
                created_at_epoch_s=request.requested_at_epoch_s - 301,
                expires_at_epoch_s=request.requested_at_epoch_s - 1,
                outcome="replay",
            )
        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_expired"):
            self.reserve(admission, reserver=expired)

    def test_malformed_mismatched_and_provider_failure_fail_closed(self) -> None:
        admission = self.admission()
        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_unavailable"):
            self.reserve(admission, reserver=lambda request: (_ for _ in ()).throw(RuntimeError("private backend")))
        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_receipt_invalid"):
            self.reserve(admission, reserver=lambda request: object())
        def mismatch(request):
            receipt = self.receipt(request)
            object.__setattr__(receipt, "session_id", "upload_" + "f" * 40)
            return receipt
        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_receipt_invalid"):
            self.reserve(admission, reserver=mismatch)

    def test_callback_is_single_atomic_seam_and_direct_authority_cannot_be_forged(self) -> None:
        calls = 0
        def reserver(request):
            nonlocal calls
            calls += 1
            return self.receipt(request)
        admission = self.admission()
        self.reserve(admission, reserver=reserver)
        self.assertEqual(calls, 1)
        with self.assertRaisesRegex(SafeUploadSessionError, "upload_session_decision_construction_forbidden"):
            SafeUploadSessionDecision(
                version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
                environment=admission.environment,
                principal_id=admission.principal_id,
                operation_id=admission.operation_id,
                state="reserved",
                replayed=False,
                session_id="upload_" + "a" * 40,
                admission_binding_id=admission.binding_id,
                request_sha256=admission.request_sha256,
                request_bytes=admission.request_bytes,
                created_at_epoch_s=admission.evaluated_at_epoch_s,
                expires_at_epoch_s=admission.evaluated_at_epoch_s + 300,
            )

    def test_public_api_has_no_caller_supplied_session_authority(self) -> None:
        signature = inspect.signature(reserve_safe_upload_session)
        for name in ("session_id", "created_at_epoch_s", "expires_at_epoch_s", "upload_allowed", "storage_write_allowed"):
            self.assertNotIn(name, signature.parameters)


if __name__ == "__main__":
    unittest.main()
