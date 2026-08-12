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
    build_dispatch_deadline_context,
    evaluate_dispatch_deadline,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_retry import (
    DISPATCH_RETRY_CONTRACT_VERSION,
    DispatchRetryError,
    build_dispatch_attempt_budget,
    build_terminal_attempt_evidence,
    build_terminal_attempt_evidence_from_deadline,
    evaluate_dispatch_retry,
    require_dispatch_attempt_number,
)
from scoremosaic_gateway.dispatch_target import build_engine_dispatch_target
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.receiver_verification import verify_receiver_dispatch_request
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


NANOSECONDS_PER_SECOND = 1_000_000_000


class DispatchRetryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoint = EngineEndpoint("homr", "http://homr-foundation:8080")
        self.binding = build_engine_auth_binding(self.endpoint, "staging")
        self.generation = "gen-2026-08-g"
        self.secret = b"R" * MIN_CREDENTIAL_BYTES
        self.request_timestamp = 1_800_300_000
        self.nonce = "abcdef1234567890abcdef1234567890"
        self.dispatch_started_ns = 7_000_000_000
        self.plan = build_orchestration_plan(
            "job_c2gretry001",
            source_artifact_ref="sources/job_c2gretry001/source.pdf",
            source_sha256="7" * 64,
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
        self.deadline_context = build_dispatch_deadline_context(
            self.plan,
            self.verified,
            dispatch_started_monotonic_ns=self.dispatch_started_ns,
        )
        self.budget = build_dispatch_attempt_budget(
            self.plan,
            self.verified,
            self.deadline_context,
        )

    @property
    def timeout_deadline_ns(self) -> int:
        return self.dispatch_started_ns + 30 * NANOSECONDS_PER_SECOND

    def test_budget_binds_exact_run_and_preserves_zero_retry_v1_policy(self) -> None:
        self.assertEqual(self.budget.version, DISPATCH_RETRY_CONTRACT_VERSION)
        self.assertEqual(self.budget.plan_id, self.verified.dispatch_identity.plan_id)
        self.assertEqual(self.budget.job_id, self.verified.dispatch_identity.job_id)
        self.assertEqual(self.budget.run_id, self.verified.dispatch_identity.run_id)
        self.assertEqual(self.budget.engine, "homr")
        self.assertEqual(self.budget.attempt_limit, 1)
        self.assertEqual(self.budget.retries_remaining, 0)
        self.assertFalse(self.budget.retry_after_timeout)
        with self.assertRaises(FrozenInstanceError):
            self.budget.attempt_limit = 2

    def test_only_first_attempt_number_is_within_v1_budget(self) -> None:
        self.assertEqual(require_dispatch_attempt_number(self.budget, attempt_number=1), 1)
        for invalid in (True, 0, -1):
            with self.subTest(attempt_number=invalid):
                with self.assertRaisesRegex(DispatchRetryError, "attempt_number_invalid"):
                    require_dispatch_attempt_number(self.budget, attempt_number=invalid)
        for exhausted in (2, 1000):
            with self.subTest(attempt_number=exhausted):
                with self.assertRaisesRegex(DispatchRetryError, "attempt_budget_exhausted"):
                    require_dispatch_attempt_number(self.budget, attempt_number=exhausted)

    def test_all_terminal_states_are_explicitly_non_retryable(self) -> None:
        for status in ("completed", "failed", "cancelled", "timed_out"):
            with self.subTest(status=status):
                evidence = build_terminal_attempt_evidence(
                    self.budget,
                    attempt_number=1,
                    terminal_status=status,
                )
                decision = evaluate_dispatch_retry(self.budget, evidence)
                self.assertFalse(decision.retry_allowed)
                self.assertIsNone(decision.next_attempt_number)
                self.assertEqual(decision.attempts_remaining, 0)
                self.assertEqual(decision.terminal_status, status)
                self.assertEqual(
                    decision.reason_category,
                    "retry_prohibited_by_v1_attempt_budget",
                )

    def test_wrong_job_run_or_engine_attempt_evidence_fails_closed(self) -> None:
        evidence = build_terminal_attempt_evidence(
            self.budget,
            attempt_number=1,
            terminal_status="failed",
        )
        tampered = (
            replace(evidence, job_id="job_c2gretry002"),
            replace(evidence, run_id="run_" + "0" * 24),
            replace(evidence, engine="clarity"),
        )
        for item in tampered:
            with self.subTest(item=item):
                with self.assertRaisesRegex(
                    DispatchRetryError,
                    "attempt_evidence_identity_mismatch",
                ):
                    evaluate_dispatch_retry(self.budget, item)

    def test_nonterminal_or_unknown_status_cannot_enter_retry_decision(self) -> None:
        for status in ("planned", "queued", "dispatching", "running", "active", "retrying", ""):
            with self.subTest(status=status):
                with self.assertRaisesRegex(
                    DispatchRetryError,
                    "terminal_status_invalid",
                ):
                    build_terminal_attempt_evidence(
                        self.budget,
                        attempt_number=1,
                        terminal_status=status,
                    )
        with self.assertRaisesRegex(DispatchRetryError, "terminal_status_invalid"):
            build_terminal_attempt_evidence(
                self.budget,
                attempt_number=1,
                terminal_status=True,
            )

    def test_c2f_timeout_terminal_evidence_cannot_reopen_dispatch(self) -> None:
        timed_out = evaluate_dispatch_deadline(
            self.deadline_context,
            observed_monotonic_ns=self.timeout_deadline_ns,
        )
        evidence = build_terminal_attempt_evidence_from_deadline(
            self.budget,
            timed_out,
            attempt_number=1,
        )
        decision = evaluate_dispatch_retry(self.budget, evidence)
        self.assertEqual(decision.terminal_status, "timed_out")
        self.assertFalse(decision.retry_allowed)
        self.assertIsNone(decision.next_attempt_number)
        with self.assertRaisesRegex(DispatchRetryError, "attempt_budget_exhausted"):
            require_dispatch_attempt_number(self.budget, attempt_number=2)

    def test_c2f_cancellation_terminal_evidence_cannot_reopen_dispatch(self) -> None:
        cancel_ns = self.dispatch_started_ns + NANOSECONDS_PER_SECOND
        cancelled = evaluate_dispatch_deadline(
            self.deadline_context,
            observed_monotonic_ns=cancel_ns,
            cancellation_requested_monotonic_ns=cancel_ns,
        )
        evidence = build_terminal_attempt_evidence_from_deadline(
            self.budget,
            cancelled,
            attempt_number=1,
        )
        decision = evaluate_dispatch_retry(self.budget, evidence)
        self.assertEqual(decision.terminal_status, "cancelled")
        self.assertFalse(decision.retry_allowed)

    def test_active_c2f_decision_is_not_terminal_retry_evidence(self) -> None:
        active = evaluate_dispatch_deadline(
            self.deadline_context,
            observed_monotonic_ns=self.dispatch_started_ns + 1,
        )
        with self.assertRaisesRegex(DispatchRetryError, "deadline_decision_not_terminal"):
            build_terminal_attempt_evidence_from_deadline(
                self.budget,
                active,
                attempt_number=1,
            )

    def test_deadline_context_identity_mismatch_fails_closed(self) -> None:
        tampered = replace(self.deadline_context, run_id="run_" + "f" * 24)
        with self.assertRaisesRegex(
            DispatchRetryError,
            "dispatch_deadline_identity_mismatch",
        ):
            build_dispatch_attempt_budget(self.plan, self.verified, tampered)

    def test_orchestration_retry_policy_cannot_be_widened(self) -> None:
        widened = {**self.plan}
        widened["engineRuns"] = [dict(run) for run in self.plan["engineRuns"]]
        widened["engineRuns"][0]["attemptLimit"] = 2
        with self.assertRaisesRegex(DispatchRetryError, "orchestration_plan_invalid"):
            build_dispatch_attempt_budget(
                widened,
                self.verified,
                self.deadline_context,
            )

    def test_safe_evidence_does_not_create_next_run_candidate_or_artifact_identity(self) -> None:
        evidence = build_terminal_attempt_evidence(
            self.budget,
            attempt_number=1,
            terminal_status="failed",
        )
        decision = evaluate_dispatch_retry(self.budget, evidence)
        safe = decision.as_safe_dict()
        self.assertEqual(
            set(safe),
            {
                "version",
                "planId",
                "planSha256",
                "dispatchIdentitySha256",
                "jobId",
                "runId",
                "engine",
                "attemptNumber",
                "attemptLimit",
                "terminalStatus",
                "retryAllowed",
                "nextAttemptNumber",
                "attemptsRemaining",
                "reasonCategory",
            },
        )
        self.assertFalse(safe["retryAllowed"])
        self.assertIsNone(safe["nextAttemptNumber"])
        serialized_keys = " ".join(safe).lower()
        for forbidden in ("candidateid", "artifactid", "secret", "signature", "nonce", "credential"):
            self.assertNotIn(forbidden, serialized_keys)

    def test_evidence_type_is_closed(self) -> None:
        with self.assertRaisesRegex(DispatchRetryError, "attempt_evidence_invalid"):
            evaluate_dispatch_retry(self.budget, object())


if __name__ == "__main__":
    unittest.main()
