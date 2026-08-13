from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.external_admission import (
    ExternalAdmissionError,
    compose_external_admission,
)
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
from scoremosaic_gateway.external_idempotency import (
    ExternalIdempotencyReservationReceipt,
)
from scoremosaic_gateway.external_rate_limit import (
    EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
    ExternalRateLimitPolicy,
    ExternalRateLimitRule,
    ExternalRateReservationReceipt,
)


class ExternalAdmissionConvergenceTests(unittest.TestCase):
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

    def build_other_principal(self):
        return authenticate_external_principal(
            policy=ExternalAuthPolicy(
                version=EXTERNAL_AUTH_CONTRACT_VERSION,
                environment="staging",
                allowed_provider_ids=("test-provider",),
            ),
            provider_id="test-provider",
            credential=b"other-opaque-authentication-credential",
            verifier=lambda provider_id, credential: VerifiedExternalIdentity(
                provider_id=provider_id,
                subject_id="private-subject-beta",
                issued_at_epoch_s=self.now - 60,
                expires_at_epoch_s=self.now + 600,
            ),
            observed_at_epoch_s=self.now,
        )

    @staticmethod
    def normal_rate(request):
        return ExternalRateReservationReceipt(
            reservation_key=request.reservation_key,
            window_start_epoch_s=request.window_start_epoch_s,
            window_end_epoch_s=request.window_end_epoch_s,
            max_requests=request.max_requests,
            outcome="reserved",
        )

    @staticmethod
    def normal_idempotency(request):
        return ExternalIdempotencyReservationReceipt(
            slot_id=request.slot_id,
            request_sha256=request.request_sha256,
            request_bytes=request.request_bytes,
            outcome="reserved",
        )

    def compose(self, *, rate_reserver, idempotency_reserver):
        return compose_external_admission(
            rate_policy=self.rate_policy,
            principal=self.principal,
            authorization=self.authorization,
            operation_id=self.operation,
            client_idempotency_key="request-key-00000001",
            request_payload=b"exact immutable external request bytes",
            observed_at_epoch_s=self.now + 3,
            rate_reserver=rate_reserver,
            idempotency_reserver=idempotency_reserver,
        )

    def test_rate_adapter_cannot_mutate_server_derived_request_and_self_validate(self) -> None:
        calls = 0

        def mutating_rate(request):
            nonlocal calls
            calls += 1
            object.__setattr__(request, "reservation_key", "f" * 64)
            return ExternalRateReservationReceipt(
                reservation_key=request.reservation_key,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s,
                max_requests=request.max_requests,
                outcome="reserved",
            )

        with self.assertRaisesRegex(ExternalAdmissionError, "rate_reservation_invalid"):
            self.compose(
                rate_reserver=mutating_rate,
                idempotency_reserver=self.normal_idempotency,
            )
        self.assertEqual(calls, 1)

    def test_idempotency_adapter_cannot_mutate_server_derived_request_and_self_validate(self) -> None:
        calls = 0

        def mutating_idempotency(request):
            nonlocal calls
            calls += 1
            object.__setattr__(request, "slot_id", "f" * 64)
            return ExternalIdempotencyReservationReceipt(
                slot_id=request.slot_id,
                request_sha256=request.request_sha256,
                request_bytes=request.request_bytes,
                outcome="reserved",
            )

        with self.assertRaisesRegex(
            ExternalAdmissionError,
            "idempotency_receipt_invalid",
        ):
            self.compose(
                rate_reserver=self.normal_rate,
                idempotency_reserver=mutating_idempotency,
            )
        self.assertEqual(calls, 1)

    def test_rate_adapter_cannot_replace_authenticated_authority_mid_call(self) -> None:
        other_principal = self.build_other_principal()
        idempotency_calls = 0

        def mutating_rate(request):
            object.__setattr__(self.principal, "subject_id", other_principal.subject_id)
            object.__setattr__(self.principal, "principal_id", other_principal.principal_id)
            object.__setattr__(
                self.authorization,
                "principal_id",
                other_principal.principal_id,
            )
            object.__setattr__(self.rate_policy.rules[0], "max_requests", 6)
            return ExternalRateReservationReceipt(
                reservation_key=request.reservation_key,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s,
                max_requests=request.max_requests,
                outcome="reserved",
            )

        def counting_idempotency(request):
            nonlocal idempotency_calls
            idempotency_calls += 1
            return self.normal_idempotency(request)

        with self.assertRaisesRegex(
            ExternalAdmissionError,
            "admission_authority_mutated",
        ):
            self.compose(
                rate_reserver=mutating_rate,
                idempotency_reserver=counting_idempotency,
            )
        self.assertEqual(idempotency_calls, 0)

    def test_idempotency_adapter_cannot_mutate_authority_mid_call(self) -> None:
        calls = 0

        def mutating_idempotency(request):
            nonlocal calls
            calls += 1
            object.__setattr__(self.principal, "subject_id", "private-subject-mutated")
            object.__setattr__(self.authorization, "allowed", False)
            return ExternalIdempotencyReservationReceipt(
                slot_id=request.slot_id,
                request_sha256=request.request_sha256,
                request_bytes=request.request_bytes,
                outcome="reserved",
            )

        with self.assertRaisesRegex(
            ExternalAdmissionError,
            "admission_authority_mutated",
        ):
            self.compose(
                rate_reserver=self.normal_rate,
                idempotency_reserver=mutating_idempotency,
            )
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
