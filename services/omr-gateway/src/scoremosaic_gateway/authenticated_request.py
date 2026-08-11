"""Contract-only authenticated request envelope for Gate C.2-A.

This module deliberately does not send network requests, register HTTP routes,
read production secrets, or enable orchestration. It defines a deterministic
HMAC-SHA256 request envelope and receiver-verification boundary that later Gate C
slices can wire into private engine transport.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Callable

from .service_auth import (
    EngineAuthBinding,
    EngineCredential,
    MAX_CREDENTIAL_BYTES,
    MIN_CREDENTIAL_BYTES,
    ServiceAuthError,
    _validated_resolver_key,
)

REQUEST_AUTH_VERSION = "scoremosaic-s2s-request-v1"
REQUEST_AUTH_ALGORITHM = "hmac-sha256"
MAX_AUTH_PAYLOAD_BYTES = 20 * 1024 * 1024
MAX_AUTH_PATH_BYTES = 256
MAX_REQUEST_AGE_SECONDS = 120
MAX_FUTURE_SKEW_SECONDS = 30
NONCE_HEX_LENGTH = 32
SHA256_HEX_LENGTH = 64
_ALLOWED_METHODS = frozenset({"POST"})
_LOWER_HEX_RE = re.compile(r"^[0-9a-f]+$")
_HTTP_METHOD_RE = re.compile(r"^[A-Z]{1,16}$")


class RequestAuthError(ValueError):
    """Safe bounded authenticated-request contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticatedRequestEnvelope:
    """Non-secret signed request metadata for one private engine request."""

    version: str
    algorithm: str
    binding_version: str
    caller_identity: str
    engine: str
    audience_identity: str
    environment: str
    credential_key: str
    method: str
    path: str
    timestamp: int
    nonce: str
    payload_bytes: int
    payload_sha256: str
    signature: str

    def __repr__(self) -> str:
        return (
            "AuthenticatedRequestEnvelope("
            f"version={self.version!r}, algorithm={self.algorithm!r}, "
            f"engine={self.engine!r}, environment={self.environment!r}, "
            f"method={self.method!r}, path={self.path!r}, "
            f"timestamp={self.timestamp!r}, nonce={self.nonce!r}, "
            f"payload_bytes={self.payload_bytes!r}, "
            f"payload_sha256={self.payload_sha256!r}, signature=<redacted>)"
        )

    def as_safe_dict(self) -> dict[str, object]:
        """Return bounded non-secret diagnostics without authentication proof."""

        return {
            "version": self.version,
            "algorithm": self.algorithm,
            "bindingVersion": self.binding_version,
            "callerIdentity": self.caller_identity,
            "engine": self.engine,
            "audienceIdentity": self.audience_identity,
            "environment": self.environment,
            "credentialKey": self.credential_key,
            "method": self.method,
            "path": self.path,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "payloadBytes": self.payload_bytes,
            "payloadSha256": self.payload_sha256,
            "signaturePresent": bool(self.signature),
        }


ReplayChecker = Callable[[EngineAuthBinding, str, int], bool]


def _require_exact_payload(payload: bytes) -> bytes:
    if type(payload) is not bytes:
        raise RequestAuthError("payload_invalid")
    if len(payload) > MAX_AUTH_PAYLOAD_BYTES:
        raise RequestAuthError("payload_too_large")
    return payload


def _require_method(method: str) -> str:
    if type(method) is not str or method not in _ALLOWED_METHODS:
        raise RequestAuthError("method_not_allowed")
    return method


def _require_observed_method(method: str) -> str:
    if type(method) is not str or _HTTP_METHOD_RE.fullmatch(method) is None:
        raise RequestAuthError("observed_method_invalid")
    return method


