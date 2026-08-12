"""Gate C.2-G deterministic bounded retry / attempt-budget foundation.

The orchestration v1 contract permits exactly one execution attempt and no
retry after timeout. This module makes that already-approved policy explicit
and fail-closed without creating queues, workers, backoff loops, new run IDs,
network requests, persistence, engine execution, or orchestration activation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .dispatch_deadline import DispatchDeadlineContext, DispatchDeadlineDecision
from .dispatch_identity import DispatchIdentityError, build_dispatch_identity
from .orchestration import OrchestrationContractError, verify_orchestration_plan
from .receiver_verification import VerifiedDispatchRequest

DISPATCH_RETRY_CONTRACT_VERSION = "scoremosaic-dispatch-retry-v1"

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "timed_out"})
_DEADLINE_TERMINAL_STATUSES = frozenset({"cancelled", "timed_out"})
_RETRY_PROHIBITED_REASON = "retry_prohibited_by_v1_attempt_budget"


class DispatchRetryError(ValueError):
    """Safe bounded C.2-G attempt-budget contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _snapshot_plan(orchestration_plan: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(orchestration_plan, Mapping):
        raise DispatchRetryError("orchestration_plan_invalid")
    try:
        snapshot = deepcopy(dict(orchestration_plan))
    except Exception:
        raise DispatchRetryError("orchestration_plan_invalid") from None
    try:
        verify_orchestration_plan(snapshot)
    except OrchestrationContractError:
        raise DispatchRetryError("orchestration_plan_invalid") from None
    return snapshot


@dataclass(frozen=True, slots=True)
class DispatchAttemptBudget:
    """Exact immutable v1 attempt budget for one verified engine run."""

    version: str
    plan_id: str
    plan_sha256: str
    dispatch_identity_sha256: str
    job_id: str
    run_id: str
    engine: str
    attempt_limit: int
    retries_remaining: int
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
            "attemptLimit": self.attempt_limit,
            "retriesRemaining": self.retries_remaining,
            "retryAfterTimeout": self.retry_after_timeout,
        }


@dataclass(frozen=True, slots=True)
class DispatchTerminalAttemptEvidence:
    """Bounded terminal-state evidence for the single allowed v1 attempt."""

    version: str
    plan_id: str
    plan_sha256: str
    dispatch_identity_sha256: str
    job_id: str
    run_id: str
    engine: str
    attempt_number: int
    terminal_status: str

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "jobId": self.job_id,
            "runId": self.run_id,
            "engine": self.engine,
            "attemptNumber": self.attempt_number,
            "terminalStatus": self.terminal_status,
        }


@dataclass(frozen=True, slots=True)
class DispatchRetryDecision:
    """Fail-closed v1 decision: terminal engine attempts never retry."""

    version: str
    plan_id: str
    plan_sha256: str
    dispatch_identity_sha256: str
    job_id: str
    run_id: str
    engine: str
    attempt_number: int
    attempt_limit: int
    terminal_status: str
    retry_allowed: bool
    next_attempt_number: int | None
    attempts_remaining: int
    reason_category: str

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "jobId": self.job_id,
            "runId": self.run_id,
            "engine": self.engine,
            "attemptNumber": self.attempt_number,
            "attemptLimit": self.attempt_limit,
            "terminalStatus": self.terminal_status,
            "retryAllowed": self.retry_allowed,
            "nextAttemptNumber": self.next_attempt_number,
            "attemptsRemaining": self.attempts_remaining,
            "reasonCategory": self.reason_category,
        }


def _budget_identity(value: DispatchAttemptBudget) -> tuple[object, ...]:
    return (
        value.plan_id,
        value.plan_sha256,
        value.dispatch_identity_sha256,
        value.job_id,
        value.run_id,
        value.engine,
    )


def _evidence_identity(value: DispatchTerminalAttemptEvidence) -> tuple[object, ...]:
    return (
        value.plan_id,
        value.plan_sha256,
        value.dispatch_identity_sha256,
        value.job_id,
        value.run_id,
        value.engine,
    )


