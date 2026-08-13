"""Fail-closed Safe Intake session finalization contract for Gate E.4B.

This module consumes one exact E.4A Safe Upload Session decision and one complete
immutable document payload. It requires the session to still be active, evaluates
the exact bytes through the completed Gate B ``decide_safe_intake()`` boundary,
derives a server-owned document digest/finalization identity, and delegates one
atomic reserve/replay/conflict decision to a future stateful provider.

The provider never receives raw document bytes or the original filename. E.4B
produces bounded finalization evidence only. It does not register an HTTP route,
write storage, create a job, bind an immutable source/job, dispatch a network
request, or enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Callable

from .external_auth import ALLOWED_ENVIRONMENTS, MAX_TIMESTAMP
from .intake_decision import SafeIntakeDecision, decide_safe_intake
from .safe_upload_session import (
    SAFE_UPLOAD_SESSION_OPERATION_ID,
    SafeUploadSessionDecision,
    SafeUploadSessionError,
)


SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION = "scoremosaic-safe-upload-finalization-v1"

_PRINCIPAL_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SESSION_ID_RE = re.compile(r"upload_[0-9a-f]{40}\Z")
_FINALIZATION_ID_RE = re.compile(r"final_[0-9a-f]{40}\Z")
_DECISION_CONSTRUCTION_SEAL = object()


class SafeUploadFinalizationError(ValueError):
    """Stable fail-closed E.4B failure category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIMESTAMP


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _is_principal_id(value: object) -> bool:
    return type(value) is str and _PRINCIPAL_ID_RE.fullmatch(value) is not None


def _session_snapshot(value: object) -> tuple[object, ...] | None:
    if type(value) is not SafeUploadSessionDecision:
        return None
    try:
        return (
            value.version,
            value.environment,
            value.principal_id,
            value.operation_id,
            value.state,
            value.replayed,
            value.session_id,
            value.admission_binding_id,
            value.request_sha256,
            value.request_bytes,
            value.created_at_epoch_s,
            value.expires_at_epoch_s,
            value.max_bytes,
            value.max_pages,
            type(value.allowed_media_types),
            tuple(value.allowed_media_types),
        )
    except Exception:
        return None


def _intake_shape(decision: SafeIntakeDecision) -> tuple[object, ...]:
    return (
        decision.policy_version,
        decision.format_id,
        decision.media_type,
        decision.observed_bytes,
        decision.page_count,
        decision.image_width,
        decision.image_height,
        decision.image_pixel_count,
    )


def _finalization_id(*, session_id: str, document_sha256: str, intake: SafeIntakeDecision) -> str:
    payload = b"\0".join(
        (
            SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION.encode("ascii"),
            session_id.encode("ascii"),
            document_sha256.encode("ascii"),
            intake.policy_version.encode("ascii"),
            intake.format_id.encode("ascii"),
            intake.media_type.encode("ascii"),
            str(intake.observed_bytes).encode("ascii"),
        )
    )
    return "final_" + sha256(payload).hexdigest()[:40]


def _validate_intake_fields(
    *,
    format_id: object,
    media_type: object,
    observed_bytes: object,
    page_count: object,
    image_width: object,
    image_height: object,
    image_pixel_count: object,
) -> None:
    if type(format_id) is not str or format_id not in {"pdf", "jpeg", "png"}:
        raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")
    expected_media_type = {
        "pdf": "application/pdf",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }[format_id]
    if type(media_type) is not str or media_type != expected_media_type:
        raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")
    if type(observed_bytes) is not int or observed_bytes <= 0:
        raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")

    if format_id == "pdf":
        if type(page_count) is not int or page_count <= 0:
            raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")
        if any(value is not None for value in (image_width, image_height, image_pixel_count)):
            raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")
        return

    if page_count is not None:
        raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")
    if any(type(value) is not int or value <= 0 for value in (image_width, image_height, image_pixel_count)):
        raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")
    if image_width * image_height != image_pixel_count:
        raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")


