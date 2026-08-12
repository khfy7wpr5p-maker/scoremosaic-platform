"""Bounded outward diagnostic mapping for Gate C receiver/dispatch failures.

This module converts internal C.2-E/F/G exception types into one closed,
non-secret diagnostic vocabulary suitable for a future receiver/dispatch
adapter. It does not register routes, emit HTTP responses, send requests,
execute engines, persist state, or enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dispatch_deadline import DispatchDeadlineError
from .dispatch_retry import DispatchRetryError
from .receiver_verification import ReceiverVerificationError

DISPATCH_DIAGNOSTIC_CONTRACT_VERSION = "scoremosaic-dispatch-diagnostic-v1"

_RECEIVER_DIAGNOSTIC = (
    "receiver_verification",
    "receiver_request_rejected",
)
_DEADLINE_DIAGNOSTIC = (
    "dispatch_deadline",
    "dispatch_deadline_rejected",
)
_RETRY_DIAGNOSTIC = (
    "dispatch_retry",
    "dispatch_retry_rejected",
)
_INTERNAL_DIAGNOSTIC = (
    "dispatch_internal",
    "dispatch_internal_failure",
)
_ALLOWED_DIAGNOSTICS = frozenset(
    {
        _RECEIVER_DIAGNOSTIC,
        _DEADLINE_DIAGNOSTIC,
        _RETRY_DIAGNOSTIC,
        _INTERNAL_DIAGNOSTIC,
    }
)


@dataclass(frozen=True, slots=True)
class SafeDispatchDiagnostic:
    """Closed non-secret diagnostic evidence for a future dispatch surface."""

    version: str
    stage: str
    reason: str

    def __post_init__(self) -> None:
        if self.version != DISPATCH_DIAGNOSTIC_CONTRACT_VERSION:
            raise ValueError("dispatch diagnostic version is invalid")
        if (self.stage, self.reason) not in _ALLOWED_DIAGNOSTICS:
            raise ValueError("dispatch diagnostic value is invalid")

    def as_safe_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "stage": self.stage,
            "reason": self.reason,
        }


def _diagnostic(stage_reason: tuple[str, str]) -> SafeDispatchDiagnostic:
    stage, reason = stage_reason
    return SafeDispatchDiagnostic(
        version=DISPATCH_DIAGNOSTIC_CONTRACT_VERSION,
        stage=stage,
        reason=reason,
    )


def map_dispatch_failure(failure: Exception) -> SafeDispatchDiagnostic:
    """Map one internal dispatch failure without inspecting its text or payload.

    Exact exception types are deliberate. A subclass is not allowed to inherit
    a more specific trusted public mapping because future adapters may receive
    exceptions from untrusted or extensible integration code.
    """

    if not isinstance(failure, Exception):
        raise TypeError("dispatch failure must be an exception")
    if type(failure) is ReceiverVerificationError:
        return _diagnostic(_RECEIVER_DIAGNOSTIC)
    if type(failure) is DispatchDeadlineError:
        return _diagnostic(_DEADLINE_DIAGNOSTIC)
    if type(failure) is DispatchRetryError:
        return _diagnostic(_RETRY_DIAGNOSTIC)
    return _diagnostic(_INTERNAL_DIAGNOSTIC)
