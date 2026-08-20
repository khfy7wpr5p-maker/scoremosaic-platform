"""Bounded staging wire representation for one already-signed dispatch request.

This contract serializes only the transport metadata that cannot be reconstructed
from the trusted staging target: credential generation, timestamp, nonce, payload
length/digest, inner request HMAC, and generation HMAC. Caller/engine/audience,
environment, credential key, method, and path are reconstructed from the trusted
C.2-B target plus receiver-observed method/path.

The module does not sign, resolve credentials, send network traffic, register an
HTTP route, persist wire material, advance job state, or execute an engine.
Authentication proofs and raw body bytes are deliberately redacted from repr/safe
diagnostics even though the typed wire object necessarily carries them for a
future transport adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Sequence

from .authenticated_request import (
    AuthenticatedRequestEnvelope,
    REQUEST_AUTH_ALGORITHM,
    REQUEST_AUTH_VERSION,
)
from .credential_rotation import (
    GENERATION_AUTH_ALGORITHM,
    GENERATION_REQUEST_PROOF_VERSION,
    GenerationBoundRequest,
)
from .dispatch_identity import MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
from .dispatch_target import (
    DISPATCH_METHOD,
    DISPATCH_PATH,
    DispatchTargetError,
    EngineDispatchTarget,
    require_envelope_for_dispatch_target,
)


CONTROLLED_STAGING_DISPATCH_WIRE_VERSION = (
    "scoremosaic-controlled-staging-dispatch-wire-v1"
)
_HEADER_GENERATION = "x-scoremosaic-credential-generation"
_HEADER_TIMESTAMP = "x-scoremosaic-request-timestamp"
_HEADER_NONCE = "x-scoremosaic-request-nonce"
_HEADER_PAYLOAD_BYTES = "x-scoremosaic-payload-bytes"
_HEADER_PAYLOAD_SHA256 = "x-scoremosaic-payload-sha256"
_HEADER_REQUEST_SIGNATURE = "x-scoremosaic-request-signature"
_HEADER_GENERATION_SIGNATURE = "x-scoremosaic-generation-signature"
WIRE_HEADER_NAMES = (
    _HEADER_GENERATION,
    _HEADER_TIMESTAMP,
    _HEADER_NONCE,
    _HEADER_PAYLOAD_BYTES,
    _HEADER_PAYLOAD_SHA256,
    _HEADER_REQUEST_SIGNATURE,
    _HEADER_GENERATION_SIGNATURE,
)
_MAX_HEADER_VALUE_BYTES = 256
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_HEADER_NAME_RE = re.compile(r"[a-z0-9-]+\Z")


class ControlledStagingDispatchWireError(ValueError):
    """Stable fail-closed category for staging wire encoding/decoding."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require_ascii_text(value: object, *, category: str) -> str:
    if type(value) is not str or not value:
        raise ControlledStagingDispatchWireError(category)
    if value != value.strip():
        raise ControlledStagingDispatchWireError(category)
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        raise ControlledStagingDispatchWireError(category) from None
    if len(encoded) > _MAX_HEADER_VALUE_BYTES:
        raise ControlledStagingDispatchWireError(category)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ControlledStagingDispatchWireError(category)
    return value


def _require_target(value: object) -> EngineDispatchTarget:
    if type(value) is not EngineDispatchTarget or value.environment != "staging":
        raise ControlledStagingDispatchWireError("staging_wire_target_invalid")
    if value.method != DISPATCH_METHOD or value.path != DISPATCH_PATH:
        raise ControlledStagingDispatchWireError("staging_wire_target_invalid")
    return value


def _require_payload(value: object) -> bytes:
    if (
        type(value) is not bytes
        or not value
        or len(value) > MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
    ):
        raise ControlledStagingDispatchWireError("staging_wire_payload_invalid")
    return value


def _require_generation(value: object) -> str:
    if type(value) is not str or _GENERATION_RE.fullmatch(value) is None:
        raise ControlledStagingDispatchWireError("staging_wire_generation_invalid")
    return value


def _require_nonce(value: object) -> str:
    if type(value) is not str or _NONCE_RE.fullmatch(value) is None:
        raise ControlledStagingDispatchWireError("staging_wire_nonce_invalid")
    return value