@dataclass(frozen=True, slots=True)
class SafeUploadFinalizationRequest:
    """Bounded server-derived finalization request; contains no raw document bytes."""

    version: str
    session_id: str
    admission_binding_id: str
    principal_id: str
    environment: str
    operation_id: str
    finalization_id: str
    document_sha256: str
    observed_bytes: int
    format_id: str
    media_type: str
    page_count: int | None
    image_width: int | None
    image_height: int | None
    image_pixel_count: int | None
    session_created_at_epoch_s: int
    session_expires_at_epoch_s: int
    requested_at_epoch_s: int

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION:
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        if type(self.session_id) is not str or _SESSION_ID_RE.fullmatch(self.session_id) is None:
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        if not _is_sha256(self.admission_binding_id) or not _is_principal_id(self.principal_id):
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        if type(self.operation_id) is not str or self.operation_id != SAFE_UPLOAD_SESSION_OPERATION_ID:
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        if type(self.finalization_id) is not str or _FINALIZATION_ID_RE.fullmatch(self.finalization_id) is None:
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        if not _is_sha256(self.document_sha256):
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        try:
            _validate_intake_fields(
                format_id=self.format_id,
                media_type=self.media_type,
                observed_bytes=self.observed_bytes,
                page_count=self.page_count,
                image_width=self.image_width,
                image_height=self.image_height,
                image_pixel_count=self.image_pixel_count,
            )
        except SafeUploadFinalizationError:
            raise SafeUploadFinalizationError("upload_finalization_request_invalid") from None
        if not all(
            _is_timestamp(value)
            for value in (
                self.session_created_at_epoch_s,
                self.session_expires_at_epoch_s,
                self.requested_at_epoch_s,
            )
        ):
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        if not self.session_created_at_epoch_s < self.session_expires_at_epoch_s:
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")
        if not self.session_created_at_epoch_s <= self.requested_at_epoch_s < self.session_expires_at_epoch_s:
            raise SafeUploadFinalizationError("upload_finalization_request_invalid")


@dataclass(frozen=True, slots=True)
class SafeUploadFinalizationReceipt:
    """Atomic provider result bound to the exact server-derived finalization request."""

    version: str
    session_id: str
    admission_binding_id: str
    principal_id: str
    environment: str
    operation_id: str
    finalization_id: str
    document_sha256: str
    observed_bytes: int
    format_id: str
    media_type: str
    page_count: int | None
    image_width: int | None
    image_height: int | None
    image_pixel_count: int | None
    finalized_at_epoch_s: int
    outcome: str

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION:
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
        if type(self.session_id) is not str or _SESSION_ID_RE.fullmatch(self.session_id) is None:
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
        if not _is_sha256(self.admission_binding_id) or not _is_principal_id(self.principal_id):
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
        if type(self.operation_id) is not str or self.operation_id != SAFE_UPLOAD_SESSION_OPERATION_ID:
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
        if type(self.finalization_id) is not str or _FINALIZATION_ID_RE.fullmatch(self.finalization_id) is None:
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
        if not _is_sha256(self.document_sha256):
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
        try:
            _validate_intake_fields(
                format_id=self.format_id,
                media_type=self.media_type,
                observed_bytes=self.observed_bytes,
                page_count=self.page_count,
                image_width=self.image_width,
                image_height=self.image_height,
                image_pixel_count=self.image_pixel_count,
            )
        except SafeUploadFinalizationError:
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid") from None
        if not _is_timestamp(self.finalized_at_epoch_s):
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
        if type(self.outcome) is not str or self.outcome not in {"reserved", "replay", "conflict"}:
            raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")


SafeUploadFinalizer = Callable[[SafeUploadFinalizationRequest], SafeUploadFinalizationReceipt]


