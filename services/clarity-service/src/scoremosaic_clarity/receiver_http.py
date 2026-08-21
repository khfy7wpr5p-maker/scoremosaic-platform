"""Fail-closed HTTP wiring for authenticated engine receiver routes.

Stage 5-B3a adds an authenticated execution trigger while preserving the
existing provisioning, dispatch and source-delivery contracts. Execution is
available only when an explicit engine-owned execution context is injected.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Callable, Sequence
from urllib.parse import urlsplit

from .authenticated_dispatch_receiver import (
    AuthenticatedDispatchReceiverError,
    ReceiverCredentialRotation,
    WIRE_HEADER_NAMES,
    accept_authenticated_dispatch,
)
from .authenticated_execution_trigger import (
    AuthenticatedExecutionTriggerError,
    EngineExecutionHttpContext,
    EXECUTION_TRIGGER_HEADER_NAMES,
    EXECUTION_TRIGGER_MAX_BODY_BYTES,
    EXECUTION_TRIGGER_PATH,
    accept_authenticated_execution_trigger,
)
from .dispatch_acceptance import DispatchAcceptanceStoreError, EngineDispatchAcceptanceStore
from .receiver_authority import EngineReceiverAuthority
from .source_delivery import (
    EngineSourceStore,
    SOURCE_DELIVERY_HEADER_NAMES,
    SOURCE_DELIVERY_MAX_BYTES,
    SOURCE_DELIVERY_PATH,
    SourceDeliveryReceiverError,
    SourceDeliveryRotation,
    accept_source_delivery,
)
from .trusted_plan_provisioning import (
    MAX_PROVISIONING_REQUEST_BYTES,
    TRUSTED_PLAN_PROVISIONING_PATH,
    TrustedPlanProvisioningError,
    accept_trusted_plan_provisioning,
)

DISPATCH_PATH = "/internal/transcribe"
PROVISIONING_SIGNATURE_HEADER = "x-scoremosaic-provisioning-signature"
MAX_DISPATCH_BODY_BYTES = 4096
MAX_SAFE_RESPONSE_BYTES = 16 * 1024
_RECEIVER_PATHS = frozenset({
    TRUSTED_PLAN_PROVISIONING_PATH,
    DISPATCH_PATH,
    SOURCE_DELIVERY_PATH,
    EXECUTION_TRIGGER_PATH,
})
_SAFE_HEADER_NAME_MAX = 128
_SAFE_HEADER_VALUE_MAX = 512


class ReceiverHttpError(ValueError):
    def __init__(self, category: str, status: int, *, allow: str | None = None) -> None:
        self.category = category
        self.status = status
        self.allow = allow
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ReceiverHttpContext:
    authority: EngineReceiverAuthority
    provisioning_credential_resolver: Callable[[str, str], object]
    dispatch_rotation: ReceiverCredentialRotation
    dispatch_credential_resolver: Callable[[str, str], object]
    now_seconds: Callable[[], int] = lambda: int(time.time())
    dispatch_acceptance_store: EngineDispatchAcceptanceStore | None = None
    source_store: EngineSourceStore | None = None
    source_rotation: SourceDeliveryRotation | None = None
    source_credential_resolver: Callable[[str, str], object] | None = None
    execution_http_context: EngineExecutionHttpContext | None = None

    def __post_init__(self) -> None:
        if (
            type(self.authority) is not EngineReceiverAuthority
            or type(self.dispatch_rotation) is not ReceiverCredentialRotation
            or not callable(self.provisioning_credential_resolver)
            or not callable(self.dispatch_credential_resolver)
            or not callable(self.now_seconds)
        ):
            raise ReceiverHttpError("receiver_context_invalid", 503)
        source_values = (
            self.dispatch_acceptance_store,
            self.source_store,
            self.source_rotation,
            self.source_credential_resolver,
        )
        if all(value is None for value in source_values):
            if self.execution_http_context is not None:
                raise ReceiverHttpError("receiver_context_invalid", 503)
            return
        if (
            type(self.dispatch_acceptance_store) is not EngineDispatchAcceptanceStore
            or type(self.source_store) is not EngineSourceStore
            or type(self.source_rotation) is not SourceDeliveryRotation
            or not callable(self.source_credential_resolver)
            or (
                self.execution_http_context is not None
                and type(self.execution_http_context) is not EngineExecutionHttpContext
            )
        ):
            raise ReceiverHttpError("receiver_context_invalid", 503)

    @property
    def source_delivery_enabled(self) -> bool:
        return self.dispatch_acceptance_store is not None

    @property
    def execution_enabled(self) -> bool:
        return self.source_delivery_enabled and self.execution_http_context is not None


@dataclass(frozen=True, slots=True)
class ReceiverHttpResponse:
    status: int
    payload: dict[str, object]
    allow: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.status) is not int
            or not 100 <= self.status <= 599
            or type(self.payload) is not dict
            or (self.allow is not None and type(self.allow) is not str)
        ):
            raise ReceiverHttpError("receiver_response_invalid", 500)
        encoded = json.dumps(
            self.payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        if len(encoded) > MAX_SAFE_RESPONSE_BYTES:
            raise ReceiverHttpError("receiver_response_invalid", 500)


def is_receiver_target(target: str) -> bool:
    if type(target) is not str:
        return False
    try:
        parsed = urlsplit(target)
    except ValueError:
        return False
    return parsed.path in _RECEIVER_PATHS


def _safe_header_pair(name: object, value: object) -> tuple[str, str]:
    if type(name) is not str or type(value) is not str:
        raise ReceiverHttpError("receiver_headers_invalid", 400)
    try:
        name_bytes = name.encode("ascii")
        value_bytes = value.encode("ascii")
    except UnicodeEncodeError:
        raise ReceiverHttpError("receiver_headers_invalid", 400) from None
    if (
        not name_bytes
        or len(name_bytes) > _SAFE_HEADER_NAME_MAX
        or len(value_bytes) > _SAFE_HEADER_VALUE_MAX
        or name != name.strip()
        or value != value.strip()
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in name + value)
    ):
        raise ReceiverHttpError("receiver_headers_invalid", 400)
    return name.lower(), value


def _normalized_headers(headers: Sequence[tuple[str, str]]) -> dict[str, list[str]]:
    if type(headers) not in {tuple, list}:
        raise ReceiverHttpError("receiver_headers_invalid", 400)
    normalized: dict[str, list[str]] = {}
    for pair in headers:
        if type(pair) is not tuple or len(pair) != 2:
            raise ReceiverHttpError("receiver_headers_invalid", 400)
        name, value = _safe_header_pair(pair[0], pair[1])
        normalized.setdefault(name, []).append(value)
    return normalized


def _single_header(normalized: dict[str, list[str]], name: str, *, missing_status: int = 400) -> str:
    values = normalized.get(name)
    if values is None:
        raise ReceiverHttpError("receiver_header_missing", missing_status)
    if len(values) != 1:
        raise ReceiverHttpError("receiver_header_ambiguous", 400)
    return values[0]


def _canonical_positive_decimal(value: str) -> int:
    if not value.isdigit() or value.startswith("0"):
        raise ReceiverHttpError("receiver_content_length_invalid", 400)
    try:
        parsed = int(value, 10)
    except ValueError:
        raise ReceiverHttpError("receiver_content_length_invalid", 400) from None
    if parsed < 1:
        raise ReceiverHttpError("receiver_content_length_invalid", 400)
    return parsed


def _exact_target(method: object, target: object) -> str:
    if type(method) is not str or type(target) is not str:
        raise ReceiverHttpError("receiver_target_invalid", 400)
    try:
        parsed = urlsplit(target)
    except ValueError:
        raise ReceiverHttpError("receiver_target_invalid", 400) from None
    if parsed.path not in _RECEIVER_PATHS:
        raise ReceiverHttpError("receiver_target_invalid", 404)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ReceiverHttpError("receiver_target_invalid", 400)
    if method != "POST":
        raise ReceiverHttpError("receiver_method_not_allowed", 405, allow="POST")
    return parsed.path


def receiver_body_length(*, method: str, target: str, headers: Sequence[tuple[str, str]]) -> int:
    path = _exact_target(method, target)
    normalized = _normalized_headers(headers)
    if "transfer-encoding" in normalized:
        raise ReceiverHttpError("receiver_transfer_encoding_forbidden", 400)
    content_length = _canonical_positive_decimal(
        _single_header(normalized, "content-length", missing_status=411)
    )
    content_type = _single_header(normalized, "content-type", missing_status=415)
    if path == SOURCE_DELIVERY_PATH:
        expected_x_headers = set(SOURCE_DELIVERY_HEADER_NAMES)
        maximum = SOURCE_DELIVERY_MAX_BYTES
    elif path == EXECUTION_TRIGGER_PATH:
        expected_x_headers = set(EXECUTION_TRIGGER_HEADER_NAMES)
        maximum = EXECUTION_TRIGGER_MAX_BODY_BYTES
        if content_type != "application/json":
            raise ReceiverHttpError("receiver_content_type_invalid", 415)
    elif path == TRUSTED_PLAN_PROVISIONING_PATH:
        expected_x_headers = {PROVISIONING_SIGNATURE_HEADER}
        maximum = MAX_PROVISIONING_REQUEST_BYTES
        if content_type != "application/json":
            raise ReceiverHttpError("receiver_content_type_invalid", 415)
    else:
        expected_x_headers = set(WIRE_HEADER_NAMES)
        maximum = MAX_DISPATCH_BODY_BYTES
        if content_type != "application/json":
            raise ReceiverHttpError("receiver_content_type_invalid", 415)
    observed_x = {name for name in normalized if name.startswith("x-scoremosaic-")}
    if observed_x != expected_x_headers:
        raise ReceiverHttpError("receiver_security_headers_invalid", 400)
    for name in expected_x_headers:
        _single_header(normalized, name)
    if (
        path == SOURCE_DELIVERY_PATH
        and content_type != _single_header(normalized, "x-scoremosaic-source-media-type")
    ):
        raise ReceiverHttpError("receiver_content_type_invalid", 415)
    if content_length > maximum:
        raise ReceiverHttpError("receiver_body_too_large", 413)
    return content_length


def _now(context: ReceiverHttpContext) -> int:
    try:
        value = context.now_seconds()
    except Exception:
        raise ReceiverHttpError("receiver_clock_unavailable", 503) from None
    if type(value) is not int or value < 0:
        raise ReceiverHttpError("receiver_clock_unavailable", 503)
    return value


def _business_error(exc: Exception) -> ReceiverHttpResponse:
    category = getattr(exc, "category", "")
    if type(category) is not str:
        category = ""
    if "reconciliation_required" in category or "replay" in category or "conflict" in category:
        return ReceiverHttpResponse(status=409, payload={"error": "receiver_reconciliation_required"})
    if "not_found" in category or "mismatch" in category or "prerequisite" in category:
        return ReceiverHttpResponse(status=409, payload={"error": "receiver_prerequisite_not_satisfied"})
    if (
        "state_invalid" in category
        or "authority_invalid" in category
        or "credential_unavailable" in category
        or "execution_failed" in category
    ):
        return ReceiverHttpResponse(status=503, payload={"error": "receiver_state_unavailable"})
    return ReceiverHttpResponse(status=403, payload={"error": "receiver_rejected"})


def _source_headers(normalized: dict[str, list[str]]) -> tuple[tuple[str, str], ...]:
    return tuple((name, _single_header(normalized, name)) for name in SOURCE_DELIVERY_HEADER_NAMES)


def _execution_headers(normalized: dict[str, list[str]]) -> tuple[tuple[str, str], ...]:
    return tuple((name, _single_header(normalized, name)) for name in EXECUTION_TRIGGER_HEADER_NAMES)


def handle_receiver_http_request(
    *,
    method: str,
    target: str,
    headers: Sequence[tuple[str, str]],
    body: bytes,
    context: ReceiverHttpContext | None,
) -> ReceiverHttpResponse:
    try:
        expected_length = receiver_body_length(method=method, target=target, headers=headers)
    except ReceiverHttpError as exc:
        return ReceiverHttpResponse(status=exc.status, payload={"error": exc.category}, allow=exc.allow)
    if type(body) is not bytes or len(body) != expected_length:
        return ReceiverHttpResponse(status=400, payload={"error": "receiver_body_length_mismatch"})
    if context is None or type(context) is not ReceiverHttpContext:
        return ReceiverHttpResponse(status=503, payload={"error": "receiver_context_unavailable"})
    normalized = _normalized_headers(headers)
    path = urlsplit(target).path
    try:
        now = _now(context)
    except ReceiverHttpError:
        return ReceiverHttpResponse(status=503, payload={"error": "receiver_state_unavailable"})

    if path == TRUSTED_PLAN_PROVISIONING_PATH:
        try:
            accepted = accept_trusted_plan_provisioning(
                authority=context.authority,
                request_bytes=body,
                signature=_single_header(normalized, PROVISIONING_SIGNATURE_HEADER),
                now_seconds=now,
                credential_resolver=context.provisioning_credential_resolver,
            )
        except TrustedPlanProvisioningError as exc:
            return _business_error(exc)
        return ReceiverHttpResponse(
            status=201,
            payload={"status": "accepted", "kind": "trusted_plan", "evidence": accepted.as_safe_dict(), "engineExecutionAllowed": False},
        )

    if path == SOURCE_DELIVERY_PATH:
        if not context.source_delivery_enabled:
            return ReceiverHttpResponse(status=503, payload={"error": "receiver_context_unavailable"})
        assert context.dispatch_acceptance_store is not None
        assert context.source_store is not None
        assert context.source_rotation is not None
        assert context.source_credential_resolver is not None
        try:
            context.dispatch_acceptance_store.require(
                job_id=_single_header(normalized, "x-scoremosaic-source-job"),
                run_id=_single_header(normalized, "x-scoremosaic-source-run"),
                dispatch_identity_sha256=_single_header(normalized, "x-scoremosaic-source-dispatch-sha256"),
            )
            accepted_source = accept_source_delivery(
                authority=context.authority,
                store=context.source_store,
                rotation=context.source_rotation,
                headers=_source_headers(normalized),
                body=body,
                now_seconds=now,
                credential_resolver=context.source_credential_resolver,
            )
        except (DispatchAcceptanceStoreError, SourceDeliveryReceiverError) as exc:
            return _business_error(exc)
        return ReceiverHttpResponse(
            status=201 if accepted_source.persistence_state == "written" else 200,
            payload={"status": "accepted", "kind": "source", "evidence": accepted_source.as_safe_dict(), "engineExecutionAllowed": False},
        )

    if path == EXECUTION_TRIGGER_PATH:
        if not context.execution_enabled:
            return ReceiverHttpResponse(status=503, payload={"error": "receiver_context_unavailable"})
        assert context.dispatch_acceptance_store is not None
        assert context.source_store is not None
        assert context.execution_http_context is not None
        try:
            accepted_execution = accept_authenticated_execution_trigger(
                authority=context.authority,
                dispatch_acceptance_store=context.dispatch_acceptance_store,
                source_store=context.source_store,
                http_context=context.execution_http_context,
                headers=_execution_headers(normalized),
                body=body,
                now_seconds=now,
            )
        except AuthenticatedExecutionTriggerError as exc:
            return _business_error(exc)
        return ReceiverHttpResponse(
            status=200,
            payload={
                "status": "executed",
                "kind": "execution",
                "evidence": accepted_execution.as_safe_dict(),
                "engineExecutionPerformed": True,
                "resultReturnAllowed": False,
                "resultPersistenceAllowed": False,
            },
        )

    dispatch_headers = tuple((name, _single_header(normalized, name)) for name in WIRE_HEADER_NAMES)
    try:
        accepted_dispatch = accept_authenticated_dispatch(
            authority=context.authority,
            rotation=context.dispatch_rotation,
            headers=dispatch_headers,
            body=body,
            observed_method=method,
            observed_path=path,
            now_seconds=now,
            credential_resolver=context.dispatch_credential_resolver,
        )
        if context.source_delivery_enabled:
            assert context.dispatch_acceptance_store is not None
            context.dispatch_acceptance_store.publish(
                job_id=accepted_dispatch.job_id,
                run_id=accepted_dispatch.run_id,
                dispatch_identity_sha256=accepted_dispatch.dispatch_identity_sha256,
            )
    except (AuthenticatedDispatchReceiverError, DispatchAcceptanceStoreError) as exc:
        return _business_error(exc)
    return ReceiverHttpResponse(
        status=202,
        payload={"status": "accepted", "kind": "dispatch", "evidence": accepted_dispatch.as_safe_dict(), "engineExecutionAllowed": False},
    )


def read_and_handle_receiver_http(handler: object, *, context: ReceiverHttpContext | None) -> ReceiverHttpResponse:
    method = getattr(handler, "command", None)
    target = getattr(handler, "path", None)
    header_object = getattr(handler, "headers", None)
    stream = getattr(handler, "rfile", None)
    if (
        type(method) is not str
        or type(target) is not str
        or header_object is None
        or stream is None
        or not hasattr(header_object, "raw_items")
        or not hasattr(stream, "read")
    ):
        return ReceiverHttpResponse(status=400, payload={"error": "receiver_http_request_invalid"})
    try:
        header_pairs = tuple(header_object.raw_items())
        expected_length = receiver_body_length(method=method, target=target, headers=header_pairs)
    except ReceiverHttpError as exc:
        return ReceiverHttpResponse(status=exc.status, payload={"error": exc.category}, allow=exc.allow)
    except Exception:
        return ReceiverHttpResponse(status=400, payload={"error": "receiver_headers_invalid"})
    try:
        body = stream.read(expected_length)
    except Exception:
        return ReceiverHttpResponse(status=400, payload={"error": "receiver_body_read_failed"})
    if type(body) is not bytes or len(body) != expected_length:
        return ReceiverHttpResponse(status=400, payload={"error": "receiver_body_length_mismatch"})
    try:
        return handle_receiver_http_request(
            method=method,
            target=target,
            headers=header_pairs,
            body=body,
            context=context,
        )
    except Exception:
        return ReceiverHttpResponse(status=503, payload={"error": "receiver_state_unavailable"})
