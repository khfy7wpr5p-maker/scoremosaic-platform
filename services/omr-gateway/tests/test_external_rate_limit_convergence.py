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
    ExternalRateLimitError,
    ExternalRateLimitPolicy,
    ExternalRateLimitRule,
    ExternalRateReservationReceipt,
    reserve_external_rate_slot,
)


class ExternalRateLimitConvergenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        self.alpha = "platform.operation.alpha"
        self.beta = "platform.operation.beta"
        self.policy = ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=(
                ExternalRateLimitRule(self.alpha, 60, 5),
                ExternalRateLimitRule(self.beta, 60, 5),
            ),
        )

    def principal_for(self, subject_id: str):
        return authenticate_external_principal(
            policy=ExternalAuthPolicy(
                version=EXTERNAL_AUTH_CONTRACT_VERSION,
                environment="staging",
                allowed_provider_ids=("test-provider",),
            ),
            provider_id="test-provider",
            credential=b"opaque-authentication-credential",
            verifier=lambda provider_id, credential: VerifiedExternalIdentity(
                provider_id=provider_id,
                subject_id=subject_id,
                issued_at_epoch_s=self.now - 60,
                expires_at_epoch_s=self.now + 600,
            ),
            observed_at_epoch_s=self.now,
        )

    def authorization_for(self, principal, operation_id: str):
        return authorize_external_operation(
            policy=ExternalAuthorizationPolicy(
                version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
                environment="staging",
                grants=(
                    ExternalAuthorizationGrant(
                        principal_id=principal.principal_id,
                        operation_id=operation_id,
                    ),
                ),
            ),
            principal=principal,
            operation_id=operation_id,
            observed_at_epoch_s=self.now + 1,
        )

    @staticmethod
    def reserved(request):
        return ExternalRateReservationReceipt(
            reservation_key=request.reservation_key,
            window_start_epoch_s=request.window_start_epoch_s,
            window_end_epoch_s=request.window_end_epoch_s,
            max_requests=request.max_requests,
            outcome="reserved",
        )

    def reserve_and_capture_key(self, principal, operation_id: str) -> str:
        keys: list[str] = []

        def reserver(request):
            keys.append(request.reservation_key)
            return self.reserved(request)

        reserve_external_rate_slot(
            policy=self.policy,
            principal=principal,
            authorization=self.authorization_for(principal, operation_id),
            operation_id=operation_id,
            observed_at_epoch_s=self.now + 2,
            reserver=reserver,
        )
        self.assertEqual(len(keys), 1)
        return keys[0]

    def test_same_window_different_operations_have_distinct_server_keys(self) -> None:
        principal = self.principal_for("private-subject-123")
        alpha_key = self.reserve_and_capture_key(principal, self.alpha)
        beta_key = self.reserve_and_capture_key(principal, self.beta)
        self.assertNotEqual(alpha_key, beta_key)

    def test_same_window_different_principals_have_distinct_server_keys(self) -> None:
        first = self.principal_for("private-subject-123")
        second = self.principal_for("private-subject-456")
        first_key = self.reserve_and_capture_key(first, self.alpha)
        second_key = self.reserve_and_capture_key(second, self.alpha)
        self.assertNotEqual(first.principal_id, second.principal_id)
        self.assertNotEqual(first_key, second_key)

    def test_same_window_budget_change_keeps_server_bucket_key_stable(self) -> None:
        principal = self.principal_for("private-subject-123")
        authorization = self.authorization_for(principal, self.alpha)
        requests = []

        def reserver(request):
            requests.append(request)
            return self.reserved(request)

        for max_requests in (5, 3):
            policy = ExternalRateLimitPolicy(
                version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
                environment="staging",
                rules=(ExternalRateLimitRule(self.alpha, 60, max_requests),),
            )
            reserve_external_rate_slot(
                policy=policy,
                principal=principal,
                authorization=authorization,
                operation_id=self.alpha,
                observed_at_epoch_s=self.now + 2,
                reserver=reserver,
            )

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].window_start_epoch_s, requests[1].window_start_epoch_s)
        self.assertEqual(requests[0].window_end_epoch_s, requests[1].window_end_epoch_s)
        self.assertEqual((requests[0].max_requests, requests[1].max_requests), (5, 3))
        self.assertEqual(requests[0].reservation_key, requests[1].reservation_key)

    def test_receipt_window_or_budget_mutation_fails_closed(self) -> None:
        principal = self.principal_for("private-subject-123")
        authorization = self.authorization_for(principal, self.alpha)

        def wrong_window(request):
            return ExternalRateReservationReceipt(
                reservation_key=request.reservation_key,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s + 1,
                max_requests=request.max_requests,
                outcome="reserved",
            )

        with self.assertRaisesRegex(ExternalRateLimitError, "rate_reservation_invalid"):
            reserve_external_rate_slot(
                policy=self.policy,
                principal=principal,
                authorization=authorization,
                operation_id=self.alpha,
                observed_at_epoch_s=self.now + 2,
                reserver=wrong_window,
            )

        def wrong_budget(request):
            return ExternalRateReservationReceipt(
                reservation_key=request.reservation_key,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s,
                max_requests=request.max_requests + 1,
                outcome="reserved",
            )

        with self.assertRaisesRegex(ExternalRateLimitError, "rate_reservation_invalid"):
            reserve_external_rate_slot(
                policy=self.policy,
                principal=principal,
                authorization=authorization,
                operation_id=self.alpha,
                observed_at_epoch_s=self.now + 2,
                reserver=wrong_budget,
            )

    def test_invalid_receipt_is_not_retried_or_fail_open(self) -> None:
        principal = self.principal_for("private-subject-123")
        authorization = self.authorization_for(principal, self.alpha)
        calls = 0

        def invalid_receipt(request):
            nonlocal calls
            calls += 1
            return ExternalRateReservationReceipt(
                reservation_key="a" * 64,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s,
                max_requests=request.max_requests,
                outcome="reserved",
            )

        with self.assertRaisesRegex(ExternalRateLimitError, "rate_reservation_invalid"):
            reserve_external_rate_slot(
                policy=self.policy,
                principal=principal,
                authorization=authorization,
                operation_id=self.alpha,
                observed_at_epoch_s=self.now + 2,
                reserver=invalid_receipt,
            )
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