def _require_path(path: str) -> str:
    if type(path) is not str:
        raise RequestAuthError("path_invalid")
    try:
        encoded = path.encode("ascii")
    except UnicodeEncodeError:
        raise RequestAuthError("path_invalid") from None
    if not encoded or len(encoded) > MAX_AUTH_PATH_BYTES:
        raise RequestAuthError("path_invalid")
    if not path.startswith("/") or path.startswith("//"):
        raise RequestAuthError("path_invalid")
    if any(char in path for char in ("?", "#", "\\", "%")):
        raise RequestAuthError("path_invalid")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in path):
        raise RequestAuthError("path_invalid")
    segments = path.split("/")[1:]
    if any(segment in {".", ".."} for segment in segments):
        raise RequestAuthError("path_invalid")
    return path


def _require_timestamp(timestamp: int) -> int:
    if type(timestamp) is not int or timestamp < 0:
        raise RequestAuthError("timestamp_invalid")
    return timestamp


def _require_nonce(nonce: str) -> str:
    if (
        type(nonce) is not str
        or len(nonce) != NONCE_HEX_LENGTH
        or _LOWER_HEX_RE.fullmatch(nonce) is None
    ):
        raise RequestAuthError("nonce_invalid")
    return nonce


def _require_sha256_hex(value: str, category: str) -> str:
    if (
        type(value) is not str
        or len(value) != SHA256_HEX_LENGTH
        or _LOWER_HEX_RE.fullmatch(value) is None
    ):
        raise RequestAuthError(category)
    return value


def _credential_secret(credential: EngineCredential) -> bytes:
    if type(credential) is not EngineCredential:
        raise RequestAuthError("credential_invalid")
    try:
        _validated_resolver_key(credential.binding)
    except ServiceAuthError:
        raise RequestAuthError("credential_binding_invalid") from None

    secret = credential.secret_bytes_for_transport()
    if type(secret) is not bytes:
        raise RequestAuthError("credential_invalid")
    if not MIN_CREDENTIAL_BYTES <= len(secret) <= MAX_CREDENTIAL_BYTES:
        raise RequestAuthError("credential_invalid")
    return secret


