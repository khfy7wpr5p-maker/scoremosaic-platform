from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import re
import threading
from typing import Any, Callable, Mapping

from .contracts import (
    COMMAND_VERSION,
    ReviewAuthorizationGrant,
    Stage8ContractError,
    build_score_edit_command,
    issue_authorization_grant,
)
from .durable_revision_store import (
    DurableRevisionStore,
    DurableRevisionStoreError,
    RevisionScope,
)
from .musical_state import (
    ReviewMusicalState,
    Stage8MaterializationError,
    expected_old_value_sha256,
    materialize_canonical_state,
)
from .write_boundary import (
    Stage8ServerWriteResult,
    Stage8WriteBoundaryError,
    WriteIdempotencyReservationReceipt,
    WriteIdempotencyReservationRequest,
    WriteIdempotencyReserver,
    build_write_request,
    submit_score_edit_request,
)


API_HARNESS_VERSION = "scoremosaic-teacher-review-api-harness-v1"
API_EDIT_INTENT_VERSION = "scoremosaic-teacher-review-api-edit-intent-v1"
API_REVISION_RESULT_VERSION = "scoremosaic-teacher-review-api-revision-result-v1"

_MAX_BODY_BYTES = 32 * 1024
_MAX_BODY_NODES = 256
_MAX_BODY_DEPTH = 10
_MAX_STRING = 2_000
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_REQUEST_ID_RE = re.compile(r"^req_[A-Za-z0-9_-]{8,120}$")
_CORRELATION_ID_RE = re.compile(r"^corr_[A-Za-z0-9_-]{8,120}$")
_REVISION_ID_RE = re.compile(r"^rev_[0-9a-f]{32}$")
_ISSUE_ID_RE = re.compile(r"^issue_[A-Za-z0-9_-]{6,80}$")
_DIFFERENCE_ID_RE = re.compile(r"^difference_[0-9a-f]{24}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._~-]{16,128}$")
_PUBLIC_OPERATIONS = frozenset({
    "set_pitch",
    "set_effective_duration",
    "set_dots",
    "remove_event",
})
_INTENT_KEYS = frozenset({
    "schemaVersion",
    "requestId",
    "projectionSha256",
    "snapshot",
    "evidenceContext",
    "target",
    "operation",
    "reason",
})
_AUTHORITY = {
    "canCreateAnotherRevision": False,
    "canApprove": False,
    "canPublish": False,
    "canPersistCorrectedMusicXmlToProduction": False,
}


