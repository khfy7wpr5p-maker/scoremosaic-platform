"""Fail-closed HTTP wiring for Stage 4-C2 engine receiver routes.

The handler exposes only authenticated internal control-plane endpoints. It
never executes an OMR engine, retrieves source bytes, mutates Gateway state,
retries work, or accepts caller-selected destinations.
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
from .receiver_authority import EngineReceiverAuthority
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
_RECEIVER_PATHS = frozenset({TRUSTED_PLAN_PROVISIONING_PATH, DISPATCH_PATH})
_SAFE_HEADER_NAME_MAX = 128
_SAFE_HEADER_VALUE_MAX = 512


class ReceiverHttpError(ValueError):
    """Stable HTTP-framing error with a bounded status mapping."""

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

    def __post_init__(self) -> None:
        if (
            type(self.authority) is not EngineReceiverAuthority
            or type(self.dispatch_rotation) is not ReceiverCredentialRotation
            or not callable(self.provisioning_credential_resolver)
            or not callable(self.dispatch_credential_resolver)
            or not callable(self.now_seconds)
        ):
            raise ReceiverHttpError("receiver_context_invalid", 503)


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
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name + value)
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


def _single_header(
    normalized: dict[str, list[str]],
    name: str,
    *,
    missing_status: int = 400,
) -> str:
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


def receiver_body_length(
    *,
    method: str,
    target: str,
    headers: Sequence[tuple[str, str]],
) -> int:
    """Validate HTTP framing before any body bytes are read."""

    path = _exact_target(method, target)
    normalized = _normalized_headers(headers)
    if "transfer-encoding" in normalized:
        raise ReceiverHttpError("receiver_transfer_encoding_forbidden", 400)
    content_length = _canonical_positive_decimal(
        _single_header(normalized, "content-length", missing_status=411)
    )
    content_type = _single_header(normalized, "content-type", missing_status=415)
    if content_type != "application/json":
        raise ReceiverHttpError("receiver_content_type_invalid", 415)
    expected_x_headers = (
        {PROVISIONING_SIGNATURE_HEADER}
        if path == TRUSTED_PLAN_PROVISIONING_PATH
        else set(WIRE_HEADER_NAMES)
    )
    observed_x_headers = {
        name for name in normalized if name.startswith("x-scoremosaic-")
    }
    if observed_x_headers != expected_x_headers:
        raise ReceiverHttpError("receiver_security_headers_invalid", 400)
    for name in expected_x_headers:
        _single_header(normalized, name)
    maximum = (
        MAX_PROVISIONING_REQUEST_BYTES
        if path == TRUSTED_PLAN_PROVISIONING_PATH
        else MAX_DISPATCH_BODY_BYTES
    )
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
    if "replay" in category:
        return ReceiverHttpResponse(status=409, payload={"error": "receiver_replay_detected"})
    if "conflict" in category:
        return ReceiverHttpResponse(status=409, payload={"error": "receiver_conflict"})
    if (
        "state_invalid" in category
        or "authority_invalid" in category
        or "credential_unavailable" in category
    ):
        return ReceiverHttpResponse(status=503, payload={"error": "receiver_state_unavailable"})
    return ReceiverHttpResponse(status=403, payload={"error": "receiver_rejected"})


def handle_receiver_http_request(
    *,
    method: str,
    target: str,
    headers: Sequence[tuple[str, str]],
    body: bytes,
    context: ReceiverHttpContext | None,
) -> ReceiverHttpResponse:
    """Handle one already-bounded internal receiver request."""

    try:
        expected_length = receiver_body_length(method=method, target=target, headers=headers)
    except ReceiverHttpError as exc:
        return ReceiverHttpResponse(
            status=exc.status,
            payload={"error": exc.category},
            allow=exc.allow,
        )
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
        signature = _single_header(normalized, PROVISIONING_SIGNATURE_HEADER)
        try:
            accepted = accept_trusted_plan_provisioning(
                authority=context.authority,
                request_bytes=body,
                signature=signature,
                now_seconds=now,
                credential_resolver=context.provisioning_credential_resolver,
            )
        except TrustedPlanProvisioningError as exc:
            return _business_error(exc)
        return ReceiverHttpResponse(
            status=201,
            payload={
                "status": "accepted",
                "kind": "trusted_plan",
                "evidence": accepted.as_safe_dict(),
                "engineExecutionAllowed": False,
            },
        )

    dispatch_headers = tuple(
        (name, _single_header(normalized, name)) for name in WIRE_HEADER_NAMES
    )
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
    except AuthenticatedDispatchReceiverError as exc:
        return _business_error(exc)
    return ReceiverHttpResponse(
        status=202,
        payload={
            "status": "accepted",
            "kind": "dispatch",
            "evidence": accepted_dispatch.as_safe_dict(),
            "engineExecutionAllowed": False,
        },
    )


def read_and_handle_receiver_http(
    handler: object,
    *,
    context: ReceiverHttpContext | None,
) -> ReceiverHttpResponse:
    """Validate framing before bounded body read from BaseHTTPRequestHandler."""

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
        expected_length = receiver_body_length(
            method=method,
            target=target,
            headers=header_pairs,
        )
    except ReceiverHttpError as exc:
        return ReceiverHttpResponse(
            status=exc.status,
            payload={"error": exc.category},
            allow=exc.allow,
        )
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
