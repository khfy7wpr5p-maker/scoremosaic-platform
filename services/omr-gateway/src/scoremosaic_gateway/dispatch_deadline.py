"""Gate C.2-F deterministic dispatch timeout/cancellation decision foundation.

This module converts an already-verified C.2-E dispatch request and the exact
immutable orchestration plan into bounded monotonic deadline evidence. It does
not create timers, cancel processes, execute engines, send network requests,
persist state, retry work, or enable orchestration.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .dispatch_identity import DispatchIdentityError, build_dispatch_identity
from .orchestration import OrchestrationContractError, verify_orchestration_plan
from .receiver_verification import VerifiedDispatchRequest

DISPATCH_DEADLINE_CONTRACT_VERSION = "scoremosaic-dispatch-deadline-v1"
NANOSECONDS_PER_SECOND = 1_000_000_000
MAX_MONOTONIC_NANOSECONDS = (1 << 63) - 1

_ACTIVE = "active"
_CANCELLED = "cancelled"
_TIMED_OUT = "timed_out"
_TERMINAL_STATUSES = frozenset({_CANCELLED, _TIMED_OUT})


class DispatchDeadlineError(ValueError):
    """Safe bounded C.2-F dispatch-deadline contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require_monotonic_ns(value: Any, *, category: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_MONOTONIC_NANOSECONDS:
        raise DispatchDeadlineError(category)
    return value


def _snapshot_plan(orchestration_plan: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(orchestration_plan, Mapping):
        raise DispatchDeadlineError("orchestration_plan_invalid")
    try:
        snapshot = deepcopy(dict(orchestration_plan))
    except Exception:
        raise DispatchDeadlineError("orchestration_plan_invalid") from None
    try:
        verify_orchestration_plan(snapshot)
    except OrchestrationContractError:
        raise DispatchDeadlineError("orchestration_plan_invalid") from None
    return snapshot


@dataclass(frozen=True, slots=True)
class DispatchDeadlineContext:
    """Exact immutable timeout policy for one already-verified engine dispatch."""

    version: str
    plan_id: str
    plan_sha256: str
    dispatch_identity_sha256: str
    job_id: str
    run_id: str
    engine: str
    timeout_seconds: int
    cancellation_grace_seconds: int
    dispatch_started_monotonic_ns: int
    timeout_deadline_monotonic_ns: int
    attempt_limit: int
    retry_after_timeout: bool

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "jobId": self.job_id,
            "runId": self.run_id,
            "engine": self.engine,
            "timeoutSeconds": self.timeout_seconds,
            "cancellationGraceSeconds": self.cancellation_grace_seconds,
            "dispatchStartedMonotonicNs": self.dispatch_started_monotonic_ns,
            "timeoutDeadlineMonotonicNs": self.timeout_deadline_monotonic_ns,
            "attemptLimit": self.attempt_limit,
            "retryAfterTimeout": self.retry_after_timeout,
        }


@dataclass(frozen=True, slots=True)
class DispatchDeadlineDecision:
    """One deterministic observation of the C.2-F result-acceptance boundary."""

    version: str
    plan_id: str
    plan_sha256: str
    dispatch_identity_sha256: str
    job_id: str
    run_id: str
    engine: str
    status: str
    observed_monotonic_ns: int
    terminal_monotonic_ns: int | None
    cleanup_deadline_monotonic_ns: int | None
    accepts_result: bool

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "jobId": self.job_id,
            "runId": self.run_id,
            "engine": self.engine,
            "status": self.status,
            "observedMonotonicNs": self.observed_monotonic_ns,
            "terminalMonotonicNs": self.terminal_monotonic_ns,
            "cleanupDeadlineMonotonicNs": self.cleanup_deadline_monotonic_ns,
            "acceptsResult": self.accepts_result,
        }


def _identity_tuple(value: DispatchDeadlineContext | DispatchDeadlineDecision) -> tuple[object, ...]:
    return (
        value.version,
        value.plan_id,
        value.plan_sha256,
        value.dispatch_identity_sha256,
        value.job_id,
        value.run_id,
        value.engine,
    )