class ApiHarnessError(ValueError):
    """Internal stable category for the disconnected API/security harness."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise ApiHarnessError(code)


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
        _fail("API_REQUEST_INVALID")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _bounded_walk(
    value: Any,
    *,
    depth: int = 0,
    counter: list[int] | None = None,
) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > _MAX_BODY_NODES or depth > _MAX_BODY_DEPTH:
        _fail("API_REQUEST_TOO_COMPLEX")
    if type(value) is dict:
        if len(value) > 32:
            _fail("API_REQUEST_TOO_COMPLEX")
        for key, item in value.items():
            if type(key) is not str or not key or len(key) > 200:
                _fail("API_REQUEST_INVALID")
            _bounded_walk(item, depth=depth + 1, counter=counter)
        return
    if type(value) is list:
        if len(value) > 32:
            _fail("API_REQUEST_TOO_COMPLEX")
        for item in value:
            _bounded_walk(item, depth=depth + 1, counter=counter)
        return
    if type(value) is str:
        if len(value) > _MAX_STRING:
            _fail("API_REQUEST_TOO_COMPLEX")
        return
    if value is None or type(value) in {bool, int}:
        return
    _fail("API_REQUEST_INVALID")


def _require_hash(value: Any, code: str = "API_REQUEST_INVALID") -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _require_id(value: Any, code: str = "API_REQUEST_INVALID") -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _require_rational(value: Any) -> dict[str, int]:
    if type(value) is not dict or set(value) != {"numerator", "denominator"}:
        _fail("API_REQUEST_INVALID")
    numerator = value["numerator"]
    denominator = value["denominator"]
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        _fail("API_REQUEST_INVALID")
    if abs(numerator) > 10**12 or denominator > 1_000_000:
        _fail("API_REQUEST_INVALID")
    return {"numerator": numerator, "denominator": denominator}


def _validate_operation(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"type", "value"}:
        _fail("API_REQUEST_INVALID")
    operation_type = value["type"]
    if type(operation_type) is not str or operation_type not in _PUBLIC_OPERATIONS:
        _fail("API_OPERATION_NOT_SUPPORTED")
    raw = value["value"]
    if operation_type == "set_pitch":
        if type(raw) is not dict or set(raw) != {"step", "alter", "octave"}:
            _fail("API_REQUEST_INVALID")
        step = raw["step"]
        octave = raw["octave"]
        if step not in {"A", "B", "C", "D", "E", "F", "G"}:
            _fail("API_REQUEST_INVALID")
        if type(octave) is not int or not -2 <= octave <= 12:
            _fail("API_REQUEST_INVALID")
        normalized: Any = {
            "step": step,
            "alter": _require_rational(raw["alter"]),
            "octave": octave,
        }
    elif operation_type == "set_effective_duration":
        normalized = _require_rational(raw)
        if normalized["numerator"] < 0:
            _fail("API_REQUEST_INVALID")
    elif operation_type == "set_dots":
        if type(raw) is not int or not 0 <= raw <= 8:
            _fail("API_REQUEST_INVALID")
        normalized = raw
    else:
        if raw is not None:
            _fail("API_REQUEST_INVALID")
        normalized = None
    return {"type": operation_type, "value": normalized}


def _parse_intent(raw_body: bytes) -> dict[str, Any]:
    if type(raw_body) is not bytes or not raw_body or len(raw_body) > _MAX_BODY_BYTES:
        _fail("API_REQUEST_TOO_LARGE")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeError, ValueError):
        _fail("API_REQUEST_INVALID")
    if type(payload) is not dict:
        _fail("API_REQUEST_INVALID")
    _bounded_walk(payload)
    if set(payload) != set(_INTENT_KEYS):
        _fail("API_REQUEST_SCHEMA_CLOSED")
    if payload.get("schemaVersion") != API_EDIT_INTENT_VERSION:
        _fail("API_REQUEST_VERSION_INVALID")

    request_id = payload.get("requestId")
    if type(request_id) is not str or _REQUEST_ID_RE.fullmatch(request_id) is None:
        _fail("API_REQUEST_INVALID")
    projection_sha = _require_hash(payload.get("projectionSha256"))

    snapshot = payload.get("snapshot")
    if type(snapshot) is not dict or set(snapshot) != {
        "kind", "revisionId", "revisionSha256", "stateSha256"
    }:
        _fail("API_REQUEST_INVALID")
    kind = snapshot.get("kind")
    if kind not in {"base", "revision"}:
        _fail("API_REQUEST_INVALID")
    state_sha = _require_hash(snapshot.get("stateSha256"))
    revision_id = snapshot.get("revisionId")
    revision_sha = snapshot.get("revisionSha256")
    if kind == "base":
        if revision_id is not None or revision_sha is not None:
            _fail("API_REQUEST_INVALID")
    else:
        if type(revision_id) is not str or _REVISION_ID_RE.fullmatch(revision_id) is None:
            _fail("API_REQUEST_INVALID")
        revision_sha = _require_hash(revision_sha)
    normalized_snapshot = {
        "kind": kind,
        "revisionId": revision_id,
        "revisionSha256": revision_sha,
        "stateSha256": state_sha,
    }

    evidence = payload.get("evidenceContext")
    if type(evidence) is not dict or set(evidence) != {"issueId", "differenceId"}:
        _fail("API_REQUEST_INVALID")
    issue_id = evidence.get("issueId")
    difference_id = evidence.get("differenceId")
    if issue_id is not None and (
        type(issue_id) is not str or _ISSUE_ID_RE.fullmatch(issue_id) is None
    ):
        _fail("API_REQUEST_INVALID")
    if difference_id is not None and (
        type(difference_id) is not str
        or _DIFFERENCE_ID_RE.fullmatch(difference_id) is None
    ):
        _fail("API_REQUEST_INVALID")

    target = payload.get("target")
    if type(target) is not dict or set(target) != {"partId", "measureId", "eventId"}:
        _fail("API_REQUEST_INVALID")
    normalized_target = {
        "partId": _require_id(target.get("partId")),
        "measureId": _require_id(target.get("measureId")),
        "eventId": _require_id(target.get("eventId")),
    }

    reason = payload.get("reason")
    if reason is not None and (
        type(reason) is not str or not reason or len(reason) > 500
    ):
        _fail("API_REQUEST_INVALID")

    return {
        "schemaVersion": API_EDIT_INTENT_VERSION,
        "requestId": request_id,
        "projectionSha256": projection_sha,
        "snapshot": normalized_snapshot,
        "evidenceContext": {"issueId": issue_id, "differenceId": difference_id},
        "target": normalized_target,
        "operation": _validate_operation(payload.get("operation")),
        "reason": reason,
    }


@dataclass(frozen=True, slots=True)
class ApiPrincipal:
    principal_id: str
    reviewer_id: str
    tenant_id: str

    def __post_init__(self) -> None:
        _require_id(self.principal_id, "API_PRINCIPAL_INVALID")
        _require_id(self.reviewer_id, "API_PRINCIPAL_INVALID")
        _require_id(self.tenant_id, "API_PRINCIPAL_INVALID")


@dataclass(frozen=True, slots=True)
class ApiDocumentContext:
    document_id: str
    scope: RevisionScope
    projection_sha256: str
    current_state: ReviewMusicalState
    base_canonical_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_id(self.document_id, "API_DOCUMENT_CONTEXT_INVALID")
        if not isinstance(self.scope, RevisionScope):
            _fail("API_DOCUMENT_CONTEXT_INVALID")
        _require_hash(self.projection_sha256, "API_DOCUMENT_CONTEXT_INVALID")
        if not isinstance(self.current_state, ReviewMusicalState):
            _fail("API_DOCUMENT_CONTEXT_INVALID")
        if not isinstance(self.base_canonical_payload, Mapping):
            _fail("API_DOCUMENT_CONTEXT_INVALID")


@dataclass(frozen=True, slots=True)
class ApiHarnessRequest:
    document_id: str
    raw_body: bytes
    content_type: str | None
    origin: str | None
    session_token: str | None
    csrf_token: str | None
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class ApiHarnessResponse:
    http_status: int
    body: Mapping[str, Any]

    def __post_init__(self) -> None:
        if type(self.http_status) is not int or not 100 <= self.http_status <= 599:
            _fail("API_RESPONSE_INVALID")
        if not isinstance(self.body, Mapping):
            _fail("API_RESPONSE_INVALID")


SessionAuthenticator = Callable[[str | None], ApiPrincipal | None]
CsrfValidator = Callable[[ApiPrincipal, str | None, str | None], bool]
CoarseAuthorizer = Callable[[ApiPrincipal, str, str], str]
OperationAuthorizer = Callable[[ApiPrincipal, str, str], bool]
DocumentResolver = Callable[[ApiPrincipal, str], ApiDocumentContext | None]
AuditSink = Callable[[Mapping[str, Any]], None]
IdentityFactory = Callable[[], str]
WriteInvoker = Callable[..., Stage8ServerWriteResult]


@dataclass(slots=True)
class ApiHarnessDependencies:
    store: DurableRevisionStore
    signing_key: bytes
    allowed_origin: str
    session_authenticator: SessionAuthenticator
    csrf_validator: CsrfValidator
    coarse_authorizer: CoarseAuthorizer
    operation_authorizer: OperationAuthorizer
    document_resolver: DocumentResolver
    stage8_idempotency_reserver: WriteIdempotencyReserver
    outer_idempotency: "MemoryApiIdempotencyLedger"
    audit_sink: AuditSink
    correlation_id_factory: IdentityFactory
    command_id_factory: IdentityFactory
    decision_id_factory: IdentityFactory
    write_invoker: WriteInvoker = submit_score_edit_request

    def __post_init__(self) -> None:
        if not isinstance(self.store, DurableRevisionStore):
            _fail("API_SERVER_CONFIGURATION_INVALID")
        if type(self.signing_key) is not bytes or len(self.signing_key) < 32:
            _fail("API_SERVER_CONFIGURATION_INVALID")
        if type(self.allowed_origin) is not str or not self.allowed_origin:
            _fail("API_SERVER_CONFIGURATION_INVALID")
        for callback in (
            self.session_authenticator,
            self.csrf_validator,
            self.coarse_authorizer,
            self.operation_authorizer,
            self.document_resolver,
            self.stage8_idempotency_reserver,
            self.audit_sink,
            self.correlation_id_factory,
            self.command_id_factory,
            self.decision_id_factory,
            self.write_invoker,
        ):
            if not callable(callback):
                _fail("API_SERVER_CONFIGURATION_INVALID")
        if not isinstance(self.outer_idempotency, MemoryApiIdempotencyLedger):
            _fail("API_SERVER_CONFIGURATION_INVALID")


@dataclass(frozen=True, slots=True)
class _ApiLedgerReceipt:
    outcome: str
    slot_id: str
    response: ApiHarnessResponse | None


class MemoryApiIdempotencyLedger:
    """Deterministic non-production reconciliation ledger.

    The raw Idempotency-Key is hashed into the slot identity and is never returned
    by this class. A pending slot deliberately blocks automatic mutation replay
    after an ambiguous outcome until an authorized reconciliation path exists.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _slot_id(*, principal: ApiPrincipal, document_id: str, raw_key: str) -> str:
        return _digest({
            "purpose": "scoremosaic/api-idempotency-slot/v1",
            "principalId": principal.principal_id,
            "tenantId": principal.tenant_id,
            "documentId": document_id,
            "keySha256": sha256(raw_key.encode("utf-8")).hexdigest(),
        })

    @staticmethod
    def _binding_sha(*, intent: Mapping[str, Any], request_digest: str) -> str:
        snapshot = intent["snapshot"]
        return _digest({
            "purpose": "scoremosaic/api-idempotency-binding/v1",
            "operation": intent["operation"]["type"],
            "parentRevisionId": snapshot["revisionId"],
            "parentRevisionSha256": snapshot["revisionSha256"],
            "requestDigest": request_digest,
        })

    def inspect(
        self,
        *,
        principal: ApiPrincipal,
        document_id: str,
        raw_key: str,
        intent: Mapping[str, Any],
        request_digest: str,
    ) -> _ApiLedgerReceipt:
        slot = self._slot_id(principal=principal, document_id=document_id, raw_key=raw_key)
        binding = self._binding_sha(intent=intent, request_digest=request_digest)
        with self._lock:
            current = self._slots.get(slot)
            if current is None:
                return _ApiLedgerReceipt("none", slot, None)
            if not hmac.compare_digest(current["bindingSha256"], binding):
                return _ApiLedgerReceipt("conflict", slot, None)
            if current["state"] == "committed":
                return _ApiLedgerReceipt("replay", slot, current["response"])
            return _ApiLedgerReceipt("pending", slot, None)

    def begin(
        self,
        *,
        principal: ApiPrincipal,
        document_id: str,
        raw_key: str,
        intent: Mapping[str, Any],
        request_digest: str,
    ) -> _ApiLedgerReceipt:
        slot = self._slot_id(principal=principal, document_id=document_id, raw_key=raw_key)
        binding = self._binding_sha(intent=intent, request_digest=request_digest)
        with self._lock:
            current = self._slots.get(slot)
            if current is None:
                self._slots[slot] = {
                    "bindingSha256": binding,
                    "state": "pending",
                    "response": None,
                }
                return _ApiLedgerReceipt("reserved", slot, None)
            if not hmac.compare_digest(current["bindingSha256"], binding):
                return _ApiLedgerReceipt("conflict", slot, None)
            if current["state"] == "committed":
                return _ApiLedgerReceipt("replay", slot, current["response"])
            return _ApiLedgerReceipt("pending", slot, None)

    def commit(self, *, slot_id: str, response: ApiHarnessResponse) -> None:
        with self._lock:
            current = self._slots.get(slot_id)
            if current is None or current["state"] != "pending":
                _fail("API_IDEMPOTENCY_LEDGER_INVALID")
            current["state"] = "committed"
            current["response"] = response

    def abort(self, *, slot_id: str) -> None:
        with self._lock:
            current = self._slots.get(slot_id)
            if current is not None and current["state"] == "pending":
                del self._slots[slot_id]