def _canonical_bytes(
    *,
    version: str,
    algorithm: str,
    binding: EngineAuthBinding,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    payload_bytes: int,
    payload_sha256: str,
) -> bytes:
    payload = {
        "algorithm": algorithm,
        "audienceIdentity": binding.audience_identity,
        "bindingVersion": binding.version,
        "callerIdentity": binding.caller_identity,
        "credentialKey": binding.credential_key,
        "engine": binding.engine,
        "environment": binding.environment,
        "method": method,
        "nonce": nonce,
        "path": path,
        "payloadBytes": payload_bytes,
        "payloadSha256": payload_sha256,
        "timestamp": timestamp,
        "version": version,
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def sign_authenticated_request(
    credential: EngineCredential,
    *,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    payload: bytes,
) -> AuthenticatedRequestEnvelope:
    """Build one deterministic signed envelope without performing I/O."""

    secret = _credential_secret(credential)
    body = _require_exact_payload(payload)
    approved_method = _require_method(method)
    approved_path = _require_path(path)
    approved_timestamp = _require_timestamp(timestamp)
    approved_nonce = _require_nonce(nonce)
    payload_sha256 = hashlib.sha256(body).hexdigest()
    canonical = _canonical_bytes(
        version=REQUEST_AUTH_VERSION,
        algorithm=REQUEST_AUTH_ALGORITHM,
        binding=credential.binding,
        method=approved_method,
        path=approved_path,
        timestamp=approved_timestamp,
        nonce=approved_nonce,
        payload_bytes=len(body),
        payload_sha256=payload_sha256,
    )
    signature = hmac.new(secret, canonical, hashlib.sha256).hexdigest()

    binding = credential.binding
    return AuthenticatedRequestEnvelope(
        version=REQUEST_AUTH_VERSION,
        algorithm=REQUEST_AUTH_ALGORITHM,
        binding_version=binding.version,
        caller_identity=binding.caller_identity,
        engine=binding.engine,
        audience_identity=binding.audience_identity,
        environment=binding.environment,
        credential_key=binding.credential_key,
        method=approved_method,
        path=approved_path,
        timestamp=approved_timestamp,
        nonce=approved_nonce,
        payload_bytes=len(body),
        payload_sha256=payload_sha256,
        signature=signature,
    )


def _require_envelope_structure(envelope: AuthenticatedRequestEnvelope) -> None:
    if type(envelope) is not AuthenticatedRequestEnvelope:
        raise RequestAuthError("envelope_invalid")
    if envelope.version != REQUEST_AUTH_VERSION:
        raise RequestAuthError("request_auth_version_mismatch")
    if envelope.algorithm != REQUEST_AUTH_ALGORITHM:
        raise RequestAuthError("request_auth_algorithm_mismatch")
    _require_method(envelope.method)
    _require_path(envelope.path)
    _require_timestamp(envelope.timestamp)
    _require_nonce(envelope.nonce)
    if (
        type(envelope.payload_bytes) is not int
        or envelope.payload_bytes < 0
        or envelope.payload_bytes > MAX_AUTH_PAYLOAD_BYTES
    ):
        raise RequestAuthError("payload_size_invalid")
    _require_sha256_hex(envelope.payload_sha256, "payload_digest_invalid")
    _require_sha256_hex(envelope.signature, "signature_invalid")


def _require_binding_match(
    envelope: AuthenticatedRequestEnvelope,
    binding: EngineAuthBinding,
) -> None:
    checks = (
        (envelope.binding_version, binding.version, "binding_version_mismatch"),
        (envelope.caller_identity, binding.caller_identity, "caller_identity_mismatch"),
        (envelope.engine, binding.engine, "engine_identity_mismatch"),
        (
            envelope.audience_identity,
            binding.audience_identity,
            "audience_identity_mismatch",
        ),
        (envelope.environment, binding.environment, "environment_mismatch"),
        (envelope.credential_key, binding.credential_key, "credential_key_mismatch"),
    )
    for observed, expected, category in checks:
        if observed != expected:
            raise RequestAuthError(category)


def verify_authenticated_request(
    credential: EngineCredential,
    envelope: AuthenticatedRequestEnvelope,
    *,
    observed_method: str,
    observed_path: str,
    payload: bytes,
    now_seconds: int,
    replay_checker: ReplayChecker,
) -> None:
    """Verify the received request target/integrity before reserving its nonce."""

    secret = _credential_secret(credential)
    _require_envelope_structure(envelope)
    _require_binding_match(envelope, credential.binding)
    received_method = _require_observed_method(observed_method)
    received_path = _require_path(observed_path)
    if received_method != envelope.method:
        raise RequestAuthError("request_method_mismatch")
    if received_path != envelope.path:
        raise RequestAuthError("request_path_mismatch")
    body = _require_exact_payload(payload)
    now = _require_timestamp(now_seconds)

    if envelope.timestamp > now + MAX_FUTURE_SKEW_SECONDS:
        raise RequestAuthError("timestamp_in_future")
    if now - envelope.timestamp > MAX_REQUEST_AGE_SECONDS:
        raise RequestAuthError("timestamp_expired")

    if len(body) != envelope.payload_bytes:
        raise RequestAuthError("payload_size_mismatch")
    payload_sha256 = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(payload_sha256, envelope.payload_sha256):
        raise RequestAuthError("payload_digest_mismatch")

    canonical = _canonical_bytes(
        version=envelope.version,
        algorithm=envelope.algorithm,
        binding=credential.binding,
        method=envelope.method,
        path=envelope.path,
        timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        payload_bytes=envelope.payload_bytes,
        payload_sha256=envelope.payload_sha256,
    )
    expected_signature = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, envelope.signature):
        raise RequestAuthError("signature_invalid")

    if not callable(replay_checker):
        raise RequestAuthError("replay_check_unavailable")
    try:
        accepted = replay_checker(
            credential.binding,
            envelope.nonce,
            envelope.timestamp,
        )
    except Exception:
        raise RequestAuthError("replay_check_unavailable") from None
    if accepted is not True:
        raise RequestAuthError("replay_detected")
