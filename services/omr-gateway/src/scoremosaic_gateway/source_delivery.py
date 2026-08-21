"""Authenticated bounded source-delivery contract for Stage 5-A1.

This module prepares one exact immutable source body for a private engine after
Stage 4 dispatch has been authenticated.  It validates and signs evidence only:
no network I/O, engine execution, result persistence, job mutation, retry, or
production activation is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import new as hmac_new
import hmac
import json
import re
from typing import Callable

from .config import EngineEndpoint
from .dispatch_input_capsule import (
    DispatchInputCapsule,
    DispatchInputCapsuleError,
    verify_dispatch_input_capsule,
)
from .dispatch_target import APPROVED_ENGINE_ORIGINS
from .service_auth import (
    CALLER_SERVICE_IDENTITY,
    ENGINE_SERVICE_IDENTITIES,
    MAX_CREDENTIAL_BYTES,
    MIN_CREDENTIAL_BYTES,
)

SOURCE_DELIVERY_VERSION = "scoremosaic-source-delivery-v1"
SOURCE_DELIVERY_ALGORITHM = "hmac-sha256"
SOURCE_DELIVERY_METHOD = "POST"
SOURCE_DELIVERY_PATH = "/internal/source"
SOURCE_DELIVERY_ENVIRONMENT = "staging"
SOURCE_DELIVERY_MAX_AGE_SECONDS = 60
SOURCE_DELIVERY_MAX_FUTURE_SKEW_SECONDS = 30
SOURCE_DELIVERY_MAX_BYTES = 100 * 1024 * 1024
_SOURCE_SIGNATURE_DOMAIN = b"scoremosaic-source-delivery-signature-v1"

_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_ALLOWED_MEDIA_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})

SOURCE_DELIVERY_HEADER_NAMES = (
    "x-scoremosaic-source-generation",
    "x-scoremosaic-source-timestamp",
    "x-scoremosaic-source-nonce",
    "x-scoremosaic-source-job",
    "x-scoremosaic-source-run",
    "x-scoremosaic-source-dispatch-sha256",
    "x-scoremosaic-source-artifact",
    "x-scoremosaic-source-bytes",
    "x-scoremosaic-source-sha256",
    "x-scoremosaic-source-media-type",
    "x-scoremosaic-source-signature",
)


class SourceDeliveryError(ValueError):
    """Stable bounded Stage 5-A source-delivery failure category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class SourceDeliveryBinding:
    version: str
    environment: str
    caller_identity: str
    engine: str
    audience_identity: str
    credential_key: str
    origin: str
    method: str
    path: str

    def as_safe_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "environment": self.environment,
            "callerIdentity": self.caller_identity,
            "engine": self.engine,
            "audienceIdentity": self.audience_identity,
            "credentialKey": self.credential_key,
            "origin": self.origin,
            "method": self.method,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True, repr=False)
class SourceDeliveryCredential:
    binding: SourceDeliveryBinding
    generation_id: str
    _secret: bytes = field(repr=False)

    def __repr__(self) -> str:
        return (
            "SourceDeliveryCredential("
            f"engine={self.binding.engine!r}, generation_id={self.generation_id!r}, "
            "secret=<redacted>)"
        )

    def secret_bytes_for_signing(self) -> bytes:
        return bytes(self._secret)


@dataclass(frozen=True, slots=True, repr=False)
class SourceDeliveryRequest:
    version: str
    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    source_artifact_id: str
    source_size_bytes: int
    source_sha256: str
    source_media_type: str
    credential_generation_id: str
    timestamp: int
    nonce_sha256: str
    metadata_sha256: str
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    body: bytes = field(repr=False)
    signature: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.version != SOURCE_DELIVERY_VERSION
            or self.engine not in ENGINE_SERVICE_IDENTITIES
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.source_size_bytes) is not int
            or not 1 <= self.source_size_bytes <= SOURCE_DELIVERY_MAX_BYTES
            or _SHA256_RE.fullmatch(self.source_sha256) is None
            or self.source_media_type not in _ALLOWED_MEDIA_TYPES
            or _GENERATION_RE.fullmatch(self.credential_generation_id) is None
            or type(self.timestamp) is not int
            or self.timestamp < 0
            or _SHA256_RE.fullmatch(self.nonce_sha256) is None
            or _SHA256_RE.fullmatch(self.metadata_sha256) is None
            or type(self.headers) is not tuple
            or tuple(name for name, _ in self.headers) != SOURCE_DELIVERY_HEADER_NAMES
            or type(self.body) is not bytes
            or len(self.body) != self.source_size_bytes
            or not hmac.compare_digest(sha256(self.body).hexdigest(), self.source_sha256)
            or _SHA256_RE.fullmatch(self.signature) is None
        ):
            raise SourceDeliveryError("source_delivery_result_invalid")

    def __repr__(self) -> str:
        return (
            "SourceDeliveryRequest("
            f"engine={self.engine!r}, job_id={self.job_id!r}, run_id={self.run_id!r}, "
            f"source_size_bytes={self.source_size_bytes!r}, source_sha256={self.source_sha256!r}, "
            "headers=<redacted>, body=<redacted>, signature=<redacted>)"
        )

    @property
    def network_delivery_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    @property
    def result_persistence_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "environment": SOURCE_DELIVERY_ENVIRONMENT,
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSizeBytes": self.source_size_bytes,
            "sourceSha256": self.source_sha256,
            "sourceMediaType": self.source_media_type,
            "credentialGenerationId": self.credential_generation_id,
            "timestamp": self.timestamp,
            "nonceSha256": self.nonce_sha256,
            "metadataSha256": self.metadata_sha256,
            "signaturePresent": True,
            "networkDeliveryAllowed": False,
            "engineExecutionAllowed": False,
            "resultPersistenceAllowed": False,
            "retryAllowed": False,
        }