class MemoryStage8IdempotencyReserver:
    """Thread-safe provider-neutral reserver for disconnected tests only."""

    def __init__(self, *, created_at: str = "2026-01-01T00:00:00Z") -> None:
        self._created_at = created_at
        self._lock = threading.Lock()
        self._slots: dict[str, tuple[str, str, str]] = {}
        self.calls = 0

    def __call__(
        self, request: WriteIdempotencyReservationRequest
    ) -> WriteIdempotencyReservationReceipt:
        with self._lock:
            self.calls += 1
            current = self._slots.get(request.slot_id)
            if current is None:
                self._slots[request.slot_id] = (
                    request.request_sha256,
                    request.command_sha256,
                    self._created_at,
                )
                return WriteIdempotencyReservationReceipt(
                    request.slot_id,
                    request.request_sha256,
                    request.command_sha256,
                    "reserved",
                    self._created_at,
                )
            request_sha, command_sha, created_at = current
            if (
                not hmac.compare_digest(request_sha, request.request_sha256)
                or not hmac.compare_digest(command_sha, request.command_sha256)
            ):
                return WriteIdempotencyReservationReceipt(
                    request.slot_id,
                    request.request_sha256,
                    request.command_sha256,
                    "conflict",
                    None,
                )
            return WriteIdempotencyReservationReceipt(
                request.slot_id,
                request.request_sha256,
                request.command_sha256,
                "replay",
                created_at,
            )


