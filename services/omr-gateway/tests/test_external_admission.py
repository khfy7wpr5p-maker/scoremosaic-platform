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
from scoremosaic_gateway.external_idempotency import (
    ExternalIdempotencyReservationReceipt,
)
from scoremosaic_gateway.external_admission import (
    EXTERNAL_ADMISSION_CONTRACT_VERSION,
    ExternalAdmissionDecision,
    ExternalAdmissionError,
    compose_external_admission,
)


class ExternalAdmissionCompositionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        self.operation = "platform.operation.alpha"
        self.client_key = "request-key-00000001"
        self.payload = b"exact immutable external request bytes"
        self.principal = self.build_principal("private-subject-alpha")
        self.authorization = self.authorization_for(self.principal, self.operation)
        self.rate_policy = self.rate_policy_for(self.operation)

    def build_principal(self, subject_id: str):
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
    def rate_policy_for(operation_id: str) -> ExternalRateLimitPolicy:
        return ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=(ExternalRateLimitRule(operation_id, 60, 5),),
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

    def compose(
        self,
        *,
        rate_reserver=None,
        idempotency_reserver=None,
        principal=None,
        authorization=None,
        rate_policy=None,
        operation_id=None,
        client_idempotency_key=None,
        request_payload=None,
        observed_at_epoch_s=None,
    ) -> ExternalAdmissionDecision:
        return compose_external_admission(
            rate_policy=self.rate_policy if rate_policy is None else rate_policy,
            principal=self.principal if principal is None else principal,
            authorization=self.authorization if authorization is None else authorization,
            operation_id=self.operation if operation_id is None else operation_id,
            client_idempotency_key=(
                self.client_key
                if client_idempotency_key is None
                else client_idempotency_key
            ),
            request_payload=self.payload if request_payload is None else request_payload,
            observed_at_epoch_s=(
                self.now + 3 if observed_at_epoch_s is None else observed_at_epoch_s
            ),
            rate_reserver=(self.rate_receipt if rate_reserver is None else rate_reserver),
            idempotency_reserver=(
                self.idempotency_receipt
                if idempotency_reserver is None
                else idempotency_reserver
            ),
        )

    def test_composition_runs_fresh_rate_before_idempotency_and_returns_bound_evidence(self) -> None:
        order = []
        seen_idempotency = []

        def rate_reserver(request):
            order.append("rate")
            return self.rate_receipt(request)

        def idempotency_reserver(request):
            order.append("idempotency")
            seen_idempotency.append(request)
            return self.idempotency_receipt(request)

        decision = self.compose(
            rate_reserver=rate_reserver,
            idempotency_reserver=idempotency_reserver,
        )
        self.assertIs(type(decision), ExternalAdmissionDecision)
        self.assertEqual(order, ["rate", "idempotency"])
        self.assertEqual(decision.state, "reserved")
        self.assertFalse(decision.replayed)
        self.assertRegex(decision.binding_id, r"^[0-9a-f]{64}$")
        self.assertEqual(decision.idempotency_slot_id, seen_idempotency[0].slot_id)
        self.assertEqual(decision.request_sha256, seen_idempotency[0].request_sha256)
        self.assertEqual(decision.request_bytes, len(self.payload))
        self.assertEqual(decision.evaluated_at_epoch_s, self.now + 3)
        evidence = decision.as_safe_dict()
        for key in (
            "operationExecutionAllowed",
            "uploadAllowed",
            "jobCreationAllowed",
            "networkDispatchAllowed",
            "orchestrationAllowed",
        ):
            self.assertFalse(evidence[key])

    def test_exact_replay_re_evaluates_rate_and_returns_same_binding(self) -> None:
        rate_calls = 0
        idempotency_calls = 0

        def rate_reserver(request):
            nonlocal rate_calls
            rate_calls += 1
            return self.rate_receipt(request)

        def idempotency_reserver(request):
            nonlocal idempotency_calls
            idempotency_calls += 1
            return self.idempotency_receipt(
                request,
                outcome="reserved" if idempotency_calls == 1 else "replay",
            )

        first = self.compose(
            rate_reserver=rate_reserver,
            idempotency_reserver=idempotency_reserver,
        )
        second = self.compose(
            rate_reserver=rate_reserver,
            idempotency_reserver=idempotency_reserver,
            observed_at_epoch_s=self.now + 4,
        )
        self.assertEqual(rate_calls, 2)
        self.assertEqual(idempotency_calls, 2)
        self.assertEqual(first.binding_id, second.binding_id)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)

    def test_rate_limit_stops_before_idempotency(self) -> None:
        idempotency_calls = 0

        def limited(request):
            return self.rate_receipt(request, outcome="limit_reached")

        def idempotency_reserver(request):
            nonlocal idempotency_calls
            idempotency_calls += 1
            return self.idempotency_receipt(request)

        with self.assertRaisesRegex(ExternalAdmissionError, "rate_limited"):
            self.compose(
                rate_reserver=limited,
                idempotency_reserver=idempotency_reserver,
            )
        self.assertEqual(idempotency_calls, 0)

    def test_idempotency_conflict_fails_closed_without_admission_evidence(self) -> None:
        with self.assertRaisesRegex(ExternalAdmissionError, "idempotency_conflict"):
            self.compose(
                idempotency_reserver=lambda request: self.idempotency_receipt(
                    request, outcome="conflict"
                )
            )

    def test_same_exact_request_binding_isolated_across_principal_operation_key_and_payload(self) -> None:
        base = self.compose()

        other_principal = self.build_principal("private-subject-beta")
        other_auth = self.authorization_for(other_principal, self.operation)
        by_principal = self.compose(principal=other_principal, authorization=other_auth)

        beta = "platform.operation.beta"
        beta_auth = self.authorization_for(self.principal, beta)
        by_operation = self.compose(
            authorization=beta_auth,
            rate_policy=self.rate_policy_for(beta),
            operation_id=beta,
        )
        by_key = self.compose(client_idempotency_key="request-key-00000002")
        by_payload = self.compose(request_payload=b"different exact immutable bytes")

        self.assertEqual(
            len(
                {
                    base.binding_id,
                    by_principal.binding_id,
                    by_operation.binding_id,
                    by_key.binding_id,
                    by_payload.binding_id,
                }
            ),
            5,
        )

    def test_caller_cannot_supply_prebuilt_admission_rate_or_binding_authority(self) -> None:
        signature = inspect.signature(compose_external_admission)
        for name in (
            "rate_decision",
            "idempotency_decision",
            "binding_id",
            "idempotency_slot_id",
            "request_sha256",
            "replayed",
            "reserved",
            "operation_execution_allowed",
            "upload_allowed",
        ):
            self.assertNotIn(name, signature.parameters)

    def test_direct_admission_decision_construction_is_forbidden(self) -> None:
        with self.assertRaisesRegex(
            ExternalAdmissionError,
            "admission_decision_construction_forbidden",
        ):
            ExternalAdmissionDecision(
                version=EXTERNAL_ADMISSION_CONTRACT_VERSION,
                environment="staging",
                principal_id=self.principal.principal_id,
                operation_id=self.operation,
                state="reserved",
                replayed=False,
                binding_id="a" * 64,
                idempotency_slot_id="b" * 64,
                request_sha256="c" * 64,
                request_bytes=len(self.payload),
                evaluated_at_epoch_s=self.now + 3,
            )

    def test_safe_evidence_excludes_internal_binding_request_and_private_inputs(self) -> None:
        decision = self.compose()
        serialized = repr(decision.as_safe_dict())
        self.assertNotIn(decision.binding_id, serialized)
        self.assertNotIn(decision.idempotency_slot_id, serialized)
        self.assertNotIn(decision.request_sha256, serialized)
        self.assertNotIn(self.client_key, serialized)
        self.assertNotIn(self.payload.decode("ascii"), serialized)
        self.assertNotIn(self.principal.subject_id, serialized)
        self.assertNotIn("opaque-authentication-credential", serialized)
        self.assertNotIn("provider", serialized.lower())

    def test_provider_failures_are_redacted_and_not_retried(self) -> None:
        rate_calls = 0
        secret = "redis://secret@private-host rate backend exploded"

        def failing_rate(request):
            nonlocal rate_calls
            rate_calls += 1
            raise RuntimeError(secret)

        with self.assertRaises(ExternalAdmissionError) as ctx:
            self.compose(rate_reserver=failing_rate)
        self.assertEqual(rate_calls, 1)
        self.assertEqual(ctx.exception.category, "rate_reservation_unavailable")
        self.assertNotIn(secret, str(ctx.exception))

        idempotency_calls = 0
        secret2 = "postgres://secret@private-host idempotency exploded"

        def failing_idempotency(request):
            nonlocal idempotency_calls
            idempotency_calls += 1
            raise RuntimeError(secret2)

        with self.assertRaises(ExternalAdmissionError) as ctx2:
            self.compose(idempotency_reserver=failing_idempotency)
        self.assertEqual(idempotency_calls, 1)
        self.assertEqual(ctx2.exception.category, "idempotency_unavailable")
        self.assertNotIn(secret2, str(ctx2.exception))

    def test_expired_principal_fails_before_any_backend_callback(self) -> None:
        rate_calls = 0
        idempotency_calls = 0

        def rate_reserver(request):
            nonlocal rate_calls
            rate_calls += 1
            return self.rate_receipt(request)

        def idempotency_reserver(request):
            nonlocal idempotency_calls
            idempotency_calls += 1
            return self.idempotency_receipt(request)

        with self.assertRaisesRegex(ExternalAdmissionError, "principal_expired"):
            self.compose(
                rate_reserver=rate_reserver,
                idempotency_reserver=idempotency_reserver,
                observed_at_epoch_s=self.principal.expires_at_epoch_s,
            )
        self.assertEqual(rate_calls, 0)
        self.assertEqual(idempotency_calls, 0)


if __name__ == "__main__":
    unittest.main()
