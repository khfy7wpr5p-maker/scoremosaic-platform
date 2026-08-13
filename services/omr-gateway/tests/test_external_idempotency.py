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
    reserve_external_rate_slot,
)
from scoremosaic_gateway.external_idempotency import (
    EXTERNAL_IDEMPOTENCY_CONTRACT_VERSION,
    ExternalIdempotencyDecision,
    ExternalIdempotencyError,
    ExternalIdempotencyReservationReceipt,
    ExternalIdempotencyReservationRequest,
    reserve_external_idempotency_slot,
)


class ExternalRequestIdempotencyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 2_000_000_000
        self.operation = "platform.operation.alpha"
        self.client_key = "request-key-00000001"
        self.payload = b"exact immutable external request bytes"
        self.principal = self.build_principal("private-subject-alpha")
        self.authorization = self.authorization_for(self.principal, self.operation)
        self.rate_decision = self.rate_for(
            self.principal,
            self.authorization,
            self.operation,
        )

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

    def rate_for(self, principal, authorization, operation_id: str):
        policy = ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=(
                ExternalRateLimitRule(
                    operation_id=operation_id,
                    window_seconds=60,
                    max_requests=5,
                ),
            ),
        )

        def reserver(request):
            return ExternalRateReservationReceipt(
                reservation_key=request.reservation_key,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s,
                max_requests=request.max_requests,
                outcome="reserved",
            )

        return reserve_external_rate_slot(
            policy=policy,
            principal=principal,
            authorization=authorization,
            operation_id=operation_id,
            observed_at_epoch_s=self.now + 2,
            reserver=reserver,
        )

    @staticmethod
    def receipt(
        request: ExternalIdempotencyReservationRequest,
        outcome: str = "reserved",
    ) -> ExternalIdempotencyReservationReceipt:
        return ExternalIdempotencyReservationReceipt(
            slot_id=request.slot_id,
            request_sha256=request.request_sha256,
            request_bytes=request.request_bytes,
            outcome=outcome,
        )

    def reserve(
        self,
        *,
        reserver,
        principal=None,
        authorization=None,
        rate_decision=None,
        operation_id=None,
        client_idempotency_key=None,
        request_payload=None,
        observed_at_epoch_s=None,
    ) -> ExternalIdempotencyDecision:
        return reserve_external_idempotency_slot(
            principal=self.principal if principal is None else principal,
            authorization=self.authorization if authorization is None else authorization,
            rate_decision=self.rate_decision if rate_decision is None else rate_decision,
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
            reserver=reserver,
        )

    def test_first_exact_request_reserves_one_atomic_external_slot(self) -> None:
        seen = []

        def reserver(request):
            seen.append(request)
            return self.receipt(request)

        decision = self.reserve(reserver=reserver)
        self.assertIs(type(decision), ExternalIdempotencyDecision)
        self.assertEqual(decision.state, "reserved")
        self.assertFalse(decision.replayed)
        self.assertEqual(len(seen), 1)
        request = seen[0]
        self.assertIs(type(request), ExternalIdempotencyReservationRequest)
        self.assertEqual(request.environment, "staging")
        self.assertEqual(request.principal_id, self.principal.principal_id)
        self.assertEqual(request.operation_id, self.operation)
        self.assertRegex(request.slot_id, r"^[0-9a-f]{64}$")
        self.assertRegex(request.request_sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(request.request_bytes, len(self.payload))
        evidence = decision.as_safe_dict()
        self.assertEqual(evidence["idempotencyState"], "reserved")
        self.assertFalse(evidence["replayed"])
        for key in (
            "operationExecutionAllowed",
            "uploadAllowed",
            "jobCreationAllowed",
            "networkDispatchAllowed",
            "orchestrationAllowed",
        ):
            self.assertFalse(evidence[key])

    def test_exact_replay_returns_replay_evidence_without_second_operation_authority(self) -> None:
        decision = self.reserve(
            reserver=lambda request: self.receipt(request, outcome="replay")
        )
        self.assertEqual(decision.state, "replay")
        self.assertTrue(decision.replayed)
        evidence = decision.as_safe_dict()
        self.assertTrue(evidence["replayed"])
        self.assertFalse(evidence["operationExecutionAllowed"])
        self.assertFalse(evidence["jobCreationAllowed"])

    def test_same_client_key_different_request_conflict_fails_closed(self) -> None:
        first = []
        second = []

        self.reserve(
            reserver=lambda request: first.append(request) or self.receipt(request)
        )
        with self.assertRaisesRegex(ExternalIdempotencyError, "idempotency_conflict"):
            self.reserve(
                request_payload=b"different exact request bytes",
                reserver=lambda request: second.append(request)
                or self.receipt(request, outcome="conflict"),
            )
        self.assertEqual(first[0].slot_id, second[0].slot_id)
        self.assertNotEqual(first[0].request_sha256, second[0].request_sha256)

    def test_slot_is_deterministic_for_exact_principal_operation_and_client_key(self) -> None:
        seen = []

        def reserver(request):
            seen.append(request)
            return self.receipt(request)

        self.reserve(reserver=reserver)
        self.reserve(reserver=reserver)
        self.assertEqual(seen[0].slot_id, seen[1].slot_id)
        self.assertEqual(seen[0].request_sha256, seen[1].request_sha256)

    def test_same_client_key_isolated_across_principals_and_operations(self) -> None:
        seen = []

        def reserver(request):
            seen.append(request)
            return self.receipt(request)

        self.reserve(reserver=reserver)

        other_principal = self.build_principal("private-subject-beta")
        other_auth = self.authorization_for(other_principal, self.operation)
        other_rate = self.rate_for(other_principal, other_auth, self.operation)
        self.reserve(
            reserver=reserver,
            principal=other_principal,
            authorization=other_auth,
            rate_decision=other_rate,
        )

        beta = "platform.operation.beta"
        beta_auth = self.authorization_for(self.principal, beta)
        beta_rate = self.rate_for(self.principal, beta_auth, beta)
        self.reserve(
            reserver=reserver,
            authorization=beta_auth,
            rate_decision=beta_rate,
            operation_id=beta,
        )

        self.assertEqual(len({request.slot_id for request in seen}), 3)

    def test_authorization_and_rate_evidence_must_exactly_match_request_identity(self) -> None:
        beta = "platform.operation.beta"
        beta_auth = self.authorization_for(self.principal, beta)
        beta_rate = self.rate_for(self.principal, beta_auth, beta)

        with self.assertRaisesRegex(ExternalIdempotencyError, "authorization_mismatch"):
            self.reserve(reserver=self.receipt, authorization=beta_auth)
        with self.assertRaisesRegex(ExternalIdempotencyError, "rate_mismatch"):
            self.reserve(reserver=self.receipt, rate_decision=beta_rate)

        other_principal = self.build_principal("private-subject-gamma")
        other_auth = self.authorization_for(other_principal, self.operation)
        other_rate = self.rate_for(other_principal, other_auth, self.operation)
        with self.assertRaisesRegex(ExternalIdempotencyError, "principal_mismatch"):
            self.reserve(
                reserver=self.receipt,
                principal=other_principal,
                authorization=self.authorization,
                rate_decision=other_rate,
            )

    def test_denied_or_rate_limited_evidence_never_reaches_reserver(self) -> None:
        denied = authorize_external_operation(
            policy=ExternalAuthorizationPolicy(
                version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
                environment="staging",
                grants=(),
            ),
            principal=self.principal,
            operation_id=self.operation,
            observed_at_epoch_s=self.now + 1,
        )

        rate_policy = ExternalRateLimitPolicy(
            version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
            environment="staging",
            rules=(ExternalRateLimitRule(self.operation, 60, 5),),
        )

        def limited(request):
            return ExternalRateReservationReceipt(
                reservation_key=request.reservation_key,
                window_start_epoch_s=request.window_start_epoch_s,
                window_end_epoch_s=request.window_end_epoch_s,
                max_requests=request.max_requests,
                outcome="limit_reached",
            )

        limited_rate = reserve_external_rate_slot(
            policy=rate_policy,
            principal=self.principal,
            authorization=self.authorization,
            operation_id=self.operation,
            observed_at_epoch_s=self.now + 2,
            reserver=limited,
        )
        calls = 0

        def reserver(request):
            nonlocal calls
            calls += 1
            return self.receipt(request)

        with self.assertRaisesRegex(ExternalIdempotencyError, "authorization_required"):
            self.reserve(reserver=reserver, authorization=denied)
        with self.assertRaisesRegex(ExternalIdempotencyError, "rate_required"):
            self.reserve(reserver=reserver, rate_decision=limited_rate)
        self.assertEqual(calls, 0)

    def test_principal_expiry_is_rechecked_before_idempotency_reservation(self) -> None:
        calls = 0

        def reserver(request):
            nonlocal calls
            calls += 1
            return self.receipt(request)

        with self.assertRaisesRegex(ExternalIdempotencyError, "principal_expired"):
            self.reserve(
                reserver=reserver,
                observed_at_epoch_s=self.principal.expires_at_epoch_s,
            )
        self.assertEqual(calls, 0)

    def test_client_key_is_exact_bounded_opaque_text_and_not_normalized(self) -> None:
        invalid = (
            "",
            "short",
            "x" * 129,
            "contains space",
            "contains\nnewline",
            "ünicode-key-0001",
            123,
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ExternalIdempotencyError, "idempotency_key_invalid"):
                    self.reserve(reserver=self.receipt, client_idempotency_key=value)

        seen = []

        def reserver(request):
            seen.append(request.slot_id)
            return self.receipt(request)

        self.reserve(reserver=reserver, client_idempotency_key="Opaque-Key-00000001")
        self.reserve(reserver=reserver, client_idempotency_key="opaque-key-00000001")
        self.assertNotEqual(seen[0], seen[1])

    def test_request_payload_must_be_exact_immutable_bounded_bytes(self) -> None:
        for value in (bytearray(b"mutable"), memoryview(b"view"), "text", object()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(ExternalIdempotencyError, "request_payload_invalid"):
                    self.reserve(reserver=self.receipt, request_payload=value)

    def test_reserver_is_called_exactly_once_and_provider_failure_is_redacted(self) -> None:
        calls = 0
        secret_message = "postgres://secret@private-host idempotency backend exploded"

        def failing(request):
            nonlocal calls
            calls += 1
            raise RuntimeError(secret_message)

        with self.assertRaisesRegex(ExternalIdempotencyError, "idempotency_unavailable") as ctx:
            self.reserve(reserver=failing)
        self.assertEqual(calls, 1)
        self.assertNotIn(secret_message, str(ctx.exception))
        self.assertNotIn("postgres", repr(ctx.exception).lower())

    def test_malformed_or_mismatched_receipt_fails_closed_without_retry(self) -> None:
        calls = 0

        def wrong_digest(request):
            nonlocal calls
            calls += 1
            return ExternalIdempotencyReservationReceipt(
                slot_id=request.slot_id,
                request_sha256="a" * 64,
                request_bytes=request.request_bytes,
                outcome="reserved",
            )

        with self.assertRaisesRegex(ExternalIdempotencyError, "idempotency_receipt_invalid"):
            self.reserve(reserver=wrong_digest)
        self.assertEqual(calls, 1)

        with self.assertRaisesRegex(ExternalIdempotencyError, "idempotency_receipt_invalid"):
            self.reserve(reserver=lambda request: object())

    def test_decision_cannot_be_constructed_directly_as_reserved_or_replay(self) -> None:
        for state, replayed in (("reserved", False), ("replay", True)):
            with self.subTest(state=state):
                with self.assertRaisesRegex(
                    ExternalIdempotencyError,
                    "idempotency_decision_construction_forbidden",
                ):
                    ExternalIdempotencyDecision(
                        version=EXTERNAL_IDEMPOTENCY_CONTRACT_VERSION,
                        environment="staging",
                        principal_id=self.principal.principal_id,
                        operation_id=self.operation,
                        state=state,
                        replayed=replayed,
                    )

    def test_idempotency_api_has_no_caller_supplied_slot_digest_or_authority_flags(self) -> None:
        signature = inspect.signature(reserve_external_idempotency_slot)
        for name in (
            "slot_id",
            "request_sha256",
            "request_digest",
            "replayed",
            "reserved",
            "operation_execution_allowed",
            "upload_allowed",
            "job_creation_allowed",
        ):
            self.assertNotIn(name, signature.parameters)

    def test_safe_evidence_excludes_raw_key_body_subject_and_provider_details(self) -> None:
        decision = self.reserve(reserver=self.receipt)
        serialized = repr(decision.as_safe_dict())
        self.assertNotIn(self.client_key, serialized)
        self.assertNotIn(self.payload.decode("ascii"), serialized)
        self.assertNotIn(self.principal.subject_id, serialized)
        self.assertNotIn("opaque-authentication-credential", serialized)
        self.assertNotIn("provider", serialized.lower())
        self.assertNotIn("slotId", serialized)
        self.assertNotIn("requestSha256", serialized)


if __name__ == "__main__":
    unittest.main()