def _correlation_id(deps: ApiHarnessDependencies) -> str:
    value = deps.correlation_id_factory()
    if type(value) is not str or _CORRELATION_ID_RE.fullmatch(value) is None:
        _fail("API_SERVER_CONFIGURATION_INVALID")
    return value


def _error_body(
    *,
    correlation_id: str,
    state: str,
    code: str,
    message: str,
    retryable: bool,
    reconciliation_required: bool,
) -> dict[str, Any]:
    return {
        "schemaVersion": API_REVISION_RESULT_VERSION,
        "requestId": None,
        "correlationId": correlation_id,
        "state": state,
        "documentId": None,
        "parent": None,
        "revision": None,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "reconciliationRequired": reconciliation_required,
        },
        "authority": dict(_AUTHORITY),
    }


def _error_response(
    status: int,
    *,
    correlation_id: str,
    state: str,
    code: str,
    message: str,
    retryable: bool = False,
    reconciliation_required: bool = False,
) -> ApiHarnessResponse:
    return ApiHarnessResponse(
        status,
        _error_body(
            correlation_id=correlation_id,
            state=state,
            code=code,
            message=message,
            retryable=retryable,
            reconciliation_required=reconciliation_required,
        ),
    )


def _replayed_response(response: ApiHarnessResponse) -> ApiHarnessResponse:
    body = dict(response.body)
    body["state"] = "replayed"
    return ApiHarnessResponse(200, body)