def _require_sha256(value: object, *, category: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ControlledStagingDispatchWireError(category)
    return value


def _canonical_decimal(value: object, *, category: str, allow_zero: bool) -> str:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ControlledStagingDispatchWireError(category)
    return str(value)


def _parse_canonical_decimal(
    value: str,
    *,
    category: str,
    allow_zero: bool,
) -> int:
    observed = _require_ascii_text(value, category=category)
    if not observed.isdigit():
        raise ControlledStagingDispatchWireError(category)
    if len(observed) > 1 and observed.startswith("0"):
        raise ControlledStagingDispatchWireError(category)
    try:
        parsed = int(observed, 10)
    except ValueError:
        raise ControlledStagingDispatchWireError(category) from None
    if parsed < (0 if allow_zero else 1):
        raise ControlledStagingDispatchWireError(category)
    return parsed


def _require_request_shape(
    request: object,
    target: EngineDispatchTarget,
    payload: bytes,
) -> GenerationBoundRequest:
    if type(request) is not GenerationBoundRequest:
        raise ControlledStagingDispatchWireError("staging_wire_request_invalid")
    if (
        request.version != GENERATION_REQUEST_PROOF_VERSION
        or request.algorithm != GENERATION_AUTH_ALGORITHM
    ):
        raise ControlledStagingDispatchWireError("staging_wire_request_invalid")
    _require_generation(request.credential_generation_id)
    _require_sha256(
        request.generation_signature,
        category="staging_wire_generation_signature_invalid",
    )
    envelope = request.envelope
    if type(envelope) is not AuthenticatedRequestEnvelope:
        raise ControlledStagingDispatchWireError("staging_wire_request_invalid")
    if (
        envelope.version != REQUEST_AUTH_VERSION
        or envelope.algorithm != REQUEST_AUTH_ALGORITHM
    ):
        raise ControlledStagingDispatchWireError("staging_wire_request_invalid")
    try:
        require_envelope_for_dispatch_target(target, envelope)
    except DispatchTargetError:
        raise ControlledStagingDispatchWireError("staging_wire_target_mismatch") from None
    _require_nonce(envelope.nonce)
    _require_sha256(
        envelope.payload_sha256,
        category="staging_wire_payload_digest_invalid",
    )
    _require_sha256(
        envelope.signature,
        category="staging_wire_request_signature_invalid",
    )
    if type(envelope.timestamp) is not int or envelope.timestamp < 0:
        raise ControlledStagingDispatchWireError("staging_wire_timestamp_invalid")
    if (
        type(envelope.payload_bytes) is not int
        or envelope.payload_bytes != len(payload)
    ):
        raise ControlledStagingDispatchWireError("staging_wire_payload_size_mismatch")
    observed_digest = sha256(payload).hexdigest()
    if envelope.payload_sha256 != observed_digest:
        raise ControlledStagingDispatchWireError("staging_wire_payload_digest_mismatch")
    return request


def _normalize_headers(
    headers: object,
) -> dict[str, str]:
    if type(headers) not in {tuple, list}:
        raise ControlledStagingDispatchWireError("staging_wire_headers_invalid")
    if len(headers) != len(WIRE_HEADER_NAMES):
        raise ControlledStagingDispatchWireError("staging_wire_headers_invalid")
    normalized: dict[str, str] = {}
    for pair in headers:
        if type(pair) is not tuple or len(pair) != 2:
            raise ControlledStagingDispatchWireError("staging_wire_headers_invalid")
        name, value = pair
        if type(name) is not str or type(value) is not str:
            raise ControlledStagingDispatchWireError("staging_wire_headers_invalid")
        try:
            name_ascii = name.encode("ascii")
        except UnicodeEncodeError:
            raise ControlledStagingDispatchWireError("staging_wire_headers_invalid") from None
        if (
            not name_ascii
            or len(name_ascii) > 128
            or name != name.strip()
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name)
        ):
            raise ControlledStagingDispatchWireError("staging_wire_headers_invalid")
        lowered = name.lower()
        if _HEADER_NAME_RE.fullmatch(lowered) is None:
            raise ControlledStagingDispatchWireError("staging_wire_headers_invalid")
        if lowered not in WIRE_HEADER_NAMES or lowered in normalized:
            raise ControlledStagingDispatchWireError("staging_wire_headers_invalid")
        normalized[lowered] = _require_ascii_text(
            value,
            category="staging_wire_header_value_invalid",
        )
    if frozenset(normalized) != frozenset(WIRE_HEADER_NAMES):
        raise ControlledStagingDispatchWireError("staging_wire_headers_invalid")
    return normalized


@dataclass(frozen=True, slots=True, repr=False)
class ControlledStagingDispatchWireRequest:
    version: str
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def __post_init__(self) -> None:
        if (
            self.version != CONTROLLED_STAGING_DISPATCH_WIRE_VERSION
            or type(self.headers) is not tuple
            or type(self.body) is not bytes
            or not self.body
            or len(self.body) > MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
        ):
            raise ControlledStagingDispatchWireError("staging_wire_result_invalid")
        _normalize_headers(self.headers)

    def __repr__(self) -> str:
        return (
            "ControlledStagingDispatchWireRequest("
            f"version={self.version!r}, header_count={len(self.headers)!r}, "
            f"body_bytes={len(self.body)!r}, authentication_proofs=<redacted>)"
        )

    @property
    def contains_authentication_proof(self) -> bool:
        return True

    @property
    def network_send_allowed(self) -> bool:
        return False

    @property
    def persistence_allowed(self) -> bool:
        return False

    @property
    def logging_allowed(self) -> bool:
        return False

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "environment": "staging",
            "headerCount": len(self.headers),
            "bodyBytes": len(self.body),
            "bodySha256": sha256(self.body).hexdigest(),
            "containsAuthenticationProof": True,
            "authenticationProofRedacted": True,
            "networkSendAllowed": False,
            "persistenceAllowed": False,
            "loggingAllowed": False,
            "jobStateMutationAllowed": False,
            "engineExecutionAllowed": False,
        }


