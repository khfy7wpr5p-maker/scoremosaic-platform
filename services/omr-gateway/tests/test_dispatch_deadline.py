from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.credential_rotation import (
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_deadline import (
    DISPATCH_DEADLINE_CONTRACT_VERSION,
    MAX_MONOTONIC_NANOSECONDS,
    DispatchDeadlineError,
    build_dispatch_deadline_context,
    evaluate_dispatch_deadline,
    require_dispatch_result_acceptance,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_target import build_engine_dispatch_target
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.receiver_verification import verify_receiver_dispatch_request
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


NANOSECONDS_PER_SECOND = 1_000_000_000


class DispatchDeadlineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoint = EngineEndpoint("homr", "http://homr-foundation:8080")
        self.binding = build_engine_auth_binding(self.endpoint, "staging")
        self.generation = "gen-2026-08-d"
        self.secret = b"T" * MIN_CREDENTIAL_BYTES
        self.request_timestamp = 1_800_200_000
        self.nonce = "1234567890abcdef1234567890abcdef"
        self.dispatch_started_ns = 5_000_000_000
        self.plan = build_orchestration_plan(
            "job_c2fdeadline01",
            source_artifact_ref="sources/job_c2fdeadline01/source.pdf",
            source_sha256="5" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
            requested_engines=("homr",),
            timeout_seconds_by_engine={"homr": 30},
            cancellation_grace_seconds=5,
        ).as_dict()
        credential = resolve_engine_credential_generation(
            self.binding,
            self.generation,
            lambda credential_key, generation_id: (
                self.secret
                if credential_key == self.binding.credential_key
                and generation_id == self.generation
                else None
            ),
        )
        rotation = build_rotation_set(
            current=credential,
            previous=None,
            rotation_started_at=self.request_timestamp,
            previous_valid_until=None,
        )
        target = build_engine_dispatch_target(self.binding, self.endpoint)
        identity = build_dispatch_identity(self.plan, "homr")
        payload = dispatch_identity_payload(identity)
        request = sign_rotation_authenticated_request(
            rotation,
            method=target.method,
            path=target.path,
            timestamp=self.request_timestamp,
            nonce=self.nonce,
            payload=payload,
            now_seconds=self.request_timestamp,
        )
        self.verified = verify_receiver_dispatch_request(
            self.plan,
            target,
            rotation,
            request,
            observed_method="POST",
            observed_path="/internal/transcribe",
            payload=payload,
            now_seconds=self.request_timestamp,
            replay_checker=lambda binding, generation_id, nonce, timestamp: True,
        )
        self.context = build_dispatch_deadline_context(
            self.plan,
            self.verified,
            dispatch_started_monotonic_ns=self.dispatch_started_ns,
        )

    @property
    def timeout_deadline_ns(self) -> int:
        return self.dispatch_started_ns + 30 * NANOSECONDS_PER_SECOND

    def test_context_binds_exact_verified_run_and_fixed_retry_policy(self) -> None:
        self.assertEqual(self.context.version, DISPATCH_DEADLINE_CONTRACT_VERSION)
        self.assertEqual(self.context.plan_id, self.verified.dispatch_identity.plan_id)
        self.assertEqual(self.context.job_id, self.verified.dispatch_identity.job_id)
        self.assertEqual(self.context.run_id, self.verified.dispatch_identity.run_id)
        self.assertEqual(self.context.engine, "homr")
        self.assertEqual(self.context.timeout_seconds, 30)
        self.assertEqual(self.context.cancellation_grace_seconds, 5)
        self.assertEqual(self.context.timeout_deadline_monotonic_ns, self.timeout_deadline_ns)
        self.assertEqual(self.context.attempt_limit, 1)
        self.assertFalse(self.context.retry_after_timeout)
        with self.assertRaises(FrozenInstanceError):
            self.context.timeout_seconds = 31

    def test_deadline_is_active_before_and_times_out_at_exact_boundary(self) -> None:
        before = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=self.timeout_deadline_ns - 1,
        )
        self.assertEqual(before.status, "active")
        self.assertTrue(before.accepts_result)
        require_dispatch_result_acceptance(self.context, before)

        exact = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=self.timeout_deadline_ns,
        )
        self.assertEqual(exact.status, "timed_out")
        self.assertFalse(exact.accepts_result)
        self.assertEqual(exact.terminal_monotonic_ns, self.timeout_deadline_ns)
        with self.assertRaisesRegex(
            DispatchDeadlineError,
            "dispatch_result_not_acceptable",
        ):
            require_dispatch_result_acceptance(self.context, exact)

    def test_late_result_stays_rejected_after_timeout_and_cleanup_grace(self) -> None:
        timed_out = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=self.timeout_deadline_ns,
        )
        after_grace = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=self.timeout_deadline_ns + 5 * NANOSECONDS_PER_SECOND,
            prior_decision=timed_out,
        )
        self.assertEqual(after_grace.status, "timed_out")
        self.assertFalse(after_grace.accepts_result)
        self.assertEqual(
            after_grace.cleanup_deadline_monotonic_ns,
            self.timeout_deadline_ns + 5 * NANOSECONDS_PER_SECOND,
        )
        with self.assertRaisesRegex(
            DispatchDeadlineError,
            "dispatch_result_not_acceptable",
        ):
            require_dispatch_result_acceptance(self.context, after_grace)

    def test_cancellation_before_timeout_is_immediately_terminal(self) -> None:
        cancel_ns = self.dispatch_started_ns + 10 * NANOSECONDS_PER_SECOND
        cancelled = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=cancel_ns,
            cancellation_requested_monotonic_ns=cancel_ns,
        )
        self.assertEqual(cancelled.status, "cancelled")
        self.assertFalse(cancelled.accepts_result)
        self.assertEqual(cancelled.terminal_monotonic_ns, cancel_ns)
        self.assertEqual(
            cancelled.cleanup_deadline_monotonic_ns,
            cancel_ns + 5 * NANOSECONDS_PER_SECOND,
        )

        after_cleanup = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=cancel_ns + 20 * NANOSECONDS_PER_SECOND,
            prior_decision=cancelled,
        )
        self.assertEqual(after_cleanup.status, "cancelled")
        self.assertFalse(after_cleanup.accepts_result)

    def test_cancellation_at_timeout_boundary_cannot_override_timeout(self) -> None:
        decision = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=self.timeout_deadline_ns,
            cancellation_requested_monotonic_ns=self.timeout_deadline_ns,
        )
        self.assertEqual(decision.status, "timed_out")
        self.assertEqual(decision.terminal_monotonic_ns, self.timeout_deadline_ns)

    def test_terminal_decision_cannot_reopen(self) -> None:
        cancel_ns = self.dispatch_started_ns + NANOSECONDS_PER_SECOND
        cancelled = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=cancel_ns,
            cancellation_requested_monotonic_ns=cancel_ns,
        )
        later = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=self.timeout_deadline_ns + NANOSECONDS_PER_SECOND,
            prior_decision=cancelled,
        )
        self.assertEqual(later.status, "cancelled")
        self.assertFalse(later.accepts_result)

    def test_wrong_verified_job_run_or_engine_identity_fails_closed(self) -> None:
        identity = self.verified.dispatch_identity
        tampered_identities = (
            replace(identity, job_id="job_c2fdeadline02"),
            replace(identity, run_id="run_" + "0" * 24),
            replace(identity, engine="clarity"),
        )
        for tampered_identity in tampered_identities:
            with self.subTest(tampered_identity=tampered_identity):
                tampered_verified = replace(
                    self.verified,
                    dispatch_identity=tampered_identity,
                )
                with self.assertRaisesRegex(
                    DispatchDeadlineError,
                    "dispatch_identity_mismatch",
                ):
                    build_dispatch_deadline_context(
                        self.plan,
                        tampered_verified,
                        dispatch_started_monotonic_ns=self.dispatch_started_ns,
                    )

    def test_invalid_monotonic_values_fail_closed(self) -> None:
        for invalid in (True, -1, MAX_MONOTONIC_NANOSECONDS + 1):
            with self.subTest(start=invalid):
                with self.assertRaises(DispatchDeadlineError):
                    build_dispatch_deadline_context(
                        self.plan,
                        self.verified,
                        dispatch_started_monotonic_ns=invalid,
                    )

        for invalid in (True, -1, MAX_MONOTONIC_NANOSECONDS + 1):
            with self.subTest(observed=invalid):
                with self.assertRaises(DispatchDeadlineError):
                    evaluate_dispatch_deadline(
                        self.context,
                        observed_monotonic_ns=invalid,
                    )

        with self.assertRaisesRegex(
            DispatchDeadlineError,
            "monotonic_time_before_dispatch",
        ):
            evaluate_dispatch_deadline(
                self.context,
                observed_monotonic_ns=self.dispatch_started_ns - 1,
            )

        with self.assertRaisesRegex(
            DispatchDeadlineError,
            "cancellation_time_in_future",
        ):
            evaluate_dispatch_deadline(
                self.context,
                observed_monotonic_ns=self.dispatch_started_ns + 1,
                cancellation_requested_monotonic_ns=self.dispatch_started_ns + 2,
            )

    def test_deadline_overflow_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            DispatchDeadlineError,
            "monotonic_deadline_overflow",
        ):
            build_dispatch_deadline_context(
                self.plan,
                self.verified,
                dispatch_started_monotonic_ns=(
                    MAX_MONOTONIC_NANOSECONDS
                    - 30 * NANOSECONDS_PER_SECOND
                    - 5 * NANOSECONDS_PER_SECOND
                    + 1
                ),
            )

    def test_result_acceptance_rejects_context_decision_identity_mismatch(self) -> None:
        active = evaluate_dispatch_deadline(
            self.context,
            observed_monotonic_ns=self.timeout_deadline_ns - 1,
        )
        other_context = replace(self.context, run_id="run_" + "f" * 24)
        with self.assertRaisesRegex(
            DispatchDeadlineError,
            "dispatch_decision_identity_mismatch",
        ):
            require_dispatch_result_acceptance(other_context, active)


if __name__ == "__main__":
    unittest.main()