def _resolve_target_location(
    state: ReviewMusicalState,
    target: Mapping[str, Any],
) -> dict[str, Any]:
    payload = state.to_dict()
    for part in payload.get("parts", []):
        if part.get("partId") != target["partId"]:
            continue
        for measure in part.get("measures", []):
            if measure.get("measureId") != target["measureId"]:
                continue
            for event in measure.get("events", []):
                if event.get("eventId") != target["eventId"]:
                    continue
                return {
                    "partId": target["partId"],
                    "measureId": target["measureId"],
                    "eventId": target["eventId"],
                    "staff": event["staff"],
                    "voice": event["voice"],
                    "onset": event["onset"],
                }
            _fail("API_STALE_TARGET")
        _fail("API_STALE_TARGET")
    _fail("API_STALE_TARGET")


def _verify_snapshot(
    *,
    intent: Mapping[str, Any],
    context: ApiDocumentContext,
    store: DurableRevisionStore,
) -> tuple[str | None, str | None]:
    if not hmac.compare_digest(intent["projectionSha256"], context.projection_sha256):
        _fail("API_STALE_SNAPSHOT")
    state_payload = context.current_state.to_dict()
    if state_payload.get("baseCanonicalSha256") != context.scope.base_canonical_sha256:
        _fail("API_SERVER_STATE_INVALID")
    try:
        head = store.load_head(context.scope)
    except DurableRevisionStoreError as exc:
        raise ApiHarnessError("API_SERVER_STATE_INVALID") from exc

    snapshot = intent["snapshot"]
    if head is None:
        if (
            snapshot["kind"] != "base"
            or snapshot["revisionId"] is not None
            or snapshot["revisionSha256"] is not None
            or not hmac.compare_digest(snapshot["stateSha256"], context.current_state.state_sha256)
        ):
            _fail("API_STALE_SNAPSHOT")
        try:
            base_state = materialize_canonical_state(
                context.scope, context.base_canonical_payload
            )
        except Stage8MaterializationError as exc:
            raise ApiHarnessError("API_SERVER_STATE_INVALID") from exc
        if not hmac.compare_digest(base_state.state_sha256, context.current_state.state_sha256):
            _fail("API_SERVER_STATE_INVALID")
        return None, None

    try:
        record = store.load_revision(context.scope, head.revision_sha256)
    except DurableRevisionStoreError as exc:
        raise ApiHarnessError("API_SERVER_STATE_INVALID") from exc
    if record.get("revisionId") != head.revision_id:
        _fail("API_SERVER_STATE_INVALID")
    if record.get("resultingMusicalStateSha256") != context.current_state.state_sha256:
        _fail("API_SERVER_STATE_INVALID")
    if (
        snapshot["kind"] != "revision"
        or snapshot["revisionId"] != head.revision_id
        or snapshot["revisionSha256"] != head.revision_sha256
        or not hmac.compare_digest(snapshot["stateSha256"], context.current_state.state_sha256)
    ):
        _fail("API_STALE_SNAPSHOT")
    return head.revision_id, head.revision_sha256


def _success_response(
    *,
    correlation_id: str,
    document_id: str,
    intent: Mapping[str, Any],
    result: Stage8ServerWriteResult,
) -> ApiHarnessResponse:
    revision = result.revision.to_dict()
    body = {
        "schemaVersion": API_REVISION_RESULT_VERSION,
        "requestId": intent["requestId"],
        "correlationId": correlation_id,
        "state": "replayed" if result.idempotent_replay else "created",
        "documentId": document_id,
        "parent": {
            "revisionId": intent["snapshot"]["revisionId"],
            "revisionSha256": intent["snapshot"]["revisionSha256"],
            "stateSha256": intent["snapshot"]["stateSha256"],
        },
        "revision": {
            "revisionId": revision["revisionId"],
            "revisionSha256": revision["revisionSha256"],
            "resultingMusicalStateSha256": result.state.state_sha256,
            "validationReportSha256": result.validation.report_sha256,
            "blockingIssueCount": result.validation.blocking_issue_count,
            "unresolvedIssueCount": result.validation.unresolved_issue_count,
            "status": "draft",
            "immutable": True,
            "approvalEligible": False,
            "publicationEligible": False,
        },
        "error": None,
        "authority": dict(_AUTHORITY),
    }
    return ApiHarnessResponse(200 if result.idempotent_replay else 201, body)


