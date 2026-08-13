"""Provider-neutral external rate-slot reservation contract for Gate E.3A.

This module consumes exact Gate E.1 authenticated-principal evidence and an exact
allowed Gate E.2 authorization decision. It derives one bounded operation-specific
rate window from a server-owned policy and delegates the atomic reserve-or-limit
operation to a later runtime adapter through one callback seam.

A successful rate decision is admission evidence only. It does not register an
HTTP route, execute an operation, accept an upload, create a job, persist rate
state, dispatch a network request, or enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Callable

from .external_auth import (
    ALLOWED_ENVIRONMENTS,
    MAX_TIMESTAMP,
    AuthenticatedExternalPrincipal,
)
from .external_authorization import (
    ExternalAuthorizationDecision,
    _is_operation_id as _is_authorized_operation_id,
)


EXTERNAL_RATE_LIMIT_CONTRACT_VERSION = "scoremosaic-external-rate-limit-v1"
MAX_RATE_RULES = 128
MAX_RATE_WINDOW_SECONDS = 86_400
MAX_RATE_REQUESTS = 100_000

_PRINCIPAL_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RATE_DECISION_CONSTRUCTION_SEAL = object()


class ExternalRateLimitError(ValueError):
    """Stable fail-closed external rate-limit-contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIMESTAMP


def _is_principal_id(value: object) -> bool:
    return type(value) is str and _PRINCIPAL_ID_RE.fullmatch(value) is not None


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _is_positive_bounded_int(value: object, maximum: int) -> bool:
    return type(value) is int and 1 <= value <= maximum


@dataclass(frozen=True, slots=True)
class ExternalRateLimitRule:
    """One exact operation-specific rate budget in a server-owned policy."""

    operation_id: str
    window_seconds: int
    max_requests: int

    def __post_init__(self) -> None:
        if not _is_authorized_operation_id(self.operation_id):
            raise ExternalRateLimitError("rate_policy_invalid")
        if not _is_positive_bounded_int(
            self.window_seconds, MAX_RATE_WINDOW_SECONDS
        ):
            raise ExternalRateLimitError("rate_policy_invalid")
        if not _is_positive_bounded_int(self.max_requests, MAX_RATE_REQUESTS):
            raise ExternalRateLimitError("rate_policy_invalid")


