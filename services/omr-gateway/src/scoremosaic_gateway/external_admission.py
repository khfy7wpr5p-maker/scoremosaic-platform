"""Fail-closed external admission composition contract for Gate E.3C.

This module composes the existing Gate E.1/E.2/E.3A/E.3B foundations without
activating an external route or runtime capability. Every composition call performs
a fresh E.3A rate reservation internally and immediately binds that result to one
E.3B idempotency reserve/replay decision for the exact immutable request bytes.

The returned binding is server-derived contract evidence only. It does not execute
an operation, accept an upload, create a job, persist state, dispatch a network
request, or enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .external_auth import (
    ALLOWED_ENVIRONMENTS,
    MAX_TIMESTAMP,
    AuthenticatedExternalPrincipal,
)
from .external_authorization import (
    ExternalAuthorizationDecision,
    _is_operation_id as _is_authorized_operation_id,
)
from .external_idempotency import (
    MAX_EXTERNAL_REQUEST_BYTES,
    ExternalIdempotencyDecision,
    ExternalIdempotencyError,
    ExternalIdempotencyReservationRequest,
    ExternalIdempotencySlotReserver,
    reserve_external_idempotency_slot,
)
from .external_rate_limit import (
    ExternalRateLimitError,
    ExternalRateLimitPolicy,
    ExternalRateSlotReserver,
    reserve_external_rate_slot,
)


EXTERNAL_ADMISSION_CONTRACT_VERSION = "scoremosaic-external-admission-v1"

_PRINCIPAL_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ADMISSION_DECISION_CONSTRUCTION_SEAL = object()


class ExternalAdmissionError(ValueError):
    """Stable fail-closed external admission-composition failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIMESTAMP


def _is_principal_id(value: object) -> bool:
    return type(value) is str and _PRINCIPAL_ID_RE.fullmatch(value) is not None


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _binding_id(
    *,
    environment: str,
    principal_id: str,
    operation_id: str,
    idempotency_slot_id: str,
    request_sha256: str,
    request_bytes: int,
) -> str:
    payload = b"\0".join(
        (
            EXTERNAL_ADMISSION_CONTRACT_VERSION.encode("ascii"),
            environment.encode("ascii"),
            principal_id.encode("ascii"),
            operation_id.encode("ascii"),
            idempotency_slot_id.encode("ascii"),
            request_sha256.encode("ascii"),
            str(request_bytes).encode("ascii"),
        )
    )
    return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ExternalAdmissionDecision:
    """Internal exact-request admission binding with all runtime authority disabled."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    state: str
    replayed: bool
    binding_id: str
    idempotency_slot_id: str
    request_sha256: str
    request_bytes: int
    evaluated_at_epoch_s: int

    def __init__(
        self,
        *,
        version: str,
        environment: str,
        principal_id: str,
        operation_id: str,
        state: str,
        replayed: bool,
        binding_id: str,
        idempotency_slot_id: str,
        request_sha256: str,
        request_bytes: int,
        evaluated_at_epoch_s: int,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _ADMISSION_DECISION_CONSTRUCTION_SEAL:
            raise ExternalAdmissionError("admission_decision_construction_forbidden")

        object.__setattr__(self, "version", version)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "replayed", replayed)
        object.__setattr__(self, "binding_id", binding_id)
        object.__setattr__(self, "idempotency_slot_id", idempotency_slot_id)
        object.__setattr__(self, "request_sha256", request_sha256)
        object.__setattr__(self, "request_bytes", request_bytes)
        object.__setattr__(self, "evaluated_at_epoch_s", evaluated_at_epoch_s)
        self.__post_init__()

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != EXTERNAL_ADMISSION_CONTRACT_VERSION
        ):
            raise ExternalAdmissionError("admission_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalAdmissionError("environment_not_allowed")
        if not _is_principal_id(self.principal_id):
            raise ExternalAdmissionError("principal_invalid")
        if not _is_authorized_operation_id(self.operation_id):
            raise ExternalAdmissionError("operation_invalid")
        if type(self.state) is not str or self.state not in {"reserved", "replay"}:
            raise ExternalAdmissionError("admission_decision_invalid")
        if type(self.replayed) is not bool or self.replayed != (self.state == "replay"):
            raise ExternalAdmissionError("admission_decision_invalid")
        if not _is_sha256(self.binding_id):
            raise ExternalAdmissionError("admission_binding_invalid")
        if not _is_sha256(self.idempotency_slot_id) or not _is_sha256(
            self.request_sha256
        ):
            raise ExternalAdmissionError("admission_binding_invalid")
        if (
            type(self.request_bytes) is not int
            or self.request_bytes < 0
            or self.request_bytes > MAX_EXTERNAL_REQUEST_BYTES
        ):
            raise ExternalAdmissionError("admission_binding_invalid")
        if not _is_timestamp(self.evaluated_at_epoch_s):
            raise ExternalAdmissionError("admission_time_invalid")
        expected_binding = _binding_id(
            environment=self.environment,
            principal_id=self.principal_id,
            operation_id=self.operation_id,
            idempotency_slot_id=self.idempotency_slot_id,
            request_sha256=self.request_sha256,
            request_bytes=self.request_bytes,
        )
        if self.binding_id != expected_binding:
            raise ExternalAdmissionError("admission_binding_invalid")

    def __repr__(self) -> str:
        return (
            "ExternalAdmissionDecision("
            f"version={self.version!r}, environment={self.environment!r}, "
            f"principal_id={self.principal_id!r}, operation_id={self.operation_id!r}, "
            f"state={self.state!r}, replayed={self.replayed!r})"
        )

    def as_safe_dict(self) -> dict[str, str | bool]:
        """Return bounded admission evidence without internal binding material."""

        return {
            "version": self.version,
            "environment": self.environment,
            "principalId": self.principal_id,
            "operationId": self.operation_id,
            "admissionState": self.state,
            "replayed": self.replayed,
            "freshRateEvaluated": True,
            "operationExecutionAllowed": False,
            "uploadAllowed": False,
            "jobCreationAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


def compose_external_admission(
    *,
    rate_policy: ExternalRateLimitPolicy,
    principal: AuthenticatedExternalPrincipal,
    authorization: ExternalAuthorizationDecision,
    operation_id: str,
    client_idempotency_key: str,
    request_payload: bytes,
    observed_at_epoch_s: int,
    rate_reserver: ExternalRateSlotReserver,
    idempotency_reserver: ExternalIdempotencySlotReserver,
) -> ExternalAdmissionDecision:
    """Evaluate fresh rate admission then bind one exact E.3B request decision."""

    try:
        rate_decision = reserve_external_rate_slot(
            policy=rate_policy,
            principal=principal,
            authorization=authorization,
            operation_id=operation_id,
            observed_at_epoch_s=observed_at_epoch_s,
            reserver=rate_reserver,
        )
    except ExternalRateLimitError as exc:
        raise ExternalAdmissionError(exc.category) from None

    if not rate_decision.allowed:
        raise ExternalAdmissionError("rate_limited")

    captured_request: ExternalIdempotencyReservationRequest | None = None

    def capture_and_reserve(
        request: ExternalIdempotencyReservationRequest,
    ):
        nonlocal captured_request
        if captured_request is not None:
            raise ExternalAdmissionError("idempotency_callback_invalid")
        if type(request) is not ExternalIdempotencyReservationRequest:
            raise ExternalAdmissionError("idempotency_callback_invalid")
        captured_request = request
        return idempotency_reserver(request)

    try:
        idempotency_decision = reserve_external_idempotency_slot(
            principal=principal,
            authorization=authorization,
            rate_decision=rate_decision,
            operation_id=operation_id,
            client_idempotency_key=client_idempotency_key,
            request_payload=request_payload,
            observed_at_epoch_s=observed_at_epoch_s,
            reserver=capture_and_reserve,
        )
    except ExternalIdempotencyError as exc:
        raise ExternalAdmissionError(exc.category) from None

    if captured_request is None:
        raise ExternalAdmissionError("idempotency_binding_missing")
    if type(idempotency_decision) is not ExternalIdempotencyDecision:
        raise ExternalAdmissionError("idempotency_decision_invalid")
    try:
        idempotency_decision.__post_init__()
        captured_request.__post_init__()
    except Exception:
        raise ExternalAdmissionError("idempotency_binding_invalid") from None

    if (
        idempotency_decision.environment != principal.environment
        or idempotency_decision.principal_id != principal.principal_id
        or idempotency_decision.operation_id != operation_id
        or captured_request.environment != principal.environment
        or captured_request.principal_id != principal.principal_id
        or captured_request.operation_id != operation_id
    ):
        raise ExternalAdmissionError("idempotency_binding_mismatch")

    binding_id = _binding_id(
        environment=principal.environment,
        principal_id=principal.principal_id,
        operation_id=operation_id,
        idempotency_slot_id=captured_request.slot_id,
        request_sha256=captured_request.request_sha256,
        request_bytes=captured_request.request_bytes,
    )

    return ExternalAdmissionDecision(
        version=EXTERNAL_ADMISSION_CONTRACT_VERSION,
        environment=principal.environment,
        principal_id=principal.principal_id,
        operation_id=operation_id,
        state=idempotency_decision.state,
        replayed=idempotency_decision.replayed,
        binding_id=binding_id,
        idempotency_slot_id=captured_request.slot_id,
        request_sha256=captured_request.request_sha256,
        request_bytes=captured_request.request_bytes,
        evaluated_at_epoch_s=observed_at_epoch_s,
        _construction_seal=_ADMISSION_DECISION_CONSTRUCTION_SEAL,
    )