def _require_decision_shape(
    context: DispatchDeadlineContext,
    decision: DispatchDeadlineDecision,
) -> None:
    if type(decision) is not DispatchDeadlineDecision:
        raise DispatchDeadlineError("dispatch_decision_invalid")
    if _identity_tuple(context) != _identity_tuple(decision):
        raise DispatchDeadlineError("dispatch_decision_identity_mismatch")
    observed = _require_monotonic_ns(
        decision.observed_monotonic_ns,
        category="observed_monotonic_time_invalid",
    )
    if observed < context.dispatch_started_monotonic_ns:
        raise DispatchDeadlineError("monotonic_time_before_dispatch")

    if decision.status == _ACTIVE:
        if decision.accepts_result is not True:
            raise DispatchDeadlineError("dispatch_decision_invalid")
        if decision.terminal_monotonic_ns is not None:
            raise DispatchDeadlineError("dispatch_decision_invalid")
        if decision.cleanup_deadline_monotonic_ns is not None:
            raise DispatchDeadlineError("dispatch_decision_invalid")
        if observed >= context.timeout_deadline_monotonic_ns:
            raise DispatchDeadlineError("dispatch_decision_invalid")
        return

    if decision.status not in _TERMINAL_STATUSES or decision.accepts_result is not False:
        raise DispatchDeadlineError("dispatch_decision_invalid")
    terminal = _require_monotonic_ns(
        decision.terminal_monotonic_ns,
        category="dispatch_decision_invalid",
    )
    cleanup = _require_monotonic_ns(
        decision.cleanup_deadline_monotonic_ns,
        category="dispatch_decision_invalid",
    )
    if terminal > observed:
        raise DispatchDeadlineError("dispatch_decision_invalid")
    expected_cleanup = terminal + context.cancellation_grace_seconds * NANOSECONDS_PER_SECOND
    if expected_cleanup > MAX_MONOTONIC_NANOSECONDS or cleanup != expected_cleanup:
        raise DispatchDeadlineError("dispatch_decision_invalid")
    if decision.status == _TIMED_OUT and terminal != context.timeout_deadline_monotonic_ns:
        raise DispatchDeadlineError("dispatch_decision_invalid")
    if decision.status == _CANCELLED and terminal >= context.timeout_deadline_monotonic_ns:
        raise DispatchDeadlineError("dispatch_decision_invalid")


def build_dispatch_deadline_context(
    orchestration_plan: Mapping[str, Any],
    verified_request: VerifiedDispatchRequest,
    *,
    dispatch_started_monotonic_ns: int,
) -> DispatchDeadlineContext:
    """Bind exact plan timeout policy to one C.2-E verified dispatch request."""

    if type(verified_request) is not VerifiedDispatchRequest:
        raise DispatchDeadlineError("verified_dispatch_request_invalid")
    snapshot = _snapshot_plan(orchestration_plan)
    identity = verified_request.dispatch_identity

    try:
        expected_identity = build_dispatch_identity(snapshot, identity.engine)
    except (DispatchIdentityError, KeyError, TypeError):
        raise DispatchDeadlineError("dispatch_identity_mismatch") from None
    if expected_identity != identity:
        raise DispatchDeadlineError("dispatch_identity_mismatch")
    if verified_request.target.engine != identity.engine:
        raise DispatchDeadlineError("dispatch_identity_mismatch")

    matching_runs = [
        run
        for run in snapshot["engineRuns"]
        if run.get("engine") == identity.engine and run.get("runId") == identity.run_id
    ]
    if len(matching_runs) != 1:
        raise DispatchDeadlineError("dispatch_identity_mismatch")
    run = matching_runs[0]
    timeout_policy = snapshot["timeoutPolicy"]

    if run.get("attemptLimit") != 1 or timeout_policy.get("retryAfterTimeout") is not False:
        raise DispatchDeadlineError("dispatch_retry_policy_mismatch")
    if timeout_policy.get("clock") != "monotonic" or timeout_policy.get("startsAt") != "dispatch":
        raise DispatchDeadlineError("dispatch_clock_policy_mismatch")
    if timeout_policy.get("timeoutIsTerminal") is not True:
        raise DispatchDeadlineError("dispatch_timeout_policy_mismatch")

    timeout_seconds = run["timeoutSeconds"]
    cancellation_grace_seconds = timeout_policy["cancellationGraceSeconds"]
    start = _require_monotonic_ns(
        dispatch_started_monotonic_ns,
        category="dispatch_started_monotonic_time_invalid",
    )
    timeout_delta = timeout_seconds * NANOSECONDS_PER_SECOND
    grace_delta = cancellation_grace_seconds * NANOSECONDS_PER_SECOND
    timeout_deadline = start + timeout_delta
    maximum_cleanup_deadline = timeout_deadline + grace_delta
    if maximum_cleanup_deadline > MAX_MONOTONIC_NANOSECONDS:
        raise DispatchDeadlineError("monotonic_deadline_overflow")

    return DispatchDeadlineContext(
        version=DISPATCH_DEADLINE_CONTRACT_VERSION,
        plan_id=identity.plan_id,
        plan_sha256=identity.plan_sha256,
        dispatch_identity_sha256=identity.identity_sha256,
        job_id=identity.job_id,
        run_id=identity.run_id,
        engine=identity.engine,
        timeout_seconds=timeout_seconds,
        cancellation_grace_seconds=cancellation_grace_seconds,
        dispatch_started_monotonic_ns=start,
        timeout_deadline_monotonic_ns=timeout_deadline,
        attempt_limit=1,
        retry_after_timeout=False,
    )


