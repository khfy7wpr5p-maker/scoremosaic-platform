from __future__ import annotations

import base64
from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.external_admission import compose_external_admission
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
from scoremosaic_gateway.external_idempotency import ExternalIdempotencyReservationReceipt
from scoremosaic_gateway.external_rate_limit import (
    EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
    ExternalRateLimitPolicy,
    ExternalRateLimitRule,
    ExternalRateReservationReceipt,
)
from scoremosaic_gateway.safe_intake import SAFE_INTAKE_MEDIA_TYPES
from scoremosaic_gateway.safe_upload_session import (
    SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
    SAFE_UPLOAD_SESSION_OPERATION_ID,
    SafeUploadSessionPolicy,
    SafeUploadSessionReservationReceipt,
    reserve_safe_upload_session,
)
from scoremosaic_gateway.safe_upload_finalization import (
    SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION,
    SafeUploadFinalizationError,
    SafeUploadFinalizationReceipt,
    finalize_safe_upload_session,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg=="
)
JPEG_1X1 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q=="
)


class SafeUploadFinalizationContractTests(unittest.TestCase):
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
                subject_id="private-subject-e4b",
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
        self.session_policy = SafeUploadSessionPolicy(
            version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
            environment="staging",
            session_ttl_seconds=300,
            max_bytes=25 * 1024 * 1024,
            max_pages=120,
            allowed_media_types=SAFE_INTAKE_MEDIA_TYPES,
        )
        self.session = self._reserve_session()

    @staticmethod
    def _rate_receipt(request):
        return ExternalRateReservationReceipt(
            reservation_key=request.reservation_key,
            window_start_epoch_s=request.window_start_epoch_s,
            window_end_epoch_s=request.window_end_epoch_s,
            max_requests=request.max_requests,
            outcome="reserved",
        )

    @staticmethod
    def _idempotency_receipt(request):
        return ExternalIdempotencyReservationReceipt(
            slot_id=request.slot_id,
            request_sha256=request.request_sha256,
            request_bytes=request.request_bytes,
            outcome="reserved",
        )

    def _admission(self):
        return compose_external_admission(
            rate_policy=self.rate_policy,
            principal=self.principal,
            authorization=self.authorization,
            operation_id=self.operation,
            client_idempotency_key="request-key-e4b-01",
            request_payload=b"exact upload-session metadata request",
            observed_at_epoch_s=self.now + 3,
            rate_reserver=self._rate_receipt,
            idempotency_reserver=self._idempotency_receipt,
        )

    @staticmethod
    def _session_receipt(request):
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

    def _reserve_session(self):
        admission = self._admission()
        return reserve_safe_upload_session(
            policy=self.session_policy,
            admission=admission,
            observed_at_epoch_s=admission.evaluated_at_epoch_s,
            reserver=self._session_receipt,
        )

    @staticmethod
    def _receipt_for(request, *, outcome="reserved", finalized_at_epoch_s=None):
        return SafeUploadFinalizationReceipt(
            version=SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION,
            session_id=request.session_id,
            admission_binding_id=request.admission_binding_id,
            principal_id=request.principal_id,
            environment=request.environment,
            operation_id=request.operation_id,
            finalization_id=request.finalization_id,
            document_sha256=request.document_sha256,
            observed_bytes=request.observed_bytes,
            format_id=request.format_id,
            media_type=request.media_type,
            page_count=request.page_count,
            image_width=request.image_width,
            image_height=request.image_height,
            image_pixel_count=request.image_pixel_count,
            finalized_at_epoch_s=(
                request.requested_at_epoch_s
                if finalized_at_epoch_s is None
                else finalized_at_epoch_s
            ),
            outcome=outcome,
        )

    def test_valid_exact_png_is_safe_intake_finalized_without_runtime_authority(self) -> None:
        decision = finalize_safe_upload_session(
            session=self.session,
            payload=PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.now + 4,
            finalizer=self._receipt_for,
        )

        self.assertEqual(decision.version, SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION)
        self.assertEqual(decision.session_id, self.session.session_id)
        self.assertEqual(decision.document_sha256, sha256(PNG_1X1).hexdigest())
        self.assertEqual(decision.observed_bytes, len(PNG_1X1))
        self.assertEqual((decision.format_id, decision.media_type), ("png", "image/png"))
        self.assertEqual(
            (decision.image_width, decision.image_height, decision.image_pixel_count),
            (1, 1, 1),
        )
        self.assertIsNone(decision.page_count)
        self.assertFalse(decision.replayed)
        safe = decision.as_safe_dict()
        self.assertTrue(safe["safeIntakeAccepted"])
        for key in (
            "uploadAllowed",
            "storageWriteAllowed",
            "jobCreationAllowed",
            "operationExecutionAllowed",
            "networkDispatchAllowed",
            "orchestrationAllowed",
        ):
            self.assertIs(safe[key], False)
        self.assertFalse(hasattr(decision, "payload"))
        self.assertFalse(hasattr(decision, "original_filename"))
        with self.assertRaises(FrozenInstanceError):
            decision.media_type = "application/pdf"  # type: ignore[misc]

    def test_invalid_document_never_reaches_finalization_provider(self) -> None:
        calls = []

        def finalizer(request):
            calls.append(request)
            return self._receipt_for(request)

        with self.assertRaises(Exception):
            finalize_safe_upload_session(
                session=self.session,
                payload=b"not-a-supported-document",
                original_filename="scan.png",
                declared_media_type="image/png",
                observed_at_epoch_s=self.now + 4,
                finalizer=finalizer,
            )
        self.assertEqual(calls, [])

    def test_mutable_document_bytes_fail_before_provider(self) -> None:
        calls = []

        def finalizer(request):
            calls.append(request)
            return self._receipt_for(request)

        with self.assertRaises(SafeUploadFinalizationError) as raised:
            finalize_safe_upload_session(
                session=self.session,
                payload=bytearray(PNG_1X1),  # type: ignore[arg-type]
                original_filename="scan.png",
                declared_media_type="image/png",
                observed_at_epoch_s=self.now + 4,
                finalizer=finalizer,
            )
        self.assertEqual(raised.exception.category, "upload_finalization_payload_invalid")
        self.assertEqual(calls, [])

    def test_expired_session_fails_before_safe_intake_or_provider(self) -> None:
        calls = []

        def finalizer(request):
            calls.append(request)
            return self._receipt_for(request)

        with self.assertRaises(SafeUploadFinalizationError) as raised:
            finalize_safe_upload_session(
                session=self.session,
                payload=PNG_1X1,
                original_filename="scan.png",
                declared_media_type="image/png",
                observed_at_epoch_s=self.session.expires_at_epoch_s,
                finalizer=finalizer,
            )
        self.assertEqual(raised.exception.category, "upload_session_expired")
        self.assertEqual(calls, [])

    def test_exact_replay_returns_same_finalization_identity(self) -> None:
        stored = {}

        def finalizer(request):
            previous = stored.get(request.session_id)
            if previous is None:
                stored[request.session_id] = request
                return self._receipt_for(request, outcome="reserved")
            self.assertEqual(previous.finalization_id, request.finalization_id)
            self.assertEqual(previous.document_sha256, request.document_sha256)
            return self._receipt_for(
                previous,
                outcome="replay",
                finalized_at_epoch_s=previous.requested_at_epoch_s,
            )

        first = finalize_safe_upload_session(
            session=self.session,
            payload=PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.now + 4,
            finalizer=finalizer,
        )
        replay = finalize_safe_upload_session(
            session=self.session,
            payload=PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.now + 5,
            finalizer=finalizer,
        )

        self.assertEqual(first.finalization_id, replay.finalization_id)
        self.assertEqual(first.document_sha256, replay.document_sha256)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.finalized_at_epoch_s, replay.finalized_at_epoch_s)

    def test_same_session_different_document_conflicts_fail_closed(self) -> None:
        stored = {}

        def finalizer(request):
            previous = stored.get(request.session_id)
            if previous is None:
                stored[request.session_id] = request
                return self._receipt_for(request, outcome="reserved")
            if previous.document_sha256 != request.document_sha256:
                return self._receipt_for(request, outcome="conflict")
            return self._receipt_for(previous, outcome="replay")

        finalize_safe_upload_session(
            session=self.session,
            payload=PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.now + 4,
            finalizer=finalizer,
        )
        with self.assertRaises(SafeUploadFinalizationError) as raised:
            finalize_safe_upload_session(
                session=self.session,
                payload=JPEG_1X1,
                original_filename="scan.jpg",
                declared_media_type="image/jpeg",
                observed_at_epoch_s=self.now + 5,
                finalizer=finalizer,
            )
        self.assertEqual(raised.exception.category, "upload_finalization_conflict")

    def test_provider_cannot_mutate_session_or_request_authority(self) -> None:
        original_expiry = self.session.expires_at_epoch_s

        def finalizer(request):
            object.__setattr__(self.session, "expires_at_epoch_s", original_expiry + 60)
            object.__setattr__(request, "document_sha256", "f" * 64)
            return self._receipt_for(request)

        with self.assertRaises(SafeUploadFinalizationError) as raised:
            finalize_safe_upload_session(
                session=self.session,
                payload=PNG_1X1,
                original_filename="scan.png",
                declared_media_type="image/png",
                observed_at_epoch_s=self.now + 4,
                finalizer=finalizer,
            )
        self.assertEqual(raised.exception.category, "upload_finalization_authority_mutated")

    def test_finalizer_receives_no_document_bytes_or_filename(self) -> None:
        seen = []

        def finalizer(request):
            seen.append(request)
            self.assertFalse(hasattr(request, "payload"))
            self.assertFalse(hasattr(request, "original_filename"))
            return self._receipt_for(request)

        finalize_safe_upload_session(
            session=self.session,
            payload=PNG_1X1,
            original_filename="private-score-name.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.now + 4,
            finalizer=finalizer,
        )
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
