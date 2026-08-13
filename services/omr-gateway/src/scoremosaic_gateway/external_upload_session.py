"""Provider-neutral Safe Upload Session reservation foundation for Gate E.4A.

This module consumes one exact Gate E.3C admission decision and derives one
server-owned upload-session identity plus bounded Safe Intake budgets. It delegates
one atomic reserve/replay operation to a later runtime adapter through a callback
seam.

A returned session decision is contract evidence only. It does not receive document
bytes, run Safe Intake, register an HTTP route, create a job, persist an artifact,
write storage, dispatch a network request, or enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Callable

from .external_admission import (
    EXTERNAL_ADMISSION_CONTRACT_VERSION,
    ExternalAdmissionDecision,
)
from .external_auth import ALLOWED_ENVIRONMENTS, MAX_TIMESTAMP
from .external_authorization import _is_operation_id as _is_authorized_operation_id
from .external_idempotency import MAX_EXTERNAL_REQUEST_BYTES
from .safe_intake import SAFE_INTAKE_MEDIA_TYPES, SAFE_INTAKE_POLICY_VERSION


EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION = "scoremosaic-external-upload-session-v1"
MIN_UPLOAD_SESSION_TTL_SECONDS = 1
MAX_UPLOAD_SESSION_TTL_SECONDS = 3600
MAX_UPLOAD_SESSION_PDF_PAGES = 200

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_PRINCIPAL_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_UPLOAD_SESSION_DECISION_CONSTRUCTION_SEAL = object()


class ExternalUploadSessionError(ValueError):
    """Stable fail-closed E.4A contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _is_principal_id(value: object) -> bool:
    return type(value) is str and _PRINCIPAL_ID_RE.fullmatch(value) is not None


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIMESTAMP


def _require_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ExternalUploadSessionError("upload_session_policy_invalid")
    return value


