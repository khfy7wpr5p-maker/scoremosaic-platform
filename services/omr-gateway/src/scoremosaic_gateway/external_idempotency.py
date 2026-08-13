"""Provider-neutral external request-idempotency admission contract for Gate E.3B.

This module consumes exact Gate E.1 authenticated-principal evidence, matching
allowed Gate E.2 authorization evidence, and matching allowed Gate E.3A rate
admission evidence. It derives a principal/environment/operation-scoped slot from
a bounded opaque client idempotency key and hashes the exact immutable request
bytes on the server side before delegating one atomic reserve/replay/conflict
operation to a later runtime adapter through a callback seam.

A reserved or replay decision is contract evidence only. It does not register an
HTTP route, execute an operation, accept an upload, create a job, persist state,
dispatch a network request, or enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Callable

from .external_auth import (
    MAX_TIMESTAMP,
    AuthenticatedExternalPrincipal,
)
from .external_authorization import (
    ExternalAuthorizationDecision,
    _is_operation_id as _is_authorized_operation_id,
)
from .external_rate_limit import ExternalRateDecision


EXTERNAL_IDEMPOTENCY_CONTRACT_VERSION = "scoremosaic-external-idempotency-v1"
MIN_IDEMPOTENCY_KEY_BYTES = 8
MAX_IDEMPOTENCY_KEY_BYTES = 128
MAX_EXTERNAL_REQUEST_BYTES = 100 * 1024 * 1024

_PRINCIPAL_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_IDEMPOTENCY_DECISION_CONSTRUCTION_SEAL = object()


class ExternalIdempotencyError(ValueError):
    """Stable fail-closed external idempotency-contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIMESTAMP


def _is_principal_id(value: object) -> bool:
    return type(value) is str and _PRINCIPAL_ID_RE.fullmatch(value) is not None


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _validated_client_key(value: object) -> str:
    if type(value) is not str:
        raise ExternalIdempotencyError("idempotency_key_invalid")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        raise ExternalIdempotencyError("idempotency_key_invalid") from None
    if not MIN_IDEMPOTENCY_KEY_BYTES <= len(encoded) <= MAX_IDEMPOTENCY_KEY_BYTES:
        raise ExternalIdempotencyError("idempotency_key_invalid")
    if any(byte < 0x21 or byte > 0x7E for byte in encoded):
        raise ExternalIdempotencyError("idempotency_key_invalid")
    return value


def _validated_payload(value: object) -> bytes:
    if type(value) is not bytes:
        raise ExternalIdempotencyError("request_payload_invalid")
    if len(value) > MAX_EXTERNAL_REQUEST_BYTES:
        raise ExternalIdempotencyError("request_payload_invalid")
    return value