def _map_prewrite_error(code: str, correlation_id: str) -> ApiHarnessResponse:
    if code in {"API_STALE_SNAPSHOT", "API_STALE_TARGET"}:
        return _error_response(
            409,
            correlation_id=correlation_id,
            state="stale",
            code="API_STALE_SNAPSHOT",
            message="The requested review snapshot is stale. Perform an authorized read before retrying.",
        )
    if code == "API_OPERATION_NOT_SUPPORTED":
        return _error_response(
            422,
            correlation_id=correlation_id,
            state="rejected",
            code="API_OPERATION_NOT_SUPPORTED",
            message="The requested musical operation is not available in API v1.",
        )
    if code == "API_SERVER_STATE_INVALID":
        return _error_response(
            503,
            correlation_id=correlation_id,
            state="unavailable",
            code="API_TEMPORARILY_UNAVAILABLE",
            message="The review service is temporarily unavailable.",
            retryable=True,
        )
    return _error_response(
        400,
        correlation_id=correlation_id,
        state="rejected",
        code="API_REQUEST_INVALID",
        message="The request does not satisfy the bounded Teacher Review API contract.",
    )


def _map_stage8_error(
    code: str,
    correlation_id: str,
) -> tuple[ApiHarnessResponse, bool]:
    """Return (safe response, side_effect_ambiguous)."""

    if code in {"WRITE_STALE_PARENT", "WRITE_STALE_TARGET"}:
        return (
            _error_response(
                409,
                correlation_id=correlation_id,
                state="stale",
                code="API_STALE_SNAPSHOT",
                message="The requested review snapshot is stale. Perform an authorized read before retrying.",
            ),
            False,
        )
    if code == "WRITE_IDEMPOTENCY_CONFLICT":
        return (
            _error_response(
                409,
                correlation_id=correlation_id,
                state="conflict",
                code="API_IDEMPOTENCY_CONFLICT",
                message="The idempotency key conflicts with another request.",
            ),
            False,
        )
    if code == "WRITE_EDIT_REJECTED":
        return (
            _error_response(
                422,
                correlation_id=correlation_id,
                state="rejected",
                code="API_EDIT_REJECTED",
                message="The proposed musical edit was rejected by the deterministic edit boundary.",
            ),
            False,
        )
    if code == "WRITE_IDEMPOTENCY_UNAVAILABLE":
        return (
            _error_response(
                503,
                correlation_id=correlation_id,
                state="unavailable",
                code="API_TEMPORARILY_UNAVAILABLE",
                message="The review service is temporarily unavailable.",
                retryable=True,
            ),
            False,
        )
    if code in {
        "WRITE_AUTHORIZATION_DENIED",
        "WRITE_REQUEST_INVALID",
        "WRITE_REQUEST_TOO_COMPLEX",
        "WRITE_REQUEST_SCHEMA_CLOSED",
        "WRITE_REQUEST_VERSION_INVALID",
        "WRITE_REQUEST_HASH_INVALID",
        "WRITE_REQUEST_HASH_MISMATCH",
        "WRITE_REQUEST_TOO_LARGE",
        "WRITE_COMMAND_INVALID",
        "WRITE_SCOPE_MISMATCH",
        "WRITE_CURRENT_STATE_INVALID",
        "WRITE_CURRENT_STATE_MISMATCH",
        "WRITE_BASE_CANONICAL_REQUIRED",
        "WRITE_BASE_CANONICAL_INVALID",
    }:
        return (
            _error_response(
                503,
                correlation_id=correlation_id,
                state="unavailable",
                code="API_TEMPORARILY_UNAVAILABLE",
                message="The review service is temporarily unavailable.",
                retryable=False,
            ),
            False,
        )
    return (
        _error_response(
            503,
            correlation_id=correlation_id,
            state="unavailable",
            code="API_RECONCILIATION_REQUIRED",
            message="The mutation outcome is ambiguous. Reconcile with an authorized read before any retry.",
            retryable=False,
            reconciliation_required=True,
        ),
        True,
    )