def _session_id(
    *,
    environment: str,
    principal_id: str,
    operation_id: str,
    admission_binding_id: str,
) -> str:
    payload = b"\0".join(
        (
            EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION.encode("ascii"),
            environment.encode("ascii"),
            principal_id.encode("ascii"),
            operation_id.encode("ascii"),
            admission_binding_id.encode("ascii"),
        )
    )
    return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ExternalUploadSessionPolicy:
    """Server-owned bounded policy for one exact external operation."""

    version: str
    environment: str
    operation_id: str
    session_ttl_seconds: int
    max_bytes: int
    max_pages: int
    intake_policy_version: str
    allowed_media_types: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION:
            raise ExternalUploadSessionError("upload_session_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalUploadSessionError("environment_not_allowed")
        if type(self.operation_id) is not str or not _is_authorized_operation_id(self.operation_id):
            raise ExternalUploadSessionError("operation_invalid")
        _require_int(
            self.session_ttl_seconds,
            minimum=MIN_UPLOAD_SESSION_TTL_SECONDS,
            maximum=MAX_UPLOAD_SESSION_TTL_SECONDS,
        )
        _require_int(self.max_bytes, minimum=1, maximum=MAX_EXTERNAL_REQUEST_BYTES)
        _require_int(self.max_pages, minimum=1, maximum=MAX_UPLOAD_SESSION_PDF_PAGES)
        if type(self.intake_policy_version) is not str or self.intake_policy_version != SAFE_INTAKE_POLICY_VERSION:
            raise ExternalUploadSessionError("intake_policy_mismatch")
        if type(self.allowed_media_types) is not tuple or self.allowed_media_types != SAFE_INTAKE_MEDIA_TYPES:
            raise ExternalUploadSessionError("intake_policy_mismatch")
        if any(type(item) is not str for item in self.allowed_media_types):
            raise ExternalUploadSessionError("intake_policy_mismatch")


@dataclass(frozen=True, slots=True)
class ExternalUploadSessionReservationRequest:
    """Immutable server-derived request for one atomic session reservation."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    session_id: str
    admission_binding_id: str
    request_sha256: str
    request_bytes: int
    observed_at_epoch_s: int
    session_ttl_seconds: int
    max_bytes: int
    max_pages: int
    intake_policy_version: str
    allowed_media_types: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION:
            raise ExternalUploadSessionError("upload_session_request_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalUploadSessionError("upload_session_request_invalid")
        if not _is_principal_id(self.principal_id):
            raise ExternalUploadSessionError("upload_session_request_invalid")
        if type(self.operation_id) is not str or not _is_authorized_operation_id(self.operation_id):
            raise ExternalUploadSessionError("upload_session_request_invalid")
        if not _is_sha256(self.session_id) or not _is_sha256(self.admission_binding_id):
            raise ExternalUploadSessionError("upload_session_request_invalid")
        if not _is_sha256(self.request_sha256):
            raise ExternalUploadSessionError("upload_session_request_invalid")
        if type(self.request_bytes) is not int or not 0 <= self.request_bytes <= MAX_EXTERNAL_REQUEST_BYTES:
            raise ExternalUploadSessionError("upload_session_request_invalid")
        if not _is_timestamp(self.observed_at_epoch_s):
            raise ExternalUploadSessionError("upload_session_request_invalid")
        _require_int(
            self.session_ttl_seconds,
            minimum=MIN_UPLOAD_SESSION_TTL_SECONDS,
            maximum=MAX_UPLOAD_SESSION_TTL_SECONDS,
        )
        _require_int(self.max_bytes, minimum=1, maximum=MAX_EXTERNAL_REQUEST_BYTES)
        _require_int(self.max_pages, minimum=1, maximum=MAX_UPLOAD_SESSION_PDF_PAGES)
        if self.intake_policy_version != SAFE_INTAKE_POLICY_VERSION:
            raise ExternalUploadSessionError("upload_session_request_invalid")
        if self.allowed_media_types != SAFE_INTAKE_MEDIA_TYPES:
            raise ExternalUploadSessionError("upload_session_request_invalid")


@dataclass(frozen=True, slots=True)
class ExternalUploadSessionReservationReceipt:
    """Atomic adapter receipt for one reserved or replayed upload session."""

    session_id: str
    admission_binding_id: str
    created_at_epoch_s: int
    expires_at_epoch_s: int
    max_bytes: int
    max_pages: int
    intake_policy_version: str
    allowed_media_types: tuple[str, ...]
    outcome: str

    def __post_init__(self) -> None:
        if not _is_sha256(self.session_id) or not _is_sha256(self.admission_binding_id):
            raise ExternalUploadSessionError("upload_session_receipt_invalid")
        if not _is_timestamp(self.created_at_epoch_s) or not _is_timestamp(self.expires_at_epoch_s):
            raise ExternalUploadSessionError("upload_session_receipt_invalid")
        if self.expires_at_epoch_s <= self.created_at_epoch_s:
            raise ExternalUploadSessionError("upload_session_receipt_invalid")
        _require_int(self.max_bytes, minimum=1, maximum=MAX_EXTERNAL_REQUEST_BYTES)
        _require_int(self.max_pages, minimum=1, maximum=MAX_UPLOAD_SESSION_PDF_PAGES)
        if self.intake_policy_version != SAFE_INTAKE_POLICY_VERSION:
            raise ExternalUploadSessionError("upload_session_receipt_invalid")
        if self.allowed_media_types != SAFE_INTAKE_MEDIA_TYPES:
            raise ExternalUploadSessionError("upload_session_receipt_invalid")
        if type(self.outcome) is not str or self.outcome not in {"reserved", "replay"}:
            raise ExternalUploadSessionError("upload_session_receipt_invalid")


ExternalUploadSessionReserver = Callable[
    [ExternalUploadSessionReservationRequest],
    ExternalUploadSessionReservationReceipt,
]


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ExternalUploadSessionDecision:
    """Bounded session evidence with every runtime authority disabled."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    state: str
    replayed: bool
    session_id: str
    admission_binding_id: str
    created_at_epoch_s: int
    expires_at_epoch_s: int
    max_bytes: int
    max_pages: int
    intake_policy_version: str
    allowed_media_types: tuple[str, ...]

    def __init__(
        self,
        *,
        version: str,
        environment: str,
        principal_id: str,
        operation_id: str,
        state: str,
        replayed: bool,
        session_id: str,
        admission_binding_id: str,
        created_at_epoch_s: int,
        expires_at_epoch_s: int,
        max_bytes: int,
        max_pages: int,
        intake_policy_version: str,
        allowed_media_types: tuple[str, ...],
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _UPLOAD_SESSION_DECISION_CONSTRUCTION_SEAL:
            raise ExternalUploadSessionError("upload_session_decision_construction_forbidden")
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "replayed", replayed)
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "admission_binding_id", admission_binding_id)
        object.__setattr__(self, "created_at_epoch_s", created_at_epoch_s)
        object.__setattr__(self, "expires_at_epoch_s", expires_at_epoch_s)
        object.__setattr__(self, "max_bytes", max_bytes)
        object.__setattr__(self, "max_pages", max_pages)
        object.__setattr__(self, "intake_policy_version", intake_policy_version)
        object.__setattr__(self, "allowed_media_types", allowed_media_types)
        self.__post_init__()

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION:
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if not _is_principal_id(self.principal_id):
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if type(self.operation_id) is not str or not _is_authorized_operation_id(self.operation_id):
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if type(self.state) is not str or self.state not in {"reserved", "replay"}:
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if type(self.replayed) is not bool or self.replayed != (self.state == "replay"):
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if not _is_sha256(self.session_id) or not _is_sha256(self.admission_binding_id):
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if not _is_timestamp(self.created_at_epoch_s) or not _is_timestamp(self.expires_at_epoch_s):
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if self.expires_at_epoch_s <= self.created_at_epoch_s:
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        _require_int(self.max_bytes, minimum=1, maximum=MAX_EXTERNAL_REQUEST_BYTES)
        _require_int(self.max_pages, minimum=1, maximum=MAX_UPLOAD_SESSION_PDF_PAGES)
        if self.intake_policy_version != SAFE_INTAKE_POLICY_VERSION:
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        if self.allowed_media_types != SAFE_INTAKE_MEDIA_TYPES:
            raise ExternalUploadSessionError("upload_session_decision_invalid")
        expected = _session_id(
            environment=self.environment,
            principal_id=self.principal_id,
            operation_id=self.operation_id,
            admission_binding_id=self.admission_binding_id,
        )
        if self.session_id != expected:
            raise ExternalUploadSessionError("upload_session_decision_invalid")

    def __repr__(self) -> str:
        return (
            "ExternalUploadSessionDecision("
            f"version={self.version!r}, environment={self.environment!r}, "
            f"principal_id={self.principal_id!r}, operation_id={self.operation_id!r}, "
            f"state={self.state!r}, replayed={self.replayed!r})"
        )

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "environment": self.environment,
            "principalId": self.principal_id,
            "operationId": self.operation_id,
            "sessionId": self.session_id,
            "sessionState": self.state,
            "replayed": self.replayed,
            "expiresAtEpochS": self.expires_at_epoch_s,
            "maxBytes": self.max_bytes,
            "maxPages": self.max_pages,
            "intakePolicyVersion": self.intake_policy_version,
            "allowedMediaTypes": list(self.allowed_media_types),
            "uploadAllowed": False,
            "operationExecutionAllowed": False,
            "jobCreationAllowed": False,
            "storageWriteAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