def _deadline_identity(value: DispatchDeadlineContext | DispatchDeadlineDecision) -> tuple[object, ...]:
    return (
        value.plan_id,
        value.plan_sha256,
        value.dispatch_identity_sha256,
        value.job_id,
        value.run_id,
        value.engine,
    )


def _require_budget(budget: DispatchAttemptBudget) -> None:
    if type(budget) is not DispatchAttemptBudget:
        raise DispatchRetryError("attempt_budget_invalid")
    if budget.version != DISPATCH_RETRY_CONTRACT_VERSION:
        raise DispatchRetryError("attempt_budget_invalid")
    if type(budget.attempt_limit) is not int or budget.attempt_limit != 1:
        raise DispatchRetryError("attempt_budget_invalid")
    if type(budget.retries_remaining) is not int or budget.retries_remaining != 0:
        raise DispatchRetryError("attempt_budget_invalid")
    if budget.retry_after_timeout is not False:
        raise DispatchRetryError("attempt_budget_invalid")


def require_dispatch_attempt_number(
    budget: DispatchAttemptBudget,
    *,
    attempt_number: int,
) -> int:
    """Validate an attempt number without starting or scheduling any work."""

    _require_budget(budget)
    if type(attempt_number) is not int or attempt_number < 1:
        raise DispatchRetryError("attempt_number_invalid")
    if attempt_number > budget.attempt_limit:
        raise DispatchRetryError("attempt_budget_exhausted")
    return attempt_number


def build_dispatch_attempt_budget(
    orchestration_plan: Mapping[str, Any],
    verified_request: VerifiedDispatchRequest,
    deadline_context: DispatchDeadlineContext,
) -> DispatchAttemptBudget:
    """Bind the immutable orchestration v1 attempt policy to one verified run."""

    if type(verified_request) is not VerifiedDispatchRequest:
        raise DispatchRetryError("verified_dispatch_request_invalid")
    if type(deadline_context) is not DispatchDeadlineContext:
        raise DispatchRetryError("dispatch_deadline_context_invalid")

    snapshot = _snapshot_plan(orchestration_plan)
    identity = verified_request.dispatch_identity
    try:
        expected_identity = build_dispatch_identity(snapshot, identity.engine)
    except (DispatchIdentityError, KeyError, TypeError):
        raise DispatchRetryError("dispatch_identity_mismatch") from None
    if expected_identity != identity:
        raise DispatchRetryError("dispatch_identity_mismatch")
    if verified_request.target.engine != identity.engine:
        raise DispatchRetryError("dispatch_identity_mismatch")

    expected_deadline_identity = (
        identity.plan_id,
        identity.plan_sha256,
        identity.identity_sha256,
        identity.job_id,
        identity.run_id,
        identity.engine,
    )
    if _deadline_identity(deadline_context) != expected_deadline_identity:
        raise DispatchRetryError("dispatch_deadline_identity_mismatch")
    if deadline_context.attempt_limit != 1 or deadline_context.retry_after_timeout is not False:
        raise DispatchRetryError("dispatch_retry_policy_mismatch")

    matching_runs = [
        run
        for run in snapshot["engineRuns"]
        if run.get("engine") == identity.engine and run.get("runId") == identity.run_id
    ]
    if len(matching_runs) != 1:
        raise DispatchRetryError("dispatch_identity_mismatch")
    run = matching_runs[0]
    attempt_limit = run.get("attemptLimit")
    timeout_policy = snapshot.get("timeoutPolicy")
    if type(attempt_limit) is not int or attempt_limit != 1:
        raise DispatchRetryError("dispatch_retry_policy_mismatch")
    if not isinstance(timeout_policy, Mapping):
        raise DispatchRetryError("dispatch_retry_policy_mismatch")
    if timeout_policy.get("retryAfterTimeout") is not False:
        raise DispatchRetryError("dispatch_retry_policy_mismatch")

    return DispatchAttemptBudget(
        version=DISPATCH_RETRY_CONTRACT_VERSION,
        plan_id=identity.plan_id,
        plan_sha256=identity.plan_sha256,
        dispatch_identity_sha256=identity.identity_sha256,
        job_id=identity.job_id,
        run_id=identity.run_id,
        engine=identity.engine,
        attempt_limit=1,
        retries_remaining=0,
        retry_after_timeout=False,
    )