@dataclass(frozen=True, slots=True, repr=False, init=False)
class SafeUploadFinalizationDecision:
    """Bounded accepted Safe Intake evidence; never storage or job authority."""

    version: str
    session_id: str
    admission_binding_id: str
    principal_id: str
    environment: str
    operation_id: str
    state: str
    replayed: bool
    finalization_id: str
    document_sha256: str
    observed_bytes: int
    format_id: str
    media_type: str
    page_count: int | None
    image_width: int | None
    image_height: int | None
    image_pixel_count: int | None
    finalized_at_epoch_s: int

    def __init__(
        self,
        *,
        version: str,
        session_id: str,
        admission_binding_id: str,
        principal_id: str,
        environment: str,
        operation_id: str,
        state: str,
        replayed: bool,
        finalization_id: str,
        document_sha256: str,
        observed_bytes: int,
        format_id: str,
        media_type: str,
        page_count: int | None,
        image_width: int | None,
        image_height: int | None,
        image_pixel_count: int | None,
        finalized_at_epoch_s: int,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _DECISION_CONSTRUCTION_SEAL:
            raise SafeUploadFinalizationError("upload_finalization_decision_construction_forbidden")
        for field, value in (
            ("version", version),
            ("session_id", session_id),
            ("admission_binding_id", admission_binding_id),
            ("principal_id", principal_id),
            ("environment", environment),
            ("operation_id", operation_id),
            ("state", state),
            ("replayed", replayed),
            ("finalization_id", finalization_id),
            ("document_sha256", document_sha256),
            ("observed_bytes", observed_bytes),
            ("format_id", format_id),
            ("media_type", media_type),
            ("page_count", page_count),
            ("image_width", image_width),
            ("image_height", image_height),
            ("image_pixel_count", image_pixel_count),
            ("finalized_at_epoch_s", finalized_at_epoch_s),
        ):
            object.__setattr__(self, field, value)
        self.__post_init__()

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION:
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        if type(self.session_id) is not str or _SESSION_ID_RE.fullmatch(self.session_id) is None:
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        if not _is_sha256(self.admission_binding_id) or not _is_principal_id(self.principal_id):
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        if type(self.operation_id) is not str or self.operation_id != SAFE_UPLOAD_SESSION_OPERATION_ID:
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        if type(self.state) is not str or self.state not in {"reserved", "replay"}:
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        if type(self.replayed) is not bool or self.replayed != (self.state == "replay"):
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        if type(self.finalization_id) is not str or _FINALIZATION_ID_RE.fullmatch(self.finalization_id) is None:
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        if not _is_sha256(self.document_sha256):
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")
        try:
            _validate_intake_fields(
                format_id=self.format_id,
                media_type=self.media_type,
                observed_bytes=self.observed_bytes,
                page_count=self.page_count,
                image_width=self.image_width,
                image_height=self.image_height,
                image_pixel_count=self.image_pixel_count,
            )
        except SafeUploadFinalizationError:
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid") from None
        if not _is_timestamp(self.finalized_at_epoch_s):
            raise SafeUploadFinalizationError("upload_finalization_decision_invalid")

    def __repr__(self) -> str:
        return (
            "SafeUploadFinalizationDecision("
            f"version={self.version!r}, environment={self.environment!r}, "
            f"principal_id={self.principal_id!r}, operation_id={self.operation_id!r}, "
            f"state={self.state!r}, replayed={self.replayed!r}, format_id={self.format_id!r})"
        )

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "environment": self.environment,
            "principalId": self.principal_id,
            "operationId": self.operation_id,
            "sessionId": self.session_id,
            "finalizationId": self.finalization_id,
            "finalizationState": self.state,
            "replayed": self.replayed,
            "safeIntakeAccepted": True,
            "formatId": self.format_id,
            "mediaType": self.media_type,
            "observedBytes": self.observed_bytes,
            "pageCount": self.page_count,
            "imageWidth": self.image_width,
            "imageHeight": self.image_height,
            "imagePixelCount": self.image_pixel_count,
            "uploadAllowed": False,
            "storageWriteAllowed": False,
            "jobCreationAllowed": False,
            "operationExecutionAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


def finalize_safe_upload_session(
    *,
    session: SafeUploadSessionDecision,
    payload: bytes,
    original_filename: str,
    declared_media_type: str | None,
    observed_at_epoch_s: int,
    finalizer: SafeUploadFinalizer,
) -> SafeUploadFinalizationDecision:
    """Finalize exact immutable document bytes only after Gate B Safe Intake passes."""

    if type(session) is not SafeUploadSessionDecision:
        raise SafeUploadFinalizationError("upload_session_invalid")
    try:
        session.__post_init__()
    except SafeUploadSessionError:
        raise SafeUploadFinalizationError("upload_session_invalid") from None
    except Exception:
        raise SafeUploadFinalizationError("upload_session_invalid") from None

    initial_session = _session_snapshot(session)
    if initial_session is None:
        raise SafeUploadFinalizationError("upload_session_invalid")
    if session.operation_id != SAFE_UPLOAD_SESSION_OPERATION_ID:
        raise SafeUploadFinalizationError("upload_session_operation_mismatch")
    if not _is_timestamp(observed_at_epoch_s):
        raise SafeUploadFinalizationError("upload_finalization_time_invalid")
    if not session.created_at_epoch_s <= observed_at_epoch_s < session.expires_at_epoch_s:
        raise SafeUploadFinalizationError("upload_session_expired")
    if type(payload) is not bytes:
        raise SafeUploadFinalizationError("upload_finalization_payload_invalid")
    if type(original_filename) is not str:
        raise SafeUploadFinalizationError("upload_finalization_filename_invalid")
    if declared_media_type is not None and type(declared_media_type) is not str:
        raise SafeUploadFinalizationError("upload_finalization_media_type_invalid")
    if declared_media_type not in session.allowed_media_types:
        raise SafeUploadFinalizationError("upload_finalization_media_type_invalid")

    intake = decide_safe_intake(
        payload,
        original_filename=original_filename,
        declared_media_type=declared_media_type,
        max_bytes=session.max_bytes,
        max_pages=session.max_pages,
    )

    if _session_snapshot(session) != initial_session:
        raise SafeUploadFinalizationError("upload_finalization_authority_mutated")
    if type(intake) is not SafeIntakeDecision:
        raise SafeUploadFinalizationError("upload_finalization_evidence_invalid")

    document_sha256 = sha256(payload).hexdigest()
    request = SafeUploadFinalizationRequest(
        version=SAFE_UPLOAD_FINALIZATION_CONTRACT_VERSION,
        session_id=session.session_id,
        admission_binding_id=session.admission_binding_id,
        principal_id=session.principal_id,
        environment=session.environment,
        operation_id=session.operation_id,
        finalization_id=_finalization_id(
            session_id=session.session_id,
            document_sha256=document_sha256,
            intake=intake,
        ),
        document_sha256=document_sha256,
        observed_bytes=intake.observed_bytes,
        format_id=intake.format_id,
        media_type=intake.media_type,
        page_count=intake.page_count,
        image_width=intake.image_width,
        image_height=intake.image_height,
        image_pixel_count=intake.image_pixel_count,
        session_created_at_epoch_s=session.created_at_epoch_s,
        session_expires_at_epoch_s=session.expires_at_epoch_s,
        requested_at_epoch_s=observed_at_epoch_s,
    )

    if not callable(finalizer):
        raise SafeUploadFinalizationError("upload_finalizer_invalid")

    provider_request = SafeUploadFinalizationRequest(
        version=request.version,
        session_id=request.session_id,
        admission_binding_id=request.admission_binding_id,
        principal_id=request.principal_id,
        environment=request.environment,
        operation_id=request.operation_id,
        finalization_id=request.finalization_id,
        document_sha256=request.document_sha256,
        observed_bytes=request.observed_bytes,
        format_id=request.format_id,
        media_type=request.media_type,
        page_count=request.page_count,
        image_width=request.image_width,
        image_height=request.image_height,
        image_pixel_count=request.image_pixel_count,
        session_created_at_epoch_s=request.session_created_at_epoch_s,
        session_expires_at_epoch_s=request.session_expires_at_epoch_s,
        requested_at_epoch_s=request.requested_at_epoch_s,
    )
    try:
        receipt = finalizer(provider_request)
    except Exception:
        raise SafeUploadFinalizationError("upload_finalization_unavailable") from None

    if _session_snapshot(session) != initial_session:
        raise SafeUploadFinalizationError("upload_finalization_authority_mutated")
    try:
        request.__post_init__()
    except Exception:
        raise SafeUploadFinalizationError("upload_finalization_request_invalid") from None

    if type(receipt) is not SafeUploadFinalizationReceipt:
        raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
    try:
        receipt.__post_init__()
    except Exception:
        raise SafeUploadFinalizationError("upload_finalization_receipt_invalid") from None

    if (
        receipt.version != request.version
        or receipt.session_id != request.session_id
        or receipt.admission_binding_id != request.admission_binding_id
        or receipt.principal_id != request.principal_id
        or receipt.environment != request.environment
        or receipt.operation_id != request.operation_id
        or receipt.finalization_id != request.finalization_id
        or receipt.document_sha256 != request.document_sha256
        or receipt.observed_bytes != request.observed_bytes
        or receipt.format_id != request.format_id
        or receipt.media_type != request.media_type
        or receipt.page_count != request.page_count
        or receipt.image_width != request.image_width
        or receipt.image_height != request.image_height
        or receipt.image_pixel_count != request.image_pixel_count
    ):
        raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")

    if receipt.outcome == "conflict":
        raise SafeUploadFinalizationError("upload_finalization_conflict")
    if receipt.outcome == "reserved" and receipt.finalized_at_epoch_s != request.requested_at_epoch_s:
        raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
    if not request.session_created_at_epoch_s <= receipt.finalized_at_epoch_s < request.session_expires_at_epoch_s:
        raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")
    if receipt.finalized_at_epoch_s > request.requested_at_epoch_s:
        raise SafeUploadFinalizationError("upload_finalization_receipt_invalid")

    replayed = receipt.outcome == "replay"
    return SafeUploadFinalizationDecision(
        version=request.version,
        session_id=request.session_id,
        admission_binding_id=request.admission_binding_id,
        principal_id=request.principal_id,
        environment=request.environment,
        operation_id=request.operation_id,
        state="replay" if replayed else "reserved",
        replayed=replayed,
        finalization_id=request.finalization_id,
        document_sha256=request.document_sha256,
        observed_bytes=request.observed_bytes,
        format_id=request.format_id,
        media_type=request.media_type,
        page_count=request.page_count,
        image_width=request.image_width,
        image_height=request.image_height,
        image_pixel_count=request.image_pixel_count,
        finalized_at_epoch_s=receipt.finalized_at_epoch_s,
        _construction_seal=_DECISION_CONSTRUCTION_SEAL,
    )
