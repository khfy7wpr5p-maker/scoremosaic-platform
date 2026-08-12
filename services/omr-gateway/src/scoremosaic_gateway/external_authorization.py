"""Provider-neutral external authorization decision contract for Gate E.2.

This module consumes only an exact Gate E.1 authenticated external principal and a
server-owned authorization policy. It evaluates one canonical operation identifier
with deny-by-default semantics. An allowed decision is authorization evidence only;
it does not activate an HTTP route, execute an operation, create a job, accept an
upload, dispatch a network request, or enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .external_auth import (
    ALLOWED_ENVIRONMENTS,
    MAX_TIMESTAMP,
    AuthenticatedExternalPrincipal,
)


EXTERNAL_AUTHORIZATION_CONTRACT_VERSION = "scoremosaic-external-authorization-v1"
MAX_OPERATION_ID_LENGTH = 128

_OPERATION_ID_RE = re.compile(
    r"[a-z0-9][a-z0-9_-]{0,31}(?:\.[a-z0-9][a-z0-9_-]{0,31}){1,7}\Z"
)
_PRINCIPAL_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_AUTHORIZATION_DECISION_CONSTRUCTION_SEAL = object()


class ExternalAuthorizationError(ValueError):
    """Stable fail-closed external authorization-contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIMESTAMP


def _is_principal_id(value: object) -> bool:
    return type(value) is str and _PRINCIPAL_ID_RE.fullmatch(value) is not None


def _is_operation_id(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= MAX_OPERATION_ID_LENGTH
        and _OPERATION_ID_RE.fullmatch(value) is not None
        and "*" not in value
    )


@dataclass(frozen=True, slots=True)
class ExternalAuthorizationGrant:
    """One exact principal-to-operation grant in a server-owned policy."""

    principal_id: str
    operation_id: str

    def __post_init__(self) -> None:
        if not _is_principal_id(self.principal_id):
            raise ExternalAuthorizationError("authorization_policy_invalid")
        if not _is_operation_id(self.operation_id):
            raise ExternalAuthorizationError("authorization_policy_invalid")


@dataclass(frozen=True, slots=True)
class ExternalAuthorizationPolicy:
    """Server-owned exact grants for one deployment environment.

    Empty grants are valid and represent a deny-all policy. This object is a
    contract boundary, not proof that configuration came from a trusted provider;
    later runtime wiring must construct it from server-controlled configuration.
    """

    version: str
    environment: str
    grants: tuple[ExternalAuthorizationGrant, ...]

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != EXTERNAL_AUTHORIZATION_CONTRACT_VERSION
        ):
            raise ExternalAuthorizationError("authorization_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalAuthorizationError("environment_not_allowed")
        if type(self.grants) is not tuple:
            raise ExternalAuthorizationError("authorization_policy_invalid")

        seen: set[tuple[str, str]] = set()
        for grant in self.grants:
            if type(grant) is not ExternalAuthorizationGrant:
                raise ExternalAuthorizationError("authorization_policy_invalid")
            grant.__post_init__()
            key = (grant.principal_id, grant.operation_id)
            if key in seen:
                raise ExternalAuthorizationError("authorization_policy_invalid")
            seen.add(key)


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ExternalAuthorizationDecision:
    """Bounded decision evidence without runtime operation authority."""

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
        if _construction_seal is not _AUTHORIZATION_DECISION_CONSTRUCTION_SEAL:
            raise ExternalAuthorizationError(
                "authorization_decision_construction_forbidden"
            )

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
            or self.version != EXTERNAL_AUTHORIZATION_CONTRACT_VERSION
        ):
            raise ExternalAuthorizationError("authorization_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalAuthorizationError("environment_not_allowed")
        if not _is_principal_id(self.principal_id):
            raise ExternalAuthorizationError("principal_invalid")
        if not _is_operation_id(self.operation_id):
            raise ExternalAuthorizationError("operation_invalid")
        if type(self.allowed) is not bool:
            raise ExternalAuthorizationError("authorization_decision_invalid")
        if type(self.reason) is not str:
            raise ExternalAuthorizationError("authorization_decision_invalid")
        expected_reason = "granted" if self.allowed else "not_granted"
        if self.reason != expected_reason:
            raise ExternalAuthorizationError("authorization_decision_invalid")

    def __repr__(self) -> str:
        state = "allowed" if self.allowed else "denied"
        return (
            "ExternalAuthorizationDecision("
            f"version={self.version!r}, environment={self.environment!r}, "
            f"principal_id={self.principal_id!r}, operation_id={self.operation_id!r}, "
            f"state={state!r})"
        )

    def as_safe_dict(self) -> dict[str, str | bool]:
        """Return bounded authorization evidence with all runtime capabilities off."""

        return {
            "version": self.version,
            "environment": self.environment,
            "principalId": self.principal_id,
            "operationId": self.operation_id,
            "authorizationState": "allowed" if self.allowed else "denied",
            "authorizationGranted": self.allowed,
            "reason": self.reason,
            "operationExecutionAllowed": False,
            "uploadAllowed": False,
            "jobCreationAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


def authorize_external_operation(
    *,
    policy: ExternalAuthorizationPolicy,
    principal: AuthenticatedExternalPrincipal,
    operation_id: str,
    observed_at_epoch_s: int,
) -> ExternalAuthorizationDecision:
    """Evaluate one exact operation with deny-by-default authorization semantics."""

    if type(policy) is not ExternalAuthorizationPolicy:
        raise ExternalAuthorizationError("authorization_policy_invalid")
    # Revalidate restored or object-manipulated policy evidence at the authority seam.
    policy.__post_init__()

    if type(principal) is not AuthenticatedExternalPrincipal:
        raise ExternalAuthorizationError("principal_invalid")
    try:
        principal.__post_init__()
    except Exception:
        raise ExternalAuthorizationError("principal_invalid") from None

    if principal.environment != policy.environment:
        raise ExternalAuthorizationError("environment_mismatch")
    if not _is_operation_id(operation_id):
        raise ExternalAuthorizationError("operation_invalid")
    if not _is_timestamp(observed_at_epoch_s):
        raise ExternalAuthorizationError("authorization_time_invalid")
    if observed_at_epoch_s < principal.authenticated_at_epoch_s:
        raise ExternalAuthorizationError("authorization_time_invalid")
    if principal.expires_at_epoch_s <= observed_at_epoch_s:
        raise ExternalAuthorizationError("principal_expired")

    allowed = any(
        grant.principal_id == principal.principal_id
        and grant.operation_id == operation_id
        for grant in policy.grants
    )

    return ExternalAuthorizationDecision(
        version=EXTERNAL_AUTHORIZATION_CONTRACT_VERSION,
        environment=policy.environment,
        principal_id=principal.principal_id,
        operation_id=operation_id,
        allowed=allowed,
        reason="granted" if allowed else "not_granted",
        _construction_seal=_AUTHORIZATION_DECISION_CONSTRUCTION_SEAL,
    )