def serialize_controlled_staging_dispatch_wire(
    *,
    target: EngineDispatchTarget,
    request: GenerationBoundRequest,
    payload: bytes,
) -> ControlledStagingDispatchWireRequest:
    """Serialize one already-signed staging request without performing I/O."""

    checked_target = _require_target(target)
    checked_payload = _require_payload(payload)
    checked_request = _require_request_shape(request, checked_target, checked_payload)
    envelope = checked_request.envelope
    headers = (
        (_HEADER_GENERATION, checked_request.credential_generation_id),
        (_HEADER_TIMESTAMP, _canonical_decimal(
            envelope.timestamp,
            category="staging_wire_timestamp_invalid",
            allow_zero=True,
        )),
        (_HEADER_NONCE, envelope.nonce),
        (_HEADER_PAYLOAD_BYTES, _canonical_decimal(
            envelope.payload_bytes,
            category="staging_wire_payload_size_invalid",
            allow_zero=False,
        )),
        (_HEADER_PAYLOAD_SHA256, envelope.payload_sha256),
        (_HEADER_REQUEST_SIGNATURE, envelope.signature),
        (_HEADER_GENERATION_SIGNATURE, checked_request.generation_signature),
    )
    return ControlledStagingDispatchWireRequest(
        version=CONTROLLED_STAGING_DISPATCH_WIRE_VERSION,
        headers=headers,
        body=bytes(checked_payload),
    )


def parse_controlled_staging_dispatch_wire(
    *,
    target: EngineDispatchTarget,
    headers: Sequence[tuple[str, str]],
    body: bytes,
    observed_method: str,
    observed_path: str,
) -> GenerationBoundRequest:
    """Reconstruct one signed request from bounded headers plus observed target."""

    checked_target = _require_target(target)
    checked_body = _require_payload(body)
    if type(observed_method) is not str or type(observed_path) is not str:
        raise ControlledStagingDispatchWireError("staging_wire_observed_target_invalid")
    normalized = _normalize_headers(headers)

    generation_id = _require_generation(normalized[_HEADER_GENERATION])
    timestamp = _parse_canonical_decimal(
        normalized[_HEADER_TIMESTAMP],
        category="staging_wire_timestamp_invalid",
        allow_zero=True,
    )
    nonce = _require_nonce(normalized[_HEADER_NONCE])
    payload_bytes = _parse_canonical_decimal(
        normalized[_HEADER_PAYLOAD_BYTES],
        category="staging_wire_payload_size_invalid",
        allow_zero=False,
    )
    if payload_bytes > MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES:
        raise ControlledStagingDispatchWireError("staging_wire_payload_size_invalid")
    payload_sha256 = _require_sha256(
        normalized[_HEADER_PAYLOAD_SHA256],
        category="staging_wire_payload_digest_invalid",
    )
    request_signature = _require_sha256(
        normalized[_HEADER_REQUEST_SIGNATURE],
        category="staging_wire_request_signature_invalid",
    )
    generation_signature = _require_sha256(
        normalized[_HEADER_GENERATION_SIGNATURE],
        category="staging_wire_generation_signature_invalid",
    )
    if payload_bytes != len(checked_body):
        raise ControlledStagingDispatchWireError("staging_wire_payload_size_mismatch")
    if payload_sha256 != sha256(checked_body).hexdigest():
        raise ControlledStagingDispatchWireError("staging_wire_payload_digest_mismatch")

    envelope = AuthenticatedRequestEnvelope(
        version=REQUEST_AUTH_VERSION,
        algorithm=REQUEST_AUTH_ALGORITHM,
        binding_version=checked_target.binding_version,
        caller_identity=checked_target.caller_identity,
        engine=checked_target.engine,
        audience_identity=checked_target.audience_identity,
        environment=checked_target.environment,
        credential_key=checked_target.credential_key,
        method=observed_method,
        path=observed_path,
        timestamp=timestamp,
        nonce=nonce,
        payload_bytes=payload_bytes,
        payload_sha256=payload_sha256,
        signature=request_signature,
    )
    try:
        require_envelope_for_dispatch_target(checked_target, envelope)
    except DispatchTargetError:
        raise ControlledStagingDispatchWireError("staging_wire_observed_target_mismatch") from None

    return GenerationBoundRequest(
        version=GENERATION_REQUEST_PROOF_VERSION,
        algorithm=GENERATION_AUTH_ALGORITHM,
        credential_generation_id=generation_id,
        envelope=envelope,
        generation_signature=generation_signature,
    )