def _slot_id(
    *,
    environment: str,
    principal_id: str,
    operation_id: str,
    client_idempotency_key: str,
) -> str:
    payload = b"\0".join(
        (
            EXTERNAL_IDEMPOTENCY_CONTRACT_VERSION.encode("ascii"),
            environment.encode("ascii"),
            principal_id.encode("ascii"),
            operation_id.encode("ascii"),
            client_idempotency_key.encode("ascii"),
        )
    )
    return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ExternalIdempotencyReservationRequest:
    """Immutable server-derived input for one atomic idempotency reservation."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    slot_id: str
    request_sha256: str
    request_bytes: int

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != EXTERNAL_IDEMPOTENCY_CONTRACT_VERSION
        ):
            raise ExternalIdempotencyError("idempotency_request_invalid")
        if type(self.environment) is not str or not self.environment:
            raise ExternalIdempotencyError("idempotency_request_invalid")
        if not _is_principal_id(self.principal_id):
            raise ExternalIdempotencyError("idempotency_request_invalid")
        if not _is_authorized_operation_id(self.operation_id):
            raise ExternalIdempotencyError("idempotency_request_invalid")
        if not _is_sha256(self.slot_id) or not _is_sha256(self.request_sha256):
            raise ExternalIdempotencyError("idempotency_request_invalid")
        if (
            type(self.request_bytes) is not int
            or self.request_bytes < 0
            or self.request_bytes > MAX_EXTERNAL_REQUEST_BYTES
        ):
            raise ExternalIdempotencyError("idempotency_request_invalid")


@dataclass(frozen=True, slots=True)
class ExternalIdempotencyReservationReceipt:
    """Atomic reservation-adapter result bound to the exact server request."""

    slot_id: str
    request_sha256: str
    request_bytes: int
    outcome: str

    def __post_init__(self) -> None:
        if not _is_sha256(self.slot_id) or not _is_sha256(self.request_sha256):
            raise ExternalIdempotencyError("idempotency_receipt_invalid")
        if (
            type(self.request_bytes) is not int
            or self.request_bytes < 0
            or self.request_bytes > MAX_EXTERNAL_REQUEST_BYTES
        ):
            raise ExternalIdempotencyError("idempotency_receipt_invalid")
        if type(self.outcome) is not str or self.outcome not in {
            "reserved",
            "replay",
            "conflict",
        }:
            raise ExternalIdempotencyError("idempotency_receipt_invalid")


ExternalIdempotencySlotReserver = Callable[
    [ExternalIdempotencyReservationRequest],
    ExternalIdempotencyReservationReceipt,
]


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ExternalIdempotencyDecision:
    """Bounded idempotency evidence without operation execution authority."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    state: str
    replayed: bool

    def __init__(
        self,
        *,
        version: str,
        environment: str,
        principal_id: str,
        operation_id: str,
        state: str,
        replayed: bool,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _IDEMPOTENCY_DECISION_CONSTRUCTION_SEAL:
            raise ExternalIdempotencyError(
                "idempotency_decision_construction_forbidden"
            )
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "replayed", replayed)
        self.__post_init__()

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != EXTERNAL_IDEMPOTENCY_CONTRACT_VERSION
        ):
            raise ExternalIdempotencyError("idempotency_contract_version_mismatch")
        if type(self.environment) is not str or not self.environment:
            raise ExternalIdempotencyError("environment_invalid")
        if not _is_principal_id(self.principal_id):
            raise ExternalIdempotencyError("principal_invalid")
        if not _is_authorized_operation_id(self.operation_id):
            raise ExternalIdempotencyError("operation_invalid")
        if type(self.state) is not str or self.state not in {"reserved", "replay"}:
            raise ExternalIdempotencyError("idempotency_decision_invalid")
        if type(self.replayed) is not bool:
            raise ExternalIdempotencyError("idempotency_decision_invalid")
        if self.replayed != (self.state == "replay"):
            raise ExternalIdempotencyError("idempotency_decision_invalid")

    def __repr__(self) -> str:
        return (
            "ExternalIdempotencyDecision("
            f"version={self.version!r}, environment={self.environment!r}, "
            f"principal_id={self.principal_id!r}, operation_id={self.operation_id!r}, "
            f"state={self.state!r}, replayed={self.replayed!r})"
        )

    def as_safe_dict(self) -> dict[str, str | bool]:
        """Return privacy-bounded idempotency evidence with runtime authority off."""

        return {
            "version": self.version,
            "environment": self.environment,
            "principalId": self.principal_id,
            "operationId": self.operation_id,
            "idempotencyState": self.state,
            "replayed": self.replayed,
            "operationExecutionAllowed": False,
            "uploadAllowed": False,
            "jobCreationAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


def reserve_external_idempotency_slot(
    *,
    principal: AuthenticatedExternalPrincipal,
    authorization: ExternalAuthorizationDecision,
    rate_decision: ExternalRateDecision,
    operation_id: str,
    client_idempotency_key: str,
    request_payload: bytes,
    observed_at_epoch_s: int,
    reserver: ExternalIdempotencySlotReserver,
) -> ExternalIdempotencyDecision:
    """Atomically reserve, replay, or conflict one external request slot."""

    if type(principal) is not AuthenticatedExternalPrincipal:
        raise ExternalIdempotencyError("principal_invalid")
    try:
        principal.__post_init__()
    except Exception:
        raise ExternalIdempotencyError("principal_invalid") from None

    if type(authorization) is not ExternalAuthorizationDecision:
        raise ExternalIdempotencyError("authorization_invalid")
    try:
        authorization.__post_init__()
    except Exception:
        raise ExternalIdempotencyError("authorization_invalid") from None

    if type(rate_decision) is not ExternalRateDecision:
        raise ExternalIdempotencyError("rate_invalid")
    try:
        rate_decision.__post_init__()
    except Exception:
        raise ExternalIdempotencyError("rate_invalid") from None

    if type(operation_id) is not str or not _is_authorized_operation_id(operation_id):
        raise ExternalIdempotencyError("operation_invalid")

    if authorization.environment != principal.environment:
        raise ExternalIdempotencyError("environment_mismatch")
    if rate_decision.environment != principal.environment:
        raise ExternalIdempotencyError("environment_mismatch")
    if authorization.principal_id != principal.principal_id:
        raise ExternalIdempotencyError("principal_mismatch")
    if rate_decision.principal_id != principal.principal_id:
        raise ExternalIdempotencyError("principal_mismatch")
    if authorization.operation_id != operation_id:
        raise ExternalIdempotencyError("authorization_mismatch")
    if rate_decision.operation_id != operation_id:
        raise ExternalIdempotencyError("rate_mismatch")
    if not authorization.allowed:
        raise ExternalIdempotencyError("authorization_required")
    if not rate_decision.allowed:
        raise ExternalIdempotencyError("rate_required")

    if not _is_timestamp(observed_at_epoch_s):
        raise ExternalIdempotencyError("idempotency_time_invalid")
    if observed_at_epoch_s < principal.authenticated_at_epoch_s:
        raise ExternalIdempotencyError("idempotency_time_invalid")
    if principal.expires_at_epoch_s <= observed_at_epoch_s:
        raise ExternalIdempotencyError("principal_expired")

    client_key = _validated_client_key(client_idempotency_key)
    payload = _validated_payload(request_payload)
    request = ExternalIdempotencyReservationRequest(
        version=EXTERNAL_IDEMPOTENCY_CONTRACT_VERSION,
        environment=principal.environment,
        principal_id=principal.principal_id,
        operation_id=operation_id,
        slot_id=_slot_id(
            environment=principal.environment,
            principal_id=principal.principal_id,
            operation_id=operation_id,
            client_idempotency_key=client_key,
        ),
        request_sha256=sha256(payload).hexdigest(),
        request_bytes=len(payload),
    )

    if not callable(reserver):
        raise ExternalIdempotencyError("idempotency_reserver_invalid")
    try:
        receipt = reserver(request)
    except Exception:
        raise ExternalIdempotencyError("idempotency_unavailable") from None

    if type(receipt) is not ExternalIdempotencyReservationReceipt:
        raise ExternalIdempotencyError("idempotency_receipt_invalid")
    try:
        receipt.__post_init__()
    except Exception:
        raise ExternalIdempotencyError("idempotency_receipt_invalid") from None

    if (
        receipt.slot_id != request.slot_id
        or receipt.request_sha256 != request.request_sha256
        or receipt.request_bytes != request.request_bytes
    ):
        raise ExternalIdempotencyError("idempotency_receipt_invalid")

    if receipt.outcome == "conflict":
        raise ExternalIdempotencyError("idempotency_conflict")

    replayed = receipt.outcome == "replay"
    return ExternalIdempotencyDecision(
        version=EXTERNAL_IDEMPOTENCY_CONTRACT_VERSION,
        environment=principal.environment,
        principal_id=principal.principal_id,
        operation_id=operation_id,
        state="replay" if replayed else "reserved",
        replayed=replayed,
        _construction_seal=_IDEMPOTENCY_DECISION_CONSTRUCTION_SEAL,
    )
