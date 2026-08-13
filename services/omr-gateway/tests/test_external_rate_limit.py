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
    ExternalRateDecision,
    ExternalRateLimitError,
    ExternalRateLimitPolicy,
    ExternalRateLimitRule,
    ExternalRateReservationReceipt,
    ExternalRateReservationRequest,
    reserve_external_rate_slot,
)


class ExternalRateSlotReservationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        self.operation = "platform.operation.alpha"
        auth_policy = ExternalAuthPolicy(
            version=EXTERNAL_AUTH_CONTRACT_VERSION,
            environment="staging",
            allowed_provider_ids=("test-provider",),
        )
        self.principal = authenticate_external_principal(
            policy=auth_policy,
            provider_id="test-provider",
            credential=b"opaque-authentication-credential",
            verifier=lambda provider_id, credential: VerifiedExternalIdentity(
                provider_id=provider_id,
                subject_id="private-subject-123",
                issued_at_epoch_s=self.now - 60,
                expires_at_epoch_s=self.now + 600,
            ),
            observed_at_epoch_s=self.now,
        )
        authorization_policy = ExternalAuthorizationPolicy(
            version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
            environment="staging",
            grants=(
                ExternalAuthorizationGrant(
                    principal_id=self.principal.principal_id,
                    operation_id=self.operation,
                ),
            ),
        )
        self.authorization = authorize_external_operation(
            policy=authorization_policy,
            principal=self.principal,
            operation_id=self.operation,
            observed_at_epoch_s=self.now + 1,
        )
        self.policy = ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=(
                ExternalRateLimitRule(
                    operation_id=self.operation,
                    window_seconds=60,
                    max_requests=5,
                ),
            ),
        )

    def reserve(
        self,
        *,
        reserver,
        principal=None,
        authorization=None,
        operation_id=None,
        observed_at_epoch_s=None,
        policy=None,
    ) -> ExternalRateDecision:
        return reserve_external_rate_slot(
            policy=self.policy if policy is None else policy,
            principal=self.principal if principal is None else principal,
            authorization=self.authorization if authorization is None else authorization,
            operation_id=self.operation if operation_id is None else operation_id,
            observed_at_epoch_s=self.now + 2 if observed_at_epoch_s is None else observed_at_epoch_s,
            reserver=reserver,
        )

    @staticmethod
    def reserved(request: ExternalRateReservationRequest) -> ExternalRateReservationReceipt:
        return ExternalRateReservationReceipt(
            reservation_key=request.reservation_key,
            window_start_epoch_s=request.window_start_epoch_s,
            window_end_epoch_s=request.window_end_epoch_s,
            max_requests=request.max_requests,
            outcome="reserved",
        )

    @staticmethod
    def limited(request: ExternalRateReservationRequest) -> ExternalRateReservationReceipt:
        return ExternalRateReservationReceipt(
            reservation_key=request.reservation_key,
            window_start_epoch_s=request.window_start_epoch_s,
            window_end_epoch_s=request.window_end_epoch_s,
            max_requests=request.max_requests,
            outcome="limit_reached",
        )

    def test_exact_allowed_authorization_can_reserve_one_atomic_slot(self) -> None:
        seen: list[ExternalRateReservationRequest] = []

        def reserver(request):
            seen.append(request)
            return self.reserved(request)

        decision = self.reserve(reserver=reserver)

        self.assertIs(type(decision), ExternalRateDecision)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "reserved")
        self.assertEqual(len(seen), 1)
        request = seen[0]
        self.assertIs(type(request), ExternalRateReservationRequest)
        self.assertEqual(request.environment, "staging")
        self.assertEqual(request.principal_id, self.principal.principal_id)
        self.assertEqual(request.operation_id, self.operation)
        self.assertEqual(request.window_start_epoch_s, ((self.now + 2) // 60) * 60)
        self.assertEqual(request.window_end_epoch_s, request.window_start_epoch_s + 60)
        self.assertEqual(request.max_requests, 5)
        self.assertRegex(request.reservation_key, r"^[0-9a-f]{64}$")

        evidence = decision.as_safe_dict()
        self.assertEqual(evidence["rateState"], "allowed")
        self.assertTrue(evidence["rateSlotReserved"])
        self.assertFalse(evidence["operationExecutionAllowed"])
        self.assertFalse(evidence["uploadAllowed"])
        self.assertFalse(evidence["jobCreationAllowed"])
        self.assertFalse(evidence["networkDispatchAllowed"])
        self.assertFalse(evidence["orchestrationAllowed"])

    def test_limit_reached_returns_bounded_rate_limited_decision(self) -> None:
        decision = self.reserve(reserver=self.limited)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "rate_limited")
        evidence = decision.as_safe_dict()
        self.assertEqual(evidence["rateState"], "rate_limited")
        self.assertFalse(evidence["rateSlotReserved"])
        self.assertFalse(evidence["operationExecutionAllowed"])

    def test_reserver_is_called_exactly_once_per_admission_attempt(self) -> None:
        calls = 0

        def reserver(request):
            nonlocal calls
            calls += 1
            return self.reserved(request)

        self.reserve(reserver=reserver)
        self.assertEqual(calls, 1)

    def test_denied_authorization_never_reaches_reserver(self) -> None:
        denied_policy = ExternalAuthorizationPolicy(
            version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
            environment="staging",
            grants=(),
        )
        denied = authorize_external_operation(
            policy=denied_policy,
            principal=self.principal,
            operation_id=self.operation,
            observed_at_epoch_s=self.now + 1,
        )
        calls = 0

        def reserver(request):
            nonlocal calls
            calls += 1
            return self.reserved(request)

        with self.assertRaisesRegex(ExternalRateLimitError, "authorization_required"):
            self.reserve(reserver=reserver, authorization=denied)
        self.assertEqual(calls, 0)

    def test_authorization_identity_operation_and_environment_must_match(self) -> None:
        other_operation = "platform.operation.beta"
        authz_policy = ExternalAuthorizationPolicy(
            version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
            environment="staging",
            grants=(
                ExternalAuthorizationGrant(
                    principal_id=self.principal.principal_id,
                    operation_id=other_operation,
                ),
            ),
        )
        other_decision = authorize_external_operation(
            policy=authz_policy,
            principal=self.principal,
            operation_id=other_operation,
            observed_at_epoch_s=self.now + 1,
        )
        with self.assertRaisesRegex(ExternalRateLimitError, "authorization_mismatch"):
            self.reserve(reserver=self.reserved, authorization=other_decision)

        production_policy = ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="production",
            rules=(
                ExternalRateLimitRule(
                    operation_id=self.operation,
                    window_seconds=60,
                    max_requests=5,
                ),
            ),
        )
        with self.assertRaisesRegex(ExternalRateLimitError, "environment_mismatch"):
            self.reserve(reserver=self.reserved, policy=production_policy)

    def test_rate_policy_is_server_owned_bounded_and_operation_specific(self) -> None:
        invalid_rules = (
            dict(operation_id="*", window_seconds=60, max_requests=5),
            dict(operation_id="platform.*", window_seconds=60, max_requests=5),
            dict(operation_id=self.operation, window_seconds=0, max_requests=5),
            dict(operation_id=self.operation, window_seconds=86_401, max_requests=5),
            dict(operation_id=self.operation, window_seconds=60, max_requests=0),
            dict(operation_id=self.operation, window_seconds=60, max_requests=100_001),
            dict(operation_id=self.operation, window_seconds=True, max_requests=5),
            dict(operation_id=self.operation, window_seconds=60, max_requests=True),
        )
        for kwargs in invalid_rules:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ExternalRateLimitError):
                    ExternalRateLimitRule(**kwargs)

        rule = self.policy.rules[0]
        with self.assertRaisesRegex(ExternalRateLimitError, "rate_policy_invalid"):
            ExternalRateLimitPolicy(
                version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
                environment="staging",
                rules=(rule, rule),
            )

    def test_unknown_operation_fails_closed_before_reserver(self) -> None:
        with self.assertRaisesRegex(ExternalRateLimitError, "rate_policy_operation_missing"):
            self.reserve(reserver=self.reserved, operation_id="platform.operation.beta")

    def test_principal_expiry_is_rechecked_before_reservation(self) -> None:
        calls = 0

        def reserver(request):
            nonlocal calls
            calls += 1
            return self.reserved(request)

        with self.assertRaisesRegex(ExternalRateLimitError, "principal_expired"):
            self.reserve(
                reserver=reserver,
                observed_at_epoch_s=self.principal.expires_at_epoch_s,
            )
        self.assertEqual(calls, 0)

    def test_provider_exception_fails_closed_without_message_leakage(self) -> None:
        secret_message = "redis://secret-token@private-host quota backend exploded"

        def reserver(request):
            raise RuntimeError(secret_message)

        with self.assertRaisesRegex(ExternalRateLimitError, "rate_reservation_unavailable") as ctx:
            self.reserve(reserver=reserver)
        self.assertNotIn(secret_message, str(ctx.exception))
        self.assertNotIn("redis", repr(ctx.exception))

    def test_malformed_or_mismatched_receipt_fails_closed(self) -> None:
        def wrong_key(request):
            return ExternalRateReservationReceipt(
                reservation_key="a" * 64,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s,
                max_requests=request.max_requests,
                outcome="reserved",
            )

        with self.assertRaisesRegex(ExternalRateLimitError, "rate_reservation_invalid"):
            self.reserve(reserver=wrong_key)

        with self.assertRaisesRegex(ExternalRateLimitError, "rate_reservation_invalid"):
            self.reserve(reserver=lambda request: object())

    def test_reservation_key_is_deterministic_and_principal_operation_scoped(self) -> None:
        seen: list[str] = []

        def reserver(request):
            seen.append(request.reservation_key)
            return self.reserved(request)

        self.reserve(reserver=reserver)
        self.reserve(reserver=reserver)
        self.assertEqual(seen[0], seen[1])

    def test_rate_api_has_no_caller_supplied_limit_or_authority_flags(self) -> None:
        signature = inspect.signature(reserve_external_rate_slot)
        for name in (
            "allowed",
            "rate_allowed",
            "rate_limited",
            "limit",
            "window_seconds",
            "max_requests",
            "upload_allowed",
            "job_creation_allowed",
        ):
            self.assertNotIn(name, signature.parameters)

    def test_only_exact_principal_authorization_policy_and_receipt_types_are_authority(self) -> None:
        class DerivedPolicy(ExternalRateLimitPolicy):
            pass

        derived = DerivedPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=self.policy.rules,
        )
        with self.assertRaisesRegex(ExternalRateLimitError, "rate_policy_invalid"):
            self.reserve(reserver=self.reserved, policy=derived)

        with self.assertRaisesRegex(ExternalRateLimitError, "principal_invalid"):
            self.reserve(reserver=self.reserved, principal=object())

        with self.assertRaisesRegex(ExternalRateLimitError, "authorization_invalid"):
            self.reserve(reserver=self.reserved, authorization=object())

    def test_decision_cannot_be_constructed_directly_as_allowed(self) -> None:
        with self.assertRaisesRegex(
            ExternalRateLimitError, "rate_decision_construction_forbidden"
        ):
            ExternalRateDecision(
                version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
                environment="staging",
                principal_id=self.principal.principal_id,
                operation_id=self.operation,
                allowed=True,
                reason="reserved",
            )

    def test_safe_evidence_excludes_subject_credential_policy_and_provider_details(self) -> None:
        decision = self.reserve(reserver=self.reserved)
        serialized = repr(decision.as_safe_dict())
        self.assertNotIn(self.principal.subject_id, serialized)
        self.assertNotIn("opaque-authentication-credential", serialized)
        self.assertNotIn("windowSeconds", serialized)
        self.assertNotIn("maxRequests", serialized)
        self.assertNotIn("reservationKey", serialized)
        self.assertNotIn("provider", serialized.lower())


if __name__ == "__main__":
    unittest.main()
