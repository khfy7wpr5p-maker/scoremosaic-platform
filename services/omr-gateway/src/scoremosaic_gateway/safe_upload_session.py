"""Provider-neutral Safe Upload Session reservation contract for Gate E.4A.

The contract consumes one exact Gate E.3C admission decision, derives one
server-owned session identity, and delegates one atomic reserve/replay operation to
a future runtime adapter. It carries bounded Safe Intake budgets only.

No document bytes are accepted here. This module does not run Safe Intake, register
an HTTP route, create a job, persist state, write storage, dispatch a network
request, or enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Callable

from .external_admission import ExternalAdmissionDecision
from .external_auth import ALLOWED_ENVIRONMENTS, MAX_TIMESTAMP
from .external_authorization import _is_operation_id as _is_operation_id
from .external_idempotency import MAX_EXTERNAL_REQUEST_BYTES
from .safe_intake import SAFE_INTAKE_MEDIA_TYPES


SAFE_UPLOAD_SESSION_CONTRACT_VERSION = "scoremosaic-safe-upload-session-v1"
MIN_SAFE_UPLOAD_SESSION_TTL_SECONDS = 1
MAX_SAFE_UPLOAD_SESSION_TTL_SECONDS = 3600
MAX_SAFE_UPLOAD_SESSION_PDF_PAGES = 200

_PRINCIPAL_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SESSION_ID_RE = re.compile(r"upload_[0-9a-f]{40}\Z")
_SESSION_DECISION_CONSTRUCTION_SEAL = object()


class SafeUploadSessionError(ValueError):
    """Stable fail-closed E.4A failure category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIMESTAMP


