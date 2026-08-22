from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import re
from typing import Any, Callable, Mapping

from .contracts import (
    ReviewAuthorizationGrant,
    ScoreEditCommand,
    Stage8ContractError,
    TeacherScoreRevision,
    build_teacher_score_revision,
    validate_score_edit_command,
    verify_authorization_grant,
)
from .durable_revision_store import (
    DurableRevisionHead,
    DurableRevisionStore,
    DurableRevisionStoreError,
    RevisionScope,
)
from .musical_state import (
    ReviewMusicalState,
    RevisionValidationReport,
    Stage8MaterializationError,
    apply_score_edit_command,
    materialize_canonical_state,
)


WRITE_REQUEST_VERSION = "scoremosaic-teacher-review-write-request-v1"
WRITE_IDEMPOTENCY_VERSION = "scoremosaic-teacher-review-write-idempotency-v1"
WRITE_RESULT_VERSION = "scoremosaic-teacher-review-write-result-v1"

_MAX_REQUEST_BYTES = 64 * 1024
_MAX_REQUEST_NODES = 256
_MAX_REQUEST_DEPTH = 8
_MAX_REQUEST_STRING = 4_000
_REQUEST_KEYS = frozenset({"schemaVersion", "command", "requestSha256"})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class Stage8WriteBoundaryError(ValueError):
    """Stable fail-closed category for the Stage 8-G server write boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8WriteBoundaryError(code)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("WRITE_REQUEST_INVALID")


def _bounded_walk(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > _MAX_REQUEST_NODES or depth > _MAX_REQUEST_DEPTH:
        _fail("WRITE_REQUEST_TOO_COMPLEX")
    if isinstance(value, Mapping):
        if len(value) > 32:
            _fail("WRITE_REQUEST_TOO_COMPLEX")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 200:
                _fail("WRITE_REQUEST_INVALID")
            _bounded_walk(item, depth=depth + 1, counter=counter)
    elif isinstance(value, (list, tuple)):
        if len(value) > 32:
            _fail("WRITE_REQUEST_TOO_COMPLEX")
        for item in value:
            _bounded_walk(item, depth=depth + 1, counter=counter)
    elif isinstance(value, str):
        if len(value) > _MAX_REQUEST_STRING:
            _fail("WRITE_REQUEST_TOO_COMPLEX")
    elif value is not None and not isinstance(value, (bool, int)):
        _fail("WRITE_REQUEST_INVALID")


def _request_body(payload: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    if not isinstance(payload, Mapping):
        _fail("WRITE_REQUEST_INVALID")
    _bounded_walk(payload)
    if set(payload) != set(_REQUEST_KEYS):
        _fail("WRITE_REQUEST_SCHEMA_CLOSED")
    if payload.get("schemaVersion") != WRITE_REQUEST_VERSION:
        _fail("WRITE_REQUEST_VERSION_INVALID")
    claimed = payload.get("requestSha256")
    if not isinstance(claimed, str) or _HASH_RE.fullmatch(claimed) is None:
        _fail("WRITE_REQUEST_HASH_INVALID")
    body = {
        "schemaVersion": WRITE_REQUEST_VERSION,
        "command": payload.get("command"),
    }
    encoded = _canonical_json(body)
    if len(encoded) > _MAX_REQUEST_BYTES:
        _fail("WRITE_REQUEST_TOO_LARGE")
    computed = sha256(encoded).hexdigest()
    if not hmac.compare_digest(claimed, computed):
        _fail("WRITE_REQUEST_HASH_MISMATCH")
    try:
        normalized = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        _fail("WRITE_REQUEST_INVALID")
    return normalized, encoded


def build_write_request(command: ScoreEditCommand) -> dict[str, Any]:
    if not isinstance(command, ScoreEditCommand):
        _fail("WRITE_COMMAND_INVALID")
    body = {
        "schemaVersion": WRITE_REQUEST_VERSION,
        "command": command.to_dict(),
    }
    encoded = _canonical_json(body)
    if len(encoded) > _MAX_REQUEST_BYTES:
        _fail("WRITE_REQUEST_TOO_LARGE")
    return {**body, "requestSha256": sha256(encoded).hexdigest()}


def _slot_id(
    *,
    scope: RevisionScope,
    reviewer_id: str,
    command: ScoreEditCommand,
) -> str:
    body = {
        "schemaVersion": WRITE_IDEMPOTENCY_VERSION,
        "tenantId": scope.tenant_id,
        "jobId": scope.job_id,
        "reviewerId": reviewer_id,
        "reviewReportId": scope.review_report_id,
        "reviewReportSha256": scope.review_report_sha256,
        "baseCanonicalSha256": scope.base_canonical_sha256,
        "parentRevisionId": command.base_revision_id,
        "parentRevisionSha256": command.base_revision_sha256,
        "commandId": command.command_id,
    }
    return sha256(_canonical_json(body)).hexdigest()


@dataclass(frozen=True, slots=True)
class WriteIdempotencyReservationRequest:
    version: str
    slot_id: str
    request_sha256: str
    command_id: str
    command_sha256: str
    parent_revision_id: str | None
    parent_revision_sha256: str | None

    def __post_init__(self) -> None:
        if self.version != WRITE_IDEMPOTENCY_VERSION:
            _fail("WRITE_IDEMPOTENCY_REQUEST_INVALID")
        for value in (self.slot_id, self.request_sha256, self.command_sha256):
            if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
                _fail("WRITE_IDEMPOTENCY_REQUEST_INVALID")
        if not isinstance(self.command_id, str) or not self.command_id:
            _fail("WRITE_IDEMPOTENCY_REQUEST_INVALID")
        if (self.parent_revision_id is None) != (self.parent_revision_sha256 is None):
            _fail("WRITE_IDEMPOTENCY_REQUEST_INVALID")
        if self.parent_revision_sha256 is not None and _HASH_RE.fullmatch(self.parent_revision_sha256) is None:
            _fail("WRITE_IDEMPOTENCY_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class WriteIdempotencyReservationReceipt:
    slot_id: str
    request_sha256: str
    command_sha256: str
    outcome: str
    created_at: str | None

    def __post_init__(self) -> None:
        for value in (self.slot_id, self.request_sha256, self.command_sha256):
            if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
                _fail("WRITE_IDEMPOTENCY_RECEIPT_INVALID")
        if self.outcome not in {"reserved", "replay", "conflict"}:
            _fail("WRITE_IDEMPOTENCY_RECEIPT_INVALID")
        if self.outcome == "conflict":
            if self.created_at is not None:
                _fail("WRITE_IDEMPOTENCY_RECEIPT_INVALID")
        elif not isinstance(self.created_at, str) or _TIMESTAMP_RE.fullmatch(self.created_at) is None:
            _fail("WRITE_IDEMPOTENCY_RECEIPT_INVALID")


WriteIdempotencyReserver = Callable[
    [WriteIdempotencyReservationRequest],
    WriteIdempotencyReservationReceipt,
]


@dataclass(frozen=True, slots=True)
class Stage8ServerWriteResult:
    request_sha256: str
    command_id: str
    command_sha256: str
    revision: TeacherScoreRevision
    state: ReviewMusicalState
    validation: RevisionValidationReport
    append_applied: bool
    idempotent_replay: bool
    idempotency_state: str

    def to_safe_dict(self) -> dict[str, Any]:
        revision = self.revision.to_dict()
        return {
            "schemaVersion": WRITE_RESULT_VERSION,
            "requestSha256": self.request_sha256,
            "commandId": self.command_id,
            "commandSha256": self.command_sha256,
            "revisionId": revision["revisionId"],
            "revisionSha256": revision["revisionSha256"],
            "stateSha256": self.state.state_sha256,
            "validationReport": self.validation.to_dict(),
            "appendApplied": self.append_applied,
            "idempotentReplay": self.idempotent_replay,
            "idempotencyState": self.idempotency_state,
            "status": "draft",
            "immutable": True,
            "approvalEligible": False,
            "publicationEligible": False,
            "publicApiEnabled": False,
            "browserWriteEnabled": False,
        }


def _load_head(store: DurableRevisionStore, scope: RevisionScope) -> DurableRevisionHead | None:
    try:
        return store.load_head(scope)
    except DurableRevisionStoreError as exc:
        raise Stage8WriteBoundaryError("WRITE_STORE_INVALID") from exc


def _verify_authorization_first(
    *,
    grant: ReviewAuthorizationGrant,
    signing_key: bytes,
    scope: RevisionScope,
    reviewer_id: str,
    head: DurableRevisionHead | None,
) -> dict[str, Any]:
    parent_id = head.revision_id if head is not None else None
    parent_sha = head.revision_sha256 if head is not None else None
    try:
        return verify_authorization_grant(
            grant,
            signing_key=signing_key,
            required_action="revision:propose",
            expected_tenant_id=scope.tenant_id,
            expected_job_id=scope.job_id,
            expected_reviewer_id=reviewer_id,
            expected_review_report_id=scope.review_report_id,
            expected_review_report_sha256=scope.review_report_sha256,
            expected_canonical_score_sha256=scope.base_canonical_sha256,
            expected_parent_revision_id=parent_id,
            expected_parent_revision_sha256=parent_sha,
        )
    except Stage8ContractError as exc:
        code = "WRITE_STALE_PARENT" if exc.code == "AUTHZ_STALE_PARENT" else "WRITE_AUTHORIZATION_DENIED"
        raise Stage8WriteBoundaryError(code) from exc


def _validate_command_scope(
    command: ScoreEditCommand,
    *,
    scope: RevisionScope,
    reviewer_id: str,
    authorization: Mapping[str, Any],
    head: DurableRevisionHead | None,
) -> None:
    parent_id = head.revision_id if head is not None else None
    parent_sha = head.revision_sha256 if head is not None else None
    checks = (
        (command.job_id, scope.job_id),
        (command.reviewer_id, reviewer_id),
        (command.review_report_id, scope.review_report_id),
        (command.review_report_sha256, scope.review_report_sha256),
        (command.base_canonical_sha256, scope.base_canonical_sha256),
        (command.base_revision_id, parent_id),
        (command.base_revision_sha256, parent_sha),
        (command.authorization_decision_id, authorization.get("decisionId")),
    )
    if any(actual != expected for actual, expected in checks):
        _fail("WRITE_SCOPE_MISMATCH")


def _validate_current_state(
    *,
    scope: RevisionScope,
    store: DurableRevisionStore,
    head: DurableRevisionHead | None,
    current_state: ReviewMusicalState,
    base_canonical_payload: Mapping[str, Any] | None,
) -> None:
    if not isinstance(current_state, ReviewMusicalState):
        _fail("WRITE_CURRENT_STATE_INVALID")
    state_payload = current_state.to_dict()
    if state_payload.get("baseCanonicalSha256") != scope.base_canonical_sha256:
        _fail("WRITE_CURRENT_STATE_MISMATCH")

    if head is None:
        if base_canonical_payload is None:
            _fail("WRITE_BASE_CANONICAL_REQUIRED")
        try:
            base_state = materialize_canonical_state(scope, base_canonical_payload)
        except Stage8MaterializationError as exc:
            raise Stage8WriteBoundaryError("WRITE_BASE_CANONICAL_INVALID") from exc
        if not hmac.compare_digest(base_state.state_sha256, current_state.state_sha256):
            _fail("WRITE_CURRENT_STATE_MISMATCH")
        return

    try:
        record = store.load_revision(scope, head.revision_sha256)
    except DurableRevisionStoreError as exc:
        raise Stage8WriteBoundaryError("WRITE_STORE_INVALID") from exc
    if (
        record.get("revisionId") != head.revision_id
        or record.get("revisionSha256") != head.revision_sha256
        or record.get("resultingMusicalStateSha256") != current_state.state_sha256
    ):
        _fail("WRITE_CURRENT_STATE_MISMATCH")


def _reserve_idempotency(
    *,
    scope: RevisionScope,
    reviewer_id: str,
    command: ScoreEditCommand,
    request_sha256: str,
    reserver: WriteIdempotencyReserver,
) -> WriteIdempotencyReservationReceipt:
    if not callable(reserver):
        _fail("WRITE_IDEMPOTENCY_UNAVAILABLE")
    request = WriteIdempotencyReservationRequest(
        version=WRITE_IDEMPOTENCY_VERSION,
        slot_id=_slot_id(scope=scope, reviewer_id=reviewer_id, command=command),
        request_sha256=request_sha256,
        command_id=command.command_id,
        command_sha256=command.command_sha256,
        parent_revision_id=command.base_revision_id,
        parent_revision_sha256=command.base_revision_sha256,
    )
    try:
        receipt = reserver(request)
    except Exception as exc:
        raise Stage8WriteBoundaryError("WRITE_IDEMPOTENCY_UNAVAILABLE") from exc
    if not isinstance(receipt, WriteIdempotencyReservationReceipt):
        _fail("WRITE_IDEMPOTENCY_RECEIPT_INVALID")
    receipt.__post_init__()
    if (
        receipt.slot_id != request.slot_id
        or receipt.request_sha256 != request.request_sha256
        or receipt.command_sha256 != request.command_sha256
    ):
        _fail("WRITE_IDEMPOTENCY_RECEIPT_INVALID")
    if receipt.outcome == "conflict":
        _fail("WRITE_IDEMPOTENCY_CONFLICT")
    return receipt


def submit_score_edit_request(
    *,
    request_payload: Mapping[str, Any],
    grant: ReviewAuthorizationGrant,
    signing_key: bytes,
    scope: RevisionScope,
    reviewer_id: str,
    current_state: ReviewMusicalState,
    base_canonical_payload: Mapping[str, Any] | None,
    store: DurableRevisionStore,
    idempotency_reserver: WriteIdempotencyReserver,
) -> Stage8ServerWriteResult:
    """Process one authorized typed edit without exposing an HTTP or browser-write route.

    Authorization is verified against trusted server scope and the fresh durable
    head before any caller request body is parsed or any idempotency provider is
    invoked. The edit is then applied in memory, reserved idempotently, converted
    to one immutable draft revision, and appended under the exact-parent CAS in
    the Stage 8-B durable store.
    """

    if not isinstance(scope, RevisionScope) or not isinstance(store, DurableRevisionStore):
        _fail("WRITE_SERVER_CONFIGURATION_INVALID")

    head = _load_head(store, scope)
    authorization = _verify_authorization_first(
        grant=grant,
        signing_key=signing_key,
        scope=scope,
        reviewer_id=reviewer_id,
        head=head,
    )

    normalized_request, _ = _request_body(request_payload)
    try:
        command = validate_score_edit_command(normalized_request["command"])
    except Stage8ContractError as exc:
        raise Stage8WriteBoundaryError("WRITE_COMMAND_INVALID") from exc
    _validate_command_scope(
        command,
        scope=scope,
        reviewer_id=reviewer_id,
        authorization=authorization,
        head=head,
    )
    _validate_current_state(
        scope=scope,
        store=store,
        head=head,
        current_state=current_state,
        base_canonical_payload=base_canonical_payload,
    )

    try:
        applied = apply_score_edit_command(current_state, command)
    except Stage8MaterializationError as exc:
        code = (
            "WRITE_STALE_TARGET"
            if exc.code in {
                "EDIT_TARGET_LOCATION_STALE",
                "EDIT_TARGET_EVENT_NOT_FOUND",
                "EDIT_TARGET_MEASURE_NOT_FOUND",
                "EDIT_TARGET_PART_NOT_FOUND",
                "EDIT_OLD_VALUE_PRECONDITION_FAILED",
            }
            else "WRITE_EDIT_REJECTED"
        )
        raise Stage8WriteBoundaryError(code) from exc

    receipt = _reserve_idempotency(
        scope=scope,
        reviewer_id=reviewer_id,
        command=command,
        request_sha256=request_payload["requestSha256"],
        reserver=idempotency_reserver,
    )
    assert receipt.created_at is not None

    parent_id = head.revision_id if head is not None else None
    parent_sha = head.revision_sha256 if head is not None else None
    previous_audit = head.audit_event_sha256 if head is not None else None
    try:
        revision = build_teacher_score_revision(
            grant=grant,
            signing_key=signing_key,
            expected_tenant_id=scope.tenant_id,
            expected_job_id=scope.job_id,
            expected_reviewer_id=reviewer_id,
            expected_review_report_id=scope.review_report_id,
            expected_review_report_sha256=scope.review_report_sha256,
            expected_canonical_score_sha256=scope.base_canonical_sha256,
            command=command,
            current_parent_revision_id=parent_id,
            current_parent_revision_sha256=parent_sha,
            resulting_musical_state_sha256=applied.state.state_sha256,
            validation_report_sha256=applied.validation.report_sha256,
            blocking_issue_count=applied.validation.blocking_issue_count,
            unresolved_issue_count=applied.validation.unresolved_issue_count,
            created_at=receipt.created_at,
            previous_audit_event_sha256=previous_audit,
        )
    except Stage8ContractError as exc:
        code = "WRITE_STALE_PARENT" if exc.code in {"AUTHZ_STALE_PARENT", "COMMAND_STALE_PARENT"} else "WRITE_AUTHORIZATION_DENIED"
        raise Stage8WriteBoundaryError(code) from exc

    try:
        appended = store.append_revision(
            scope,
            revision,
            expected_parent_revision_id=parent_id,
            expected_parent_revision_sha256=parent_sha,
        )
    except DurableRevisionStoreError as exc:
        code = (
            "WRITE_STALE_PARENT"
            if exc.category in {"revision_store_stale_parent", "revision_store_append_conflict"}
            else "WRITE_STORE_INVALID"
        )
        raise Stage8WriteBoundaryError(code) from exc

    revision_record = revision.to_dict()
    if (
        appended.head.revision_id != revision_record["revisionId"]
        or appended.head.revision_sha256 != revision_record["revisionSha256"]
    ):
        _fail("WRITE_STORE_RESULT_MISMATCH")

    return Stage8ServerWriteResult(
        request_sha256=request_payload["requestSha256"],
        command_id=command.command_id,
        command_sha256=command.command_sha256,
        revision=revision,
        state=applied.state,
        validation=applied.validation,
        append_applied=appended.applied,
        idempotent_replay=appended.idempotent_replay,
        idempotency_state=receipt.outcome,
    )


__all__ = [
    "WRITE_IDEMPOTENCY_VERSION",
    "WRITE_REQUEST_VERSION",
    "WRITE_RESULT_VERSION",
    "Stage8ServerWriteResult",
    "Stage8WriteBoundaryError",
    "WriteIdempotencyReservationReceipt",
    "WriteIdempotencyReservationRequest",
    "WriteIdempotencyReserver",
    "build_write_request",
    "submit_score_edit_request",
]