SourceCredentialResolver = Callable[[str, str], bytes | bytearray | memoryview | None]


def _credential_key(*, engine: str, audience_identity: str) -> str:
    return ":".join(
        (
            SOURCE_DELIVERY_VERSION,
            SOURCE_DELIVERY_ENVIRONMENT,
            CALLER_SERVICE_IDENTITY,
            engine,
            audience_identity,
        )
    )


def build_source_delivery_binding(endpoint: EngineEndpoint) -> SourceDeliveryBinding:
    if type(endpoint) is not EngineEndpoint or type(endpoint.name) is not str:
        raise SourceDeliveryError("source_delivery_endpoint_invalid")
    audience = ENGINE_SERVICE_IDENTITIES.get(endpoint.name)
    expected_origin = APPROVED_ENGINE_ORIGINS[SOURCE_DELIVERY_ENVIRONMENT].get(endpoint.name)
    if (
        audience is None
        or expected_origin is None
        or type(endpoint.base_url) is not str
        or endpoint.base_url != expected_origin
    ):
        raise SourceDeliveryError("source_delivery_endpoint_invalid")
    return SourceDeliveryBinding(
        version=SOURCE_DELIVERY_VERSION,
        environment=SOURCE_DELIVERY_ENVIRONMENT,
        caller_identity=CALLER_SERVICE_IDENTITY,
        engine=endpoint.name,
        audience_identity=audience,
        credential_key=_credential_key(engine=endpoint.name, audience_identity=audience),
        origin=expected_origin,
        method=SOURCE_DELIVERY_METHOD,
        path=SOURCE_DELIVERY_PATH,
    )


def resolve_source_delivery_credential(
    binding: SourceDeliveryBinding,
    *,
    generation_id: str,
    resolver: SourceCredentialResolver,
) -> SourceDeliveryCredential:
    if type(binding) is not SourceDeliveryBinding:
        raise SourceDeliveryError("source_delivery_binding_invalid")
    endpoint = EngineEndpoint(binding.engine, binding.origin)
    expected = build_source_delivery_binding(endpoint)
    if binding != expected:
        raise SourceDeliveryError("source_delivery_binding_invalid")
    if type(generation_id) is not str or _GENERATION_RE.fullmatch(generation_id) is None:
        raise SourceDeliveryError("source_delivery_generation_invalid")
    if not callable(resolver):
        raise SourceDeliveryError("source_delivery_credential_unavailable")
    try:
        raw = resolver(binding.credential_key, generation_id)
    except Exception:
        raise SourceDeliveryError("source_delivery_credential_unavailable") from None
    if raw is None or type(raw) not in (bytes, bytearray, memoryview):
        raise SourceDeliveryError("source_delivery_credential_unavailable")
    try:
        raw_size = raw.nbytes if type(raw) is memoryview else len(raw)
        secret = bytes(raw)
    except (BufferError, TypeError, ValueError):
        raise SourceDeliveryError("source_delivery_credential_unavailable") from None
    if not MIN_CREDENTIAL_BYTES <= raw_size <= MAX_CREDENTIAL_BYTES:
        raise SourceDeliveryError("source_delivery_credential_unavailable")
    return SourceDeliveryCredential(binding=binding, generation_id=generation_id, _secret=secret)