def reserve_external_upload_session(
    *,
    policy: ExternalUploadSessionPolicy,
    admission: ExternalAdmissionDecision,
    observed_at_epoch_s: int,
    reserver: ExternalUploadSessionReserver,
) -> ExternalUploadSessionDecision:
    """Atomically reserve or replay one server-derived Safe Upload Session."""

    if type(policy) is not ExternalUploadSessionPolicy:
        raise ExternalUploadSessionError("upload_session_policy_invalid")
    try:
        policy.__post_init__()
    except ExternalUploadSessionError:
        raise
    except Exception:
        raise ExternalUploadSessionError("upload_session_policy_invalid") from None

    if type(admission) is not ExternalAdmissionDecision:
        raise ExternalUploadSessionError("admission_invalid")
    try:
        admission.__post_init__()
    except Exception:
        raise ExternalUploadSessionError("admission_invalid") from None
    if admission.version != EXTERNAL_ADMISSION_CONTRACT_VERSION:
        raise ExternalUploadSessionError("admission_invalid")

    if policy.environment != admission.environment:
        raise ExternalUploadSessionError("environment_mismatch")
    if policy.operation_id != admission.operation_id:
        raise ExternalUploadSessionError("operation_mismatch")

    if not _is_timestamp(observed_at_epoch_s) or observed_at_epoch_s < admission.evaluated_at_epoch_s:
        raise ExternalUploadSessionError("upload_session_time_invalid")
    if observed_at_epoch_s > MAX_TIMESTAMP - policy.session_ttl_seconds:
        raise ExternalUploadSessionError("upload_session_time_invalid")

    session_id = _session_id(
        environment=admission.environment,
        principal_id=admission.principal_id,
        operation_id=admission.operation_id,
        admission_binding_id=admission.binding_id,
    )
    request = ExternalUploadSessionReservationRequest(
        version=EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION,
        environment=admission.environment,
        principal_id=admission.principal_id,
        operation_id=admission.operation_id,
        session_id=session_id,
        admission_binding_id=admission.binding_id,
        request_sha256=admission.request_sha256,
        request_bytes=admission.request_bytes,
        observed_at_epoch_s=observed_at_epoch_s,
        session_ttl_seconds=policy.session_ttl_seconds,
        max_bytes=policy.max_bytes,
        max_pages=policy.max_pages,
        intake_policy_version=policy.intake_policy_version,
        allowed_media_types=policy.allowed_media_types,
    )

    if not callable(reserver):
        raise ExternalUploadSessionError("upload_session_reserver_invalid")
    try:
        receipt = reserver(request)
    except Exception:
        raise ExternalUploadSessionError("upload_session_unavailable") from None

    if type(receipt) is not ExternalUploadSessionReservationReceipt:
        raise ExternalUploadSessionError("upload_session_receipt_invalid")
    try:
        receipt.__post_init__()
    except Exception:
        raise ExternalUploadSessionError("upload_session_receipt_invalid") from None

    if (
        receipt.session_id != request.session_id
        or receipt.admission_binding_id != request.admission_binding_id
        or receipt.max_bytes != request.max_bytes
        or receipt.max_pages != request.max_pages
        or receipt.intake_policy_version != request.intake_policy_version
        or receipt.allowed_media_types != request.allowed_media_types
        or receipt.expires_at_epoch_s - receipt.created_at_epoch_s != request.session_ttl_seconds
    ):
        raise ExternalUploadSessionError("upload_session_receipt_invalid")

    if receipt.outcome == "reserved" and receipt.created_at_epoch_s != observed_at_epoch_s:
        raise ExternalUploadSessionError("upload_session_receipt_invalid")
    if receipt.created_at_epoch_s > observed_at_epoch_s:
        raise ExternalUploadSessionError("upload_session_receipt_invalid")
    if receipt.expires_at_epoch_s <= observed_at_epoch_s:
        raise ExternalUploadSessionError("upload_session_expired")

    replayed = receipt.outcome == "replay"
    return ExternalUploadSessionDecision(
        version=EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION,
        environment=admission.environment,
        principal_id=admission.principal_id,
        operation_id=admission.operation_id,
        state="replay" if replayed else "reserved",
        replayed=replayed,
        session_id=request.session_id,
        admission_binding_id=request.admission_binding_id,
        created_at_epoch_s=receipt.created_at_epoch_s,
        expires_at_epoch_s=receipt.expires_at_epoch_s,
        max_bytes=receipt.max_bytes,
        max_pages=receipt.max_pages,
        intake_policy_version=receipt.intake_policy_version,
        allowed_media_types=receipt.allowed_media_types,
        _construction_seal=_UPLOAD_SESSION_DECISION_CONSTRUCTION_SEAL,
    )