def _terminal_decision(
    context: DispatchDeadlineContext,
    *,
    status: str,
    observed_monotonic_ns: int,
    terminal_monotonic_ns: int,
) -> DispatchDeadlineDecision:
    cleanup_deadline = (
        terminal_monotonic_ns
        + context.cancellation_grace_seconds * NANOSECONDS_PER_SECOND
    )
    if cleanup_deadline > MAX_MONOTONIC_NANOSECONDS:
        raise DispatchDeadlineError("monotonic_deadline_overflow")
    return DispatchDeadlineDecision(
        version=context.version,
        plan_id=context.plan_id,
        plan_sha256=context.plan_sha256,
        dispatch_identity_sha256=context.dispatch_identity_sha256,
        job_id=context.job_id,
        run_id=context.run_id,
        engine=context.engine,
        status=status,
        observed_monotonic_ns=observed_monotonic_ns,
        terminal_monotonic_ns=terminal_monotonic_ns,
        cleanup_deadline_monotonic_ns=cleanup_deadline,
        accepts_result=False,
    )


def evaluate_dispatch_deadline(
    context: DispatchDeadlineContext,
    *,
    observed_monotonic_ns: int,
    cancellation_requested_monotonic_ns: int | None = None,
    prior_decision: DispatchDeadlineDecision | None = None,
) -> DispatchDeadlineDecision:
    """Evaluate result acceptance without running timers or mutating state."""

    if type(context) is not DispatchDeadlineContext:
        raise DispatchDeadlineError("dispatch_deadline_context_invalid")
    observed = _require_monotonic_ns(
        observed_monotonic_ns,
        category="observed_monotonic_time_invalid",
    )
    if observed < context.dispatch_started_monotonic_ns:
        raise DispatchDeadlineError("monotonic_time_before_dispatch")

    cancellation: int | None = None
    if cancellation_requested_monotonic_ns is not None:
        cancellation = _require_monotonic_ns(
            cancellation_requested_monotonic_ns,
            category="cancellation_monotonic_time_invalid",
        )
        if cancellation < context.dispatch_started_monotonic_ns:
            raise DispatchDeadlineError("cancellation_time_before_dispatch")
        if cancellation > observed:
            raise DispatchDeadlineError("cancellation_time_in_future")

    if prior_decision is not None:
        _require_decision_shape(context, prior_decision)
        if observed < prior_decision.observed_monotonic_ns:
            raise DispatchDeadlineError("monotonic_time_regression")
        if prior_decision.terminal:
            return DispatchDeadlineDecision(
                version=prior_decision.version,
                plan_id=prior_decision.plan_id,
                plan_sha256=prior_decision.plan_sha256,
                dispatch_identity_sha256=prior_decision.dispatch_identity_sha256,
                job_id=prior_decision.job_id,
                run_id=prior_decision.run_id,
                engine=prior_decision.engine,
                status=prior_decision.status,
                observed_monotonic_ns=observed,
                terminal_monotonic_ns=prior_decision.terminal_monotonic_ns,
                cleanup_deadline_monotonic_ns=prior_decision.cleanup_deadline_monotonic_ns,
                accepts_result=False,
            )
        if cancellation is not None and cancellation < prior_decision.observed_monotonic_ns:
            raise DispatchDeadlineError("cancellation_time_regression")

    timeout_deadline = context.timeout_deadline_monotonic_ns
    if cancellation is not None and cancellation < timeout_deadline:
        return _terminal_decision(
            context,
            status=_CANCELLED,
            observed_monotonic_ns=observed,
            terminal_monotonic_ns=cancellation,
        )
    if observed >= timeout_deadline:
        return _terminal_decision(
            context,
            status=_TIMED_OUT,
            observed_monotonic_ns=observed,
            terminal_monotonic_ns=timeout_deadline,
        )

    return DispatchDeadlineDecision(
        version=context.version,
        plan_id=context.plan_id,
        plan_sha256=context.plan_sha256,
        dispatch_identity_sha256=context.dispatch_identity_sha256,
        job_id=context.job_id,
        run_id=context.run_id,
        engine=context.engine,
        status=_ACTIVE,
        observed_monotonic_ns=observed,
        terminal_monotonic_ns=None,
        cleanup_deadline_monotonic_ns=None,
        accepts_result=True,
    )


def require_dispatch_result_acceptance(
    context: DispatchDeadlineContext,
    decision: DispatchDeadlineDecision,
    *,
    observed_monotonic_ns: int,
    cancellation_requested_monotonic_ns: int | None = None,
) -> DispatchDeadlineDecision:
    """Re-evaluate at result arrival and fail closed unless still active."""

    if type(context) is not DispatchDeadlineContext:
        raise DispatchDeadlineError("dispatch_deadline_context_invalid")
    refreshed = evaluate_dispatch_deadline(
        context,
        observed_monotonic_ns=observed_monotonic_ns,
        cancellation_requested_monotonic_ns=cancellation_requested_monotonic_ns,
        prior_decision=decision,
    )
    if refreshed.status != _ACTIVE or refreshed.accepts_result is not True:
        raise DispatchDeadlineError("dispatch_result_not_acceptable")
    return refreshed