def _canonical_metadata(
    *,
    binding: SourceDeliveryBinding,
    generation_id: str,
    timestamp: int,
    nonce: str,
    capsule: DispatchInputCapsule,
) -> bytes:
    identity = capsule.dispatch_identity
    value = {
        "version": SOURCE_DELIVERY_VERSION,
        "algorithm": SOURCE_DELIVERY_ALGORITHM,
        "environment": SOURCE_DELIVERY_ENVIRONMENT,
        "callerIdentity": binding.caller_identity,
        "engine": binding.engine,
        "audienceIdentity": binding.audience_identity,
        "credentialKey": binding.credential_key,
        "origin": binding.origin,
        "method": SOURCE_DELIVERY_METHOD,
        "path": SOURCE_DELIVERY_PATH,
        "credentialGenerationId": generation_id,
        "timestamp": timestamp,
        "nonce": nonce,
        "jobId": identity.job_id,
        "runId": identity.run_id,
        "dispatchIdentitySha256": identity.identity_sha256,
        "sourceArtifactId": identity.source_artifact_id,
        "sourceBytes": capsule.source_size_bytes,
        "sourceSha256": capsule.source_sha256,
        "sourceMediaType": capsule.source_media_type,
    }
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def build_source_delivery_request(
    *,
    capsule: DispatchInputCapsule,
    credential: SourceDeliveryCredential,
    timestamp: int,
    nonce: str,
) -> SourceDeliveryRequest:
    if type(capsule) is not DispatchInputCapsule:
        raise SourceDeliveryError("source_delivery_capsule_invalid")
    try:
        verify_dispatch_input_capsule(capsule)
    except DispatchInputCapsuleError:
        raise SourceDeliveryError("source_delivery_capsule_invalid") from None
    if type(credential) is not SourceDeliveryCredential:
        raise SourceDeliveryError("source_delivery_credential_invalid")
    binding = credential.binding
    expected_binding = build_source_delivery_binding(
        EngineEndpoint(binding.engine, binding.origin)
    )
    if binding != expected_binding or binding.engine != capsule.dispatch_identity.engine:
        raise SourceDeliveryError("source_delivery_credential_invalid")
    if type(timestamp) is not int or timestamp < 0:
        raise SourceDeliveryError("source_delivery_timestamp_invalid")
    if type(nonce) is not str or _NONCE_RE.fullmatch(nonce) is None:
        raise SourceDeliveryError("source_delivery_nonce_invalid")
    if len(capsule.source_bytes) > SOURCE_DELIVERY_MAX_BYTES:
        raise SourceDeliveryError("source_delivery_source_too_large")

    metadata = _canonical_metadata(
        binding=binding,
        generation_id=credential.generation_id,
        timestamp=timestamp,
        nonce=nonce,
        capsule=capsule,
    )
    signature_message = b"\0".join(
        (_SOURCE_SIGNATURE_DOMAIN, metadata, capsule.source_sha256.encode("ascii"))
    )
    signature = hmac_new(
        credential.secret_bytes_for_signing(),
        signature_message,
        sha256,
    ).hexdigest()
    identity = capsule.dispatch_identity
    headers = (
        ("x-scoremosaic-source-generation", credential.generation_id),
        ("x-scoremosaic-source-timestamp", str(timestamp)),
        ("x-scoremosaic-source-nonce", nonce),
        ("x-scoremosaic-source-job", identity.job_id),
        ("x-scoremosaic-source-run", identity.run_id),
        ("x-scoremosaic-source-dispatch-sha256", identity.identity_sha256),
        ("x-scoremosaic-source-artifact", identity.source_artifact_id),
        ("x-scoremosaic-source-bytes", str(capsule.source_size_bytes)),
        ("x-scoremosaic-source-sha256", capsule.source_sha256),
        ("x-scoremosaic-source-media-type", capsule.source_media_type),
        ("x-scoremosaic-source-signature", signature),
    )
    return SourceDeliveryRequest(
        version=SOURCE_DELIVERY_VERSION,
        engine=identity.engine,
        job_id=identity.job_id,
        run_id=identity.run_id,
        dispatch_identity_sha256=identity.identity_sha256,
        source_artifact_id=identity.source_artifact_id,
        source_size_bytes=capsule.source_size_bytes,
        source_sha256=capsule.source_sha256,
        source_media_type=capsule.source_media_type,
        credential_generation_id=credential.generation_id,
        timestamp=timestamp,
        nonce_sha256=sha256(nonce.encode("ascii")).hexdigest(),
        metadata_sha256=sha256(metadata).hexdigest(),
        headers=headers,
        body=bytes(capsule.source_bytes),
        signature=signature,
    )