def _is_principal_id(value: object) -> bool:
    return type(value) is str and _PRINCIPAL_ID_RE.fullmatch(value) is not None


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _require_int(value: object, *, minimum: int, maximum: int, category: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SafeUploadSessionError(category)
    return value


def _session_id(*, admission: ExternalAdmissionDecision) -> str:
    payload = b"\0".join(
        (
            SAFE_UPLOAD_SESSION_CONTRACT_VERSION.encode("ascii"),
            admission.environment.encode("ascii"),
            admission.principal_id.encode("ascii"),
            admission.operation_id.encode("ascii"),
            admission.binding_id.encode("ascii"),
        )
    )
    return "upload_" + sha256(payload).hexdigest()[:40]


def _admission_snapshot(value: object) -> tuple[object, ...] | None:
    if type(value) is not ExternalAdmissionDecision:
        return None
    try:
        return (
            value.version,
            value.environment,
            value.principal_id,
            value.operation_id,
            value.state,
            value.replayed,
            value.binding_id,
            value.idempotency_slot_id,
            value.request_sha256,
            value.request_bytes,
            value.evaluated_at_epoch_s,
        )
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class SafeUploadSessionPolicy:
    """Server-owned bounded session policy aligned to the current Safe Intake allowlist."""

    version: str
    environment: str
    session_ttl_seconds: int
    max_bytes: int
    max_pages: int
    allowed_media_types: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != SAFE_UPLOAD_SESSION_CONTRACT_VERSION:
            raise SafeUploadSessionError("upload_session_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise SafeUploadSessionError("environment_not_allowed")
        _require_int(
            self.session_ttl_seconds,
            minimum=MIN_SAFE_UPLOAD_SESSION_TTL_SECONDS,
            maximum=MAX_SAFE_UPLOAD_SESSION_TTL_SECONDS,
            category="upload_session_policy_invalid",
        )
        _require_int(
            self.max_bytes,
            minimum=1,
            maximum=MAX_EXTERNAL_REQUEST_BYTES,
            category="upload_session_policy_invalid",
        )
        _require_int(
            self.max_pages,
            minimum=1,
            maximum=MAX_SAFE_UPLOAD_SESSION_PDF_PAGES,
            category="upload_session_policy_invalid",
        )
        if type(self.allowed_media_types) is not tuple or self.allowed_media_types != SAFE_INTAKE_MEDIA_TYPES:
            raise SafeUploadSessionError("upload_session_policy_invalid")
        if any(type(item) is not str for item in self.allowed_media_types):
            raise SafeUploadSessionError("upload_session_policy_invalid")


def _policy_snapshot(value: object) -> tuple[object, ...] | None:
    if type(value) is not SafeUploadSessionPolicy:
        return None
    try:
        return (
            value.version,
            value.environment,
            value.session_ttl_seconds,
            value.max_bytes,
            value.max_pages,
            type(value.allowed_media_types),
            tuple(value.allowed_media_types),
        )
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class SafeUploadSessionReservationRequest:
    """Immutable server-derived request for one atomic session reservation."""

    version: str
    session_id: str
    admission_binding_id: str
    principal_id: str
    environment: str
    operation_id: str
    request_sha256: str
    request_bytes: int
    requested_at_epoch_s: int
    session_ttl_seconds: int
    max_bytes: int
    max_pages: int
    allowed_media_types: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != SAFE_UPLOAD_SESSION_CONTRACT_VERSION:
            raise SafeUploadSessionError("upload_session_request_invalid")
        if type(self.session_id) is not str or _SESSION_ID_RE.fullmatch(self.session_id) is None:
            raise SafeUploadSessionError("upload_session_request_invalid")
        if not _is_sha256(self.admission_binding_id) or not _is_principal_id(self.principal_id):
            raise SafeUploadSessionError("upload_session_request_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise SafeUploadSessionError("upload_session_request_invalid")
        if type(self.operation_id) is not str or not _is_operation_id(self.operation_id):
            raise SafeUploadSessionError("upload_session_request_invalid")
        if not _is_sha256(self.request_sha256):
            raise SafeUploadSessionError("upload_session_request_invalid")
        if type(self.request_bytes) is not int or not 0 <= self.request_bytes <= MAX_EXTERNAL_REQUEST_BYTES:
            raise SafeUploadSessionError("upload_session_request_invalid")
        if not _is_timestamp(self.requested_at_epoch_s):
            raise SafeUploadSessionError("upload_session_request_invalid")
        _require_int(
            self.session_ttl_seconds,
            minimum=MIN_SAFE_UPLOAD_SESSION_TTL_SECONDS,
            maximum=MAX_SAFE_UPLOAD_SESSION_TTL_SECONDS,
            category="upload_session_request_invalid",
        )
        _require_int(
            self.max_bytes,
            minimum=1,
            maximum=MAX_EXTERNAL_REQUEST_BYTES,
            category="upload_session_request_invalid",
        )
        _require_int(
            self.max_pages,
            minimum=1,
            maximum=MAX_SAFE_UPLOAD_SESSION_PDF_PAGES,
            category="upload_session_request_invalid",
        )
        if self.allowed_media_types != SAFE_INTAKE_MEDIA_TYPES:
            raise SafeUploadSessionError("upload_session_request_invalid")


@dataclass(frozen=True, slots=True)
class SafeUploadSessionReservationReceipt:
    """Atomic adapter result bound to the exact server-derived reservation request."""

    session_id: str
    admission_binding_id: str
    principal_id: str
    environment: str
    operation_id: str
    request_sha256: str
    request_bytes: int
    max_bytes: int
    max_pages: int
    allowed_media_types: tuple[str, ...]
    created_at_epoch_s: int
    expires_at_epoch_s: int
    outcome: str

    def __post_init__(self) -> None:
        if type(self.session_id) is not str or _SESSION_ID_RE.fullmatch(self.session_id) is None:
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        if not _is_sha256(self.admission_binding_id) or not _is_principal_id(self.principal_id):
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        if type(self.operation_id) is not str or not _is_operation_id(self.operation_id):
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        if not _is_sha256(self.request_sha256):
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        if type(self.request_bytes) is not int or not 0 <= self.request_bytes <= MAX_EXTERNAL_REQUEST_BYTES:
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        _require_int(
            self.max_bytes,
            minimum=1,
            maximum=MAX_EXTERNAL_REQUEST_BYTES,
            category="upload_session_receipt_invalid",
        )
        _require_int(
            self.max_pages,
            minimum=1,
            maximum=MAX_SAFE_UPLOAD_SESSION_PDF_PAGES,
            category="upload_session_receipt_invalid",
        )
        if self.allowed_media_types != SAFE_INTAKE_MEDIA_TYPES:
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        if not _is_timestamp(self.created_at_epoch_s) or not _is_timestamp(self.expires_at_epoch_s):
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        if self.expires_at_epoch_s <= self.created_at_epoch_s:
            raise SafeUploadSessionError("upload_session_receipt_invalid")
        if type(self.outcome) is not str or self.outcome not in {"reserved", "replay"}:
            raise SafeUploadSessionError("upload_session_receipt_invalid")


SafeUploadSessionReserver = Callable[
    [SafeUploadSessionReservationRequest],
    SafeUploadSessionReservationReceipt,
]


@dataclass(frozen=True, slots=True, repr=False, init=False)
class SafeUploadSessionDecision:
    """Bounded reservation evidence; never upload or storage authority."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    state: str
    replayed: bool
    session_id: str
    admission_binding_id: str
    request_sha256: str
    request_bytes: int
    created_at_epoch_s: int
    expires_at_epoch_s: int
    max_bytes: int
    max_pages: int
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
        request_sha256: str,
        request_bytes: int,
        created_at_epoch_s: int,
        expires_at_epoch_s: int,
        max_bytes: int = 1,
        max_pages: int = 1,
        allowed_media_types: tuple[str, ...] = SAFE_INTAKE_MEDIA_TYPES,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _SESSION_DECISION_CONSTRUCTION_SEAL:
            raise SafeUploadSessionError("upload_session_decision_construction_forbidden")
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "replayed", replayed)
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "admission_binding_id", admission_binding_id)
        object.__setattr__(self, "request_sha256", request_sha256)
        object.__setattr__(self, "request_bytes", request_bytes)
        object.__setattr__(self, "created_at_epoch_s", created_at_epoch_s)
        object.__setattr__(self, "expires_at_epoch_s", expires_at_epoch_s)
        object.__setattr__(self, "max_bytes", max_bytes)
        object.__setattr__(self, "max_pages", max_pages)
        object.__setattr__(self, "allowed_media_types", allowed_media_types)
        self.__post_init__()

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != SAFE_UPLOAD_SESSION_CONTRACT_VERSION:
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if not _is_principal_id(self.principal_id):
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if type(self.operation_id) is not str or not _is_operation_id(self.operation_id):
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if type(self.state) is not str or self.state not in {"reserved", "replay"}:
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if type(self.replayed) is not bool or self.replayed != (self.state == "replay"):
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if type(self.session_id) is not str or _SESSION_ID_RE.fullmatch(self.session_id) is None:
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if not _is_sha256(self.admission_binding_id) or not _is_sha256(self.request_sha256):
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if type(self.request_bytes) is not int or not 0 <= self.request_bytes <= MAX_EXTERNAL_REQUEST_BYTES:
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if not _is_timestamp(self.created_at_epoch_s) or not _is_timestamp(self.expires_at_epoch_s):
            raise SafeUploadSessionError("upload_session_decision_invalid")
        if self.expires_at_epoch_s <= self.created_at_epoch_s:
            raise SafeUploadSessionError("upload_session_decision_invalid")
        _require_int(
            self.max_bytes,
            minimum=1,
            maximum=MAX_EXTERNAL_REQUEST_BYTES,
            category="upload_session_decision_invalid",
        )
        _require_int(
            self.max_pages,
            minimum=1,
            maximum=MAX_SAFE_UPLOAD_SESSION_PDF_PAGES,
            category="upload_session_decision_invalid",
        )
        if self.allowed_media_types != SAFE_INTAKE_MEDIA_TYPES:
            raise SafeUploadSessionError("upload_session_decision_invalid")

    def __repr__(self) -> str:
        return (
            "SafeUploadSessionDecision("
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
            "allowedMediaTypes": list(self.allowed_media_types),
            "uploadAllowed": False,
            "operationExecutionAllowed": False,
            "jobCreationAllowed": False,
            "storageWriteAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


def reserve_safe_upload_session(
    *,
    policy: SafeUploadSessionPolicy,
    admission: ExternalAdmissionDecision,
    observed_at_epoch_s: int,
    reserver: SafeUploadSessionReserver,
) -> SafeUploadSessionDecision:
    """Reserve/replay exactly one session for the exact freshly evaluated admission."""

    if type(policy) is not SafeUploadSessionPolicy:
        raise SafeUploadSessionError("upload_session_policy_invalid")
    try:
        policy.__post_init__()
    except SafeUploadSessionError:
        raise
    except Exception:
        raise SafeUploadSessionError("upload_session_policy_invalid") from None

    if type(admission) is not ExternalAdmissionDecision:
        raise SafeUploadSessionError("admission_invalid")
    try:
        admission.__post_init__()
    except Exception:
        raise SafeUploadSessionError("admission_invalid") from None

    initial_policy = _policy_snapshot(policy)
    initial_admission = _admission_snapshot(admission)
    if initial_policy is None or initial_admission is None:
        raise SafeUploadSessionError("upload_session_authority_invalid")

    if policy.environment != admission.environment:
        raise SafeUploadSessionError("environment_mismatch")
    if not _is_timestamp(observed_at_epoch_s):
        raise SafeUploadSessionError("upload_session_time_invalid")
    if observed_at_epoch_s != admission.evaluated_at_epoch_s:
        raise SafeUploadSessionError("upload_session_time_mismatch")
    if observed_at_epoch_s > MAX_TIMESTAMP - policy.session_ttl_seconds:
        raise SafeUploadSessionError("upload_session_time_invalid")

    request = SafeUploadSessionReservationRequest(
        version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
        session_id=_session_id(admission=admission),
        admission_binding_id=admission.binding_id,
        principal_id=admission.principal_id,
        environment=admission.environment,
        operation_id=admission.operation_id,
        request_sha256=admission.request_sha256,
        request_bytes=admission.request_bytes,
        requested_at_epoch_s=observed_at_epoch_s,
        session_ttl_seconds=policy.session_ttl_seconds,
        max_bytes=policy.max_bytes,
        max_pages=policy.max_pages,
        allowed_media_types=policy.allowed_media_types,
    )

    if not callable(reserver):
        raise SafeUploadSessionError("upload_session_reserver_invalid")

    provider_request = SafeUploadSessionReservationRequest(
        version=request.version,
        session_id=request.session_id,
        admission_binding_id=request.admission_binding_id,
        principal_id=request.principal_id,
        environment=request.environment,
        operation_id=request.operation_id,
        request_sha256=request.request_sha256,
        request_bytes=request.request_bytes,
        requested_at_epoch_s=request.requested_at_epoch_s,
        session_ttl_seconds=request.session_ttl_seconds,
        max_bytes=request.max_bytes,
        max_pages=request.max_pages,
        allowed_media_types=request.allowed_media_types,
    )
    try:
        receipt = reserver(provider_request)
    except Exception:
        raise SafeUploadSessionError("upload_session_unavailable") from None

    if _policy_snapshot(policy) != initial_policy or _admission_snapshot(admission) != initial_admission:
        raise SafeUploadSessionError("upload_session_authority_mutated")

    try:
        request.__post_init__()
    except Exception:
        raise SafeUploadSessionError("upload_session_request_invalid") from None

    if type(receipt) is not SafeUploadSessionReservationReceipt:
        raise SafeUploadSessionError("upload_session_receipt_invalid")
    try:
        receipt.__post_init__()
    except Exception:
        raise SafeUploadSessionError("upload_session_receipt_invalid") from None

    if (
        receipt.session_id != request.session_id
        or receipt.admission_binding_id != request.admission_binding_id
        or receipt.principal_id != request.principal_id
        or receipt.environment != request.environment
        or receipt.operation_id != request.operation_id
        or receipt.request_sha256 != request.request_sha256
        or receipt.request_bytes != request.request_bytes
        or receipt.max_bytes != request.max_bytes
        or receipt.max_pages != request.max_pages
        or receipt.allowed_media_types != request.allowed_media_types
        or receipt.expires_at_epoch_s - receipt.created_at_epoch_s != request.session_ttl_seconds
    ):
        raise SafeUploadSessionError("upload_session_receipt_invalid")

    if receipt.outcome == "reserved" and receipt.created_at_epoch_s != request.requested_at_epoch_s:
        raise SafeUploadSessionError("upload_session_receipt_invalid")
    if receipt.created_at_epoch_s > request.requested_at_epoch_s:
        raise SafeUploadSessionError("upload_session_receipt_invalid")
    if receipt.expires_at_epoch_s <= request.requested_at_epoch_s:
        raise SafeUploadSessionError("upload_session_expired")

    replayed = receipt.outcome == "replay"
    return SafeUploadSessionDecision(
        version=SAFE_UPLOAD_SESSION_CONTRACT_VERSION,
        environment=request.environment,
        principal_id=request.principal_id,
        operation_id=request.operation_id,
        state="replay" if replayed else "reserved",
        replayed=replayed,
        session_id=request.session_id,
        admission_binding_id=request.admission_binding_id,
        request_sha256=request.request_sha256,
        request_bytes=request.request_bytes,
        created_at_epoch_s=receipt.created_at_epoch_s,
        expires_at_epoch_s=receipt.expires_at_epoch_s,
        max_bytes=receipt.max_bytes,
        max_pages=receipt.max_pages,
        allowed_media_types=receipt.allowed_media_types,
        _construction_seal=_SESSION_DECISION_CONSTRUCTION_SEAL,
    )