def handle_revision_proposal(
    request: ApiHarnessRequest,
    deps: ApiHarnessDependencies,
) -> ApiHarnessResponse:
    """Execute the v1 mutation contract without registering a network route.

    This is intentionally an in-process harness. It models session/CSRF/origin,
    resource/operation authorization, exact snapshot resolution, server command
    construction, Stage 8-G composition, safe audit mapping, and idempotency
    reconciliation while keeping every production/live activation lock closed.
    """

    if not isinstance(request, ApiHarnessRequest) or not isinstance(deps, ApiHarnessDependencies):
        _fail("API_SERVER_CONFIGURATION_INVALID")
    correlation_id = _correlation_id(deps)

    principal = deps.session_authenticator(request.session_token)
    if not isinstance(principal, ApiPrincipal):
        return _error_response(
            401,
            correlation_id=correlation_id,
            state="rejected",
            code="API_UNAUTHENTICATED",
            message="Authentication is required.",
        )
    if not deps.csrf_validator(principal, request.session_token, request.csrf_token):
        return _error_response(
            403,
            correlation_id=correlation_id,
            state="rejected",
            code="API_CSRF_INVALID",
            message="The request failed the CSRF check.",
        )
    if request.origin != deps.allowed_origin:
        return _error_response(
            403,
            correlation_id=correlation_id,
            state="rejected",
            code="API_ORIGIN_INVALID",
            message="The request origin is not allowed.",
        )

    if type(request.document_id) is not str or _ID_RE.fullmatch(request.document_id) is None:
        return _error_response(
            404,
            correlation_id=correlation_id,
            state="rejected",
            code="API_RESOURCE_NOT_VISIBLE",
            message="The requested resource is not visible.",
        )
    coarse = deps.coarse_authorizer(principal, request.document_id, "revision.propose")
    if coarse == "not_visible":
        return _error_response(
            404,
            correlation_id=correlation_id,
            state="rejected",
            code="API_RESOURCE_NOT_VISIBLE",
            message="The requested resource is not visible.",
        )
    if coarse != "allow":
        return _error_response(
            403,
            correlation_id=correlation_id,
            state="rejected",
            code="API_FORBIDDEN",
            message="The requested action is not allowed.",
        )

    if (
        type(request.content_type) is not str
        or request.content_type.lower().strip() != "application/json"
    ):
        return _error_response(
            400,
            correlation_id=correlation_id,
            state="rejected",
            code="API_REQUEST_INVALID",
            message="Teacher Review API v1 accepts application/json only.",
        )
    if (
        type(request.idempotency_key) is not str
        or _IDEMPOTENCY_RE.fullmatch(request.idempotency_key) is None
    ):
        return _error_response(
            400,
            correlation_id=correlation_id,
            state="rejected",
            code="API_IDEMPOTENCY_KEY_INVALID",
            message="A valid bounded Idempotency-Key is required.",
        )

    try:
        intent = _parse_intent(request.raw_body)
    except ApiHarnessError as exc:
        return _map_prewrite_error(exc.code, correlation_id)

    operation_type = intent["operation"]["type"]
    if not deps.operation_authorizer(principal, request.document_id, operation_type):
        return _error_response(
            403,
            correlation_id=correlation_id,
            state="rejected",
            code="API_OPERATION_FORBIDDEN",
            message="The requested musical operation is not allowed.",
        )

    request_digest = _digest(intent)
    inspected = deps.outer_idempotency.inspect(
        principal=principal,
        document_id=request.document_id,
        raw_key=request.idempotency_key,
        intent=intent,
        request_digest=request_digest,
    )
    if inspected.outcome == "conflict":
        return _error_response(
            409,
            correlation_id=correlation_id,
            state="conflict",
            code="API_IDEMPOTENCY_CONFLICT",
            message="The idempotency key conflicts with another request.",
        )
    if inspected.outcome == "pending":
        return _error_response(
            503,
            correlation_id=correlation_id,
            state="unavailable",
            code="API_RECONCILIATION_REQUIRED",
            message="The mutation outcome is ambiguous. Reconcile with an authorized read before any retry.",
            reconciliation_required=True,
        )
    if inspected.outcome == "replay" and inspected.response is not None:
        return _replayed_response(inspected.response)

    context = deps.document_resolver(principal, request.document_id)
    if (
        not isinstance(context, ApiDocumentContext)
        or context.document_id != request.document_id
        or context.scope.tenant_id != principal.tenant_id
    ):
        return _error_response(
            404,
            correlation_id=correlation_id,
            state="rejected",
            code="API_RESOURCE_NOT_VISIBLE",
            message="The requested resource is not visible.",
        )

    try:
        parent_id, parent_sha = _verify_snapshot(
            intent=intent,
            context=context,
            store=deps.store,
        )
        location = _resolve_target_location(context.current_state, intent["target"])
        old_value_sha = expected_old_value_sha256(
            context.current_state,
            location=location,
            operation_type=operation_type,
        )
    except (ApiHarnessError, Stage8MaterializationError) as exc:
        code = exc.code if hasattr(exc, "code") else "API_SERVER_STATE_INVALID"
        return _map_prewrite_error(code, correlation_id)

    reserved = deps.outer_idempotency.begin(
        principal=principal,
        document_id=request.document_id,
        raw_key=request.idempotency_key,
        intent=intent,
        request_digest=request_digest,
    )
    if reserved.outcome == "conflict":
        return _error_response(
            409,
            correlation_id=correlation_id,
            state="conflict",
            code="API_IDEMPOTENCY_CONFLICT",
            message="The idempotency key conflicts with another request.",
        )
    if reserved.outcome == "pending":
        return _error_response(
            503,
            correlation_id=correlation_id,
            state="unavailable",
            code="API_RECONCILIATION_REQUIRED",
            message="The mutation outcome is ambiguous. Reconcile with an authorized read before any retry.",
            reconciliation_required=True,
        )
    if reserved.outcome == "replay" and reserved.response is not None:
        return _replayed_response(reserved.response)
    slot_id = reserved.slot_id

    try:
        decision_id = deps.decision_id_factory()
        command_id = deps.command_id_factory()
        _require_id(decision_id, "API_SERVER_CONFIGURATION_INVALID")
        _require_id(command_id, "API_SERVER_CONFIGURATION_INVALID")
        grant: ReviewAuthorizationGrant = issue_authorization_grant(
            decision_id=decision_id,
            reviewer_id=principal.reviewer_id,
            tenant_id=principal.tenant_id,
            job_id=context.scope.job_id,
            review_report_id=context.scope.review_report_id,
            review_report_sha256=context.scope.review_report_sha256,
            canonical_score_sha256=context.scope.base_canonical_sha256,
            parent_revision_id=parent_id,
            parent_revision_sha256=parent_sha,
            allowed_actions=("revision:read", "revision:propose"),
            signing_key=deps.signing_key,
        )
        command = build_score_edit_command({
            "schemaVersion": COMMAND_VERSION,
            "commandId": command_id,
            "jobId": context.scope.job_id,
            "reviewerId": principal.reviewer_id,
            "authorizationDecisionId": decision_id,
            "reviewReportId": context.scope.review_report_id,
            "reviewReportSha256": context.scope.review_report_sha256,
            "baseCanonicalSha256": context.scope.base_canonical_sha256,
            "baseRevisionId": parent_id,
            "baseRevisionSha256": parent_sha,
            "issueId": intent["evidenceContext"]["issueId"],
            "location": location,
            "operation": intent["operation"],
            "oldValueSha256": old_value_sha,
            "reason": intent["reason"],
        })
        internal_request = build_write_request(command)
    except (ApiHarnessError, Stage8ContractError, Stage8WriteBoundaryError):
        deps.outer_idempotency.abort(slot_id=slot_id)
        return _error_response(
            503,
            correlation_id=correlation_id,
            state="unavailable",
            code="API_TEMPORARILY_UNAVAILABLE",
            message="The review service is temporarily unavailable.",
        )

    try:
        result = deps.write_invoker(
            request_payload=internal_request,
            grant=grant,
            signing_key=deps.signing_key,
            scope=context.scope,
            reviewer_id=principal.reviewer_id,
            current_state=context.current_state,
            base_canonical_payload=context.base_canonical_payload,
            store=deps.store,
            idempotency_reserver=deps.stage8_idempotency_reserver,
        )
    except Stage8WriteBoundaryError as exc:
        response, ambiguous = _map_stage8_error(exc.code, correlation_id)
        if not ambiguous:
            deps.outer_idempotency.abort(slot_id=slot_id)
        return response
    except Exception:
        return _error_response(
            503,
            correlation_id=correlation_id,
            state="unavailable",
            code="API_RECONCILIATION_REQUIRED",
            message="The mutation outcome is ambiguous. Reconcile with an authorized read before any retry.",
            reconciliation_required=True,
        )

    response = _success_response(
        correlation_id=correlation_id,
        document_id=request.document_id,
        intent=intent,
        result=result,
    )
    audit_event = {
        "schemaVersion": API_HARNESS_VERSION,
        "correlationId": correlation_id,
        "principalId": principal.principal_id,
        "reviewerId": principal.reviewer_id,
        "tenantId": principal.tenant_id,
        "documentId": request.document_id,
        "requestDigest": request_digest,
        "operation": operation_type,
        "parentRevisionId": parent_id,
        "parentRevisionSha256": parent_sha,
        "commandSha256": result.command_sha256,
        "revisionSha256": result.revision.to_dict()["revisionSha256"],
        "resultingMusicalStateSha256": result.state.state_sha256,
        "outcome": response.body["state"],
        "authoritativeCapability": False,
    }
    try:
        deps.audit_sink(audit_event)
    except Exception:
        return _error_response(
            503,
            correlation_id=correlation_id,
            state="unavailable",
            code="API_RECONCILIATION_REQUIRED",
            message="The mutation outcome is ambiguous. Reconcile with an authorized read before any retry.",
            reconciliation_required=True,
        )

    deps.outer_idempotency.commit(slot_id=slot_id, response=response)
    return response


__all__ = [
    "API_HARNESS_VERSION",
    "API_EDIT_INTENT_VERSION",
    "API_REVISION_RESULT_VERSION",
    "ApiDocumentContext",
    "ApiHarnessDependencies",
    "ApiHarnessError",
    "ApiHarnessRequest",
    "ApiHarnessResponse",
    "ApiPrincipal",
    "MemoryApiIdempotencyLedger",
    "MemoryStage8IdempotencyReserver",
    "handle_revision_proposal",
]