@dataclass(frozen=True, slots=True)
class ExternalRateLimitPolicy:
    """Server-owned exact operation budgets for one deployment environment.

    This object defines contract evidence only. A later runtime integration must
    construct it from server-controlled configuration and separately provide an
    atomic reservation backend.
    """

    version: str
    environment: str
    rules: tuple[ExternalRateLimitRule, ...]

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != EXTERNAL_RATE_LIMIT_CONTRACT_VERSION
        ):
            raise ExternalRateLimitError("rate_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalRateLimitError("environment_not_allowed")
        if type(self.rules) is not tuple or len(self.rules) > MAX_RATE_RULES:
            raise ExternalRateLimitError("rate_policy_invalid")

        seen: set[str] = set()
        for rule in self.rules:
            if type(rule) is not ExternalRateLimitRule:
                raise ExternalRateLimitError("rate_policy_invalid")
            rule.__post_init__()
            if rule.operation_id in seen:
                raise ExternalRateLimitError("rate_policy_invalid")
            seen.add(rule.operation_id)


@dataclass(frozen=True, slots=True)
class ExternalRateReservationRequest:
    """Immutable server-derived input for one atomic reserve-or-limit operation."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    reservation_key: str
    window_start_epoch_s: int
    window_end_epoch_s: int
    max_requests: int

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != EXTERNAL_RATE_LIMIT_CONTRACT_VERSION
        ):
            raise ExternalRateLimitError("rate_reservation_request_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalRateLimitError("rate_reservation_request_invalid")
        if not _is_principal_id(self.principal_id):
            raise ExternalRateLimitError("rate_reservation_request_invalid")
        if not _is_authorized_operation_id(self.operation_id):
            raise ExternalRateLimitError("rate_reservation_request_invalid")
        if not _is_sha256(self.reservation_key):
            raise ExternalRateLimitError("rate_reservation_request_invalid")
        if not _is_timestamp(self.window_start_epoch_s) or not _is_timestamp(
            self.window_end_epoch_s
        ):
            raise ExternalRateLimitError("rate_reservation_request_invalid")
        if self.window_end_epoch_s <= self.window_start_epoch_s:
            raise ExternalRateLimitError("rate_reservation_request_invalid")
        if self.window_end_epoch_s - self.window_start_epoch_s > MAX_RATE_WINDOW_SECONDS:
            raise ExternalRateLimitError("rate_reservation_request_invalid")
        if not _is_positive_bounded_int(self.max_requests, MAX_RATE_REQUESTS):
            raise ExternalRateLimitError("rate_reservation_request_invalid")


@dataclass(frozen=True, slots=True)
class ExternalRateReservationReceipt:
    """Atomic reservation-adapter result bound back to the exact request."""

    reservation_key: str
    window_start_epoch_s: int
    window_end_epoch_s: int
    max_requests: int
    outcome: str

    def __post_init__(self) -> None:
        if not _is_sha256(self.reservation_key):
            raise ExternalRateLimitError("rate_reservation_invalid")
        if not _is_timestamp(self.window_start_epoch_s) or not _is_timestamp(
            self.window_end_epoch_s
        ):
            raise ExternalRateLimitError("rate_reservation_invalid")
        if self.window_end_epoch_s <= self.window_start_epoch_s:
            raise ExternalRateLimitError("rate_reservation_invalid")
        if self.window_end_epoch_s - self.window_start_epoch_s > MAX_RATE_WINDOW_SECONDS:
            raise ExternalRateLimitError("rate_reservation_invalid")
        if not _is_positive_bounded_int(self.max_requests, MAX_RATE_REQUESTS):
            raise ExternalRateLimitError("rate_reservation_invalid")
        if type(self.outcome) is not str or self.outcome not in {
            "reserved",
            "limit_reached",
        }:
            raise ExternalRateLimitError("rate_reservation_invalid")


ExternalRateSlotReserver = Callable[
    [ExternalRateReservationRequest],
    ExternalRateReservationReceipt,
]


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ExternalRateDecision:
    """Bounded rate-admission evidence without operation execution authority."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    allowed: bool
    reason: str

    def __init__(
        self,
        *,
        version: str,
        environment: str,
        principal_id: str,
        operation_id: str,
        allowed: bool,
        reason: str,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _RATE_DECISION_CONSTRUCTION_SEAL:
            raise ExternalRateLimitError("rate_decision_construction_forbidden")

        object.__setattr__(self, "version", version)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "allowed", allowed)
        object.__setattr__(self, "reason", reason)
        self.__post_init__()

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != EXTERNAL_RATE_LIMIT_CONTRACT_VERSION
        ):
            raise ExternalRateLimitError("rate_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalRateLimitError("environment_not_allowed")
        if not _is_principal_id(self.principal_id):
            raise ExternalRateLimitError("principal_invalid")
        if not _is_authorized_operation_id(self.operation_id):
            raise ExternalRateLimitError("operation_invalid")
        if type(self.allowed) is not bool or type(self.reason) is not str:
            raise ExternalRateLimitError("rate_decision_invalid")
        expected_reason = "reserved" if self.allowed else "rate_limited"
        if self.reason != expected_reason:
            raise ExternalRateLimitError("rate_decision_invalid")

    def __repr__(self) -> str:
        state = "allowed" if self.allowed else "rate_limited"
        return (
            "ExternalRateDecision("
            f"version={self.version!r}, environment={self.environment!r}, "
            f"principal_id={self.principal_id!r}, operation_id={self.operation_id!r}, "
            f"state={state!r})"
        )

    def as_safe_dict(self) -> dict[str, str | bool]:
        """Return privacy-bounded rate evidence with all runtime capabilities off."""

        return {
            "version": self.version,
            "environment": self.environment,
            "principalId": self.principal_id,
            "operationId": self.operation_id,
            "rateState": "allowed" if self.allowed else "rate_limited",
            "rateSlotReserved": self.allowed,
            "reason": self.reason,
            "operationExecutionAllowed": False,
            "uploadAllowed": False,
            "jobCreationAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


def _reservation_key(
    *,
    environment: str,
    principal_id: str,
    operation_id: str,
    window_start_epoch_s: int,
    window_end_epoch_s: int,
) -> str:
    payload = b"\0".join(
        (
            EXTERNAL_RATE_LIMIT_CONTRACT_VERSION.encode("ascii"),
            environment.encode("ascii"),
            principal_id.encode("ascii"),
            operation_id.encode("ascii"),
            str(window_start_epoch_s).encode("ascii"),
            str(window_end_epoch_s).encode("ascii"),
        )
    )
    return sha256(payload).hexdigest()


def reserve_external_rate_slot(
    *,
    policy: ExternalRateLimitPolicy,
    principal: AuthenticatedExternalPrincipal,
    authorization: ExternalAuthorizationDecision,
    operation_id: str,
    observed_at_epoch_s: int,
    reserver: ExternalRateSlotReserver,
) -> ExternalRateDecision:
    """Atomically reserve one operation slot through a provider-neutral authority seam."""

    if type(policy) is not ExternalRateLimitPolicy:
        raise ExternalRateLimitError("rate_policy_invalid")
    policy.__post_init__()

    if type(principal) is not AuthenticatedExternalPrincipal:
        raise ExternalRateLimitError("principal_invalid")
    try:
        principal.__post_init__()
    except Exception:
        raise ExternalRateLimitError("principal_invalid") from None

    if type(authorization) is not ExternalAuthorizationDecision:
        raise ExternalRateLimitError("authorization_invalid")
    try:
        authorization.__post_init__()
    except Exception:
        raise ExternalRateLimitError("authorization_invalid") from None

    if principal.environment != policy.environment:
        raise ExternalRateLimitError("environment_mismatch")
    if authorization.environment != principal.environment:
        raise ExternalRateLimitError("authorization_mismatch")
    if authorization.principal_id != principal.principal_id:
        raise ExternalRateLimitError("authorization_mismatch")
    if not _is_authorized_operation_id(operation_id):
        raise ExternalRateLimitError("operation_invalid")
    if authorization.operation_id != operation_id:
        raise ExternalRateLimitError("authorization_mismatch")
    if not authorization.allowed:
        raise ExternalRateLimitError("authorization_required")

    if not _is_timestamp(observed_at_epoch_s):
        raise ExternalRateLimitError("rate_time_invalid")
    if observed_at_epoch_s < principal.authenticated_at_epoch_s:
        raise ExternalRateLimitError("rate_time_invalid")
    if principal.expires_at_epoch_s <= observed_at_epoch_s:
        raise ExternalRateLimitError("principal_expired")

    matching_rules = tuple(
        rule for rule in policy.rules if rule.operation_id == operation_id
    )
    if len(matching_rules) != 1:
        raise ExternalRateLimitError("rate_policy_operation_missing")
    rule = matching_rules[0]

    window_start = (observed_at_epoch_s // rule.window_seconds) * rule.window_seconds
    window_end = window_start + rule.window_seconds
    if window_end > MAX_TIMESTAMP:
        raise ExternalRateLimitError("rate_window_invalid")

    request = ExternalRateReservationRequest(
        version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
        environment=policy.environment,
        principal_id=principal.principal_id,
        operation_id=operation_id,
        reservation_key=_reservation_key(
            environment=policy.environment,
            principal_id=principal.principal_id,
            operation_id=operation_id,
            window_start_epoch_s=window_start,
            window_end_epoch_s=window_end,
        ),
        window_start_epoch_s=window_start,
        window_end_epoch_s=window_end,
        max_requests=rule.max_requests,
    )

    if not callable(reserver):
        raise ExternalRateLimitError("rate_reserver_invalid")
    try:
        receipt = reserver(request)
    except Exception:
        raise ExternalRateLimitError("rate_reservation_unavailable") from None

    if type(receipt) is not ExternalRateReservationReceipt:
        raise ExternalRateLimitError("rate_reservation_invalid")
    try:
        receipt.__post_init__()
    except Exception:
        raise ExternalRateLimitError("rate_reservation_invalid") from None

    if (
        receipt.reservation_key != request.reservation_key
        or receipt.window_start_epoch_s != request.window_start_epoch_s
        or receipt.window_end_epoch_s != request.window_end_epoch_s
        or receipt.max_requests != request.max_requests
    ):
        raise ExternalRateLimitError("rate_reservation_invalid")

    allowed = receipt.outcome == "reserved"
    return ExternalRateDecision(
        version=EXTERNAL_RATE_LIMIT_CONTRACT_VERSION,
        environment=policy.environment,
        principal_id=principal.principal_id,
        operation_id=operation_id,
        allowed=allowed,
        reason="reserved" if allowed else "rate_limited",
        _construction_seal=_RATE_DECISION_CONSTRUCTION_SEAL,
    )