def _require_terminal_status(value: object) -> str:
    if type(value) is not str or value not in _TERMINAL_STATUSES:
        raise DispatchRetryError("terminal_status_invalid")
    return value


def build_terminal_attempt_evidence(
    budget: DispatchAttemptBudget,
    *,
    attempt_number: int,
    terminal_status: str,
) -> DispatchTerminalAttemptEvidence:
    """Create bounded terminal evidence without creating a new execution identity."""

    _require_budget(budget)
    attempt = require_dispatch_attempt_number(budget, attempt_number=attempt_number)
    status = _require_terminal_status(terminal_status)
    return DispatchTerminalAttemptEvidence(
        version=budget.version,
        plan_id=budget.plan_id,
        plan_sha256=budget.plan_sha256,
        dispatch_identity_sha256=budget.dispatch_identity_sha256,
        job_id=budget.job_id,
        run_id=budget.run_id,
        engine=budget.engine,
        attempt_number=attempt,
        terminal_status=status,
    )


def build_terminal_attempt_evidence_from_deadline(
    budget: DispatchAttemptBudget,
    decision: DispatchDeadlineDecision,
    *,
    attempt_number: int,
) -> DispatchTerminalAttemptEvidence:
    """Bind a C.2-F timeout/cancellation terminal decision to the single attempt."""

    _require_budget(budget)
    if type(decision) is not DispatchDeadlineDecision:
        raise DispatchRetryError("deadline_decision_invalid")
    if _deadline_identity(decision) != _budget_identity(budget):
        raise DispatchRetryError("deadline_decision_identity_mismatch")
    if (
        decision.status not in _DEADLINE_TERMINAL_STATUSES
        or decision.terminal is not True
        or decision.accepts_result is not False
        or decision.terminal_monotonic_ns is None
    ):
        raise DispatchRetryError("deadline_decision_not_terminal")
    return build_terminal_attempt_evidence(
        budget,
        attempt_number=attempt_number,
        terminal_status=decision.status,
    )


def _require_attempt_evidence(
    budget: DispatchAttemptBudget,
    evidence: DispatchTerminalAttemptEvidence,
) -> None:
    _require_budget(budget)
    if type(evidence) is not DispatchTerminalAttemptEvidence:
        raise DispatchRetryError("attempt_evidence_invalid")
    if evidence.version != budget.version:
        raise DispatchRetryError("attempt_evidence_invalid")
    if _evidence_identity(evidence) != _budget_identity(budget):
        raise DispatchRetryError("attempt_evidence_identity_mismatch")
    require_dispatch_attempt_number(budget, attempt_number=evidence.attempt_number)
    _require_terminal_status(evidence.terminal_status)


def evaluate_dispatch_retry(
    budget: DispatchAttemptBudget,
    evidence: DispatchTerminalAttemptEvidence,
) -> DispatchRetryDecision:
    """Return the fixed v1 no-retry decision for exact terminal attempt evidence."""

    _require_attempt_evidence(budget, evidence)
    return DispatchRetryDecision(
        version=budget.version,
        plan_id=budget.plan_id,
        plan_sha256=budget.plan_sha256,
        dispatch_identity_sha256=budget.dispatch_identity_sha256,
        job_id=budget.job_id,
        run_id=budget.run_id,
        engine=budget.engine,
        attempt_number=evidence.attempt_number,
        attempt_limit=budget.attempt_limit,
        terminal_status=evidence.terminal_status,
        retry_allowed=False,
        next_attempt_number=None,
        attempts_remaining=0,
        reason_category=_RETRY_PROHIBITED_REASON,
    )
