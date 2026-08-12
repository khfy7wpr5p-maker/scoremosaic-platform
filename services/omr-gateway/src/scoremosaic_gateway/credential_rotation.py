"""Credential-generation, bounded rotation, and replay semantics for Gate C.2-D.

This module is deliberately additive over the completed C.1/C.2-A/C.2-C
foundations. It does not register routes, send network requests, persist replay
state, provision credentials, or enable orchestration. It binds an explicit
non-secret credential generation to already-authenticated request/result proofs
without changing the completed inner contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Any, Callable

from .authenticated_request import (
    AuthenticatedRequestEnvelope,
    MAX_REQUEST_AGE_SECONDS,
    RequestAuthError,
    sign_authenticated_request,
    verify_authenticated_request,
)
from .dispatch_identity import (
    DispatchIdentityBinding,
    DispatchResultIdentity,
    build_dispatch_result_identity,
    require_dispatch_result_identity,
)
from .service_auth import (
    EngineAuthBinding,
    EngineCredential,
    MAX_CREDENTIAL_BYTES,
    MIN_CREDENTIAL_BYTES,
    ServiceAuthError,
    _validated_resolver_key,
    resolve_engine_credential,
)

CREDENTIAL_ROTATION_CONTRACT_VERSION = "scoremosaic-s2s-rotation-v1"
GENERATION_REQUEST_PROOF_VERSION = "scoremosaic-s2s-request-generation-v1"
GENERATION_RESULT_PROOF_VERSION = "scoremosaic-dispatch-result-generation-v1"
GENERATION_AUTH_ALGORITHM = "hmac-sha256"
MAX_ROTATION_GRACE_SECONDS = 300
MIN_REPLAY_RESERVATION_SECONDS = MAX_REQUEST_AGE_SECONDS + 1
MAX_REPLAY_RESERVATION_SECONDS = 600
NONCE_HEX_LENGTH = 32
SHA256_HEX_LENGTH = 64

_GENERATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_LOWER_HEX_RE = re.compile(r"^[0-9a-f]+$")


class CredentialRotationError(ValueError):
    """Safe bounded Gate C.2-D contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True, repr=False)
class GenerationCredential:
    """One exact non-secret generation label plus one opaque C.1 credential."""

    generation_id: str
    credential: EngineCredential

    @property
    def binding(self) -> EngineAuthBinding:
        return self.credential.binding

    def secret_bytes_for_transport(self) -> bytes:
        return self.credential.secret_bytes_for_transport()

    def __repr__(self) -> str:
        return (
            "GenerationCredential("
            f"generation_id={self.generation_id!r}, binding={self.binding!r}, "
            "secret=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class CredentialRotationSet:
    """At most one current and one bounded previous credential generation."""

    version: str
    current: GenerationCredential
    previous: GenerationCredential | None
    rotation_started_at: int
    previous_valid_until: int | None

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "binding": self.current.binding.as_safe_dict(),
            "currentGenerationId": self.current.generation_id,
            "previousGenerationId": (
                None if self.previous is None else self.previous.generation_id
            ),
            "rotationStartedAt": self.rotation_started_at,
            "previousValidUntil": self.previous_valid_until,
        }


@dataclass(frozen=True, slots=True)
class ReplayReservation:
    """Persistence-neutral replay reservation identity and expiry evidence."""

    version: str
    key: str
    expires_at: int

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "key": self.key,
            "expiresAt": self.expires_at,
        }


@dataclass(frozen=True, slots=True, repr=False)
class GenerationBoundRequest:
    """C.2-D proof binding a generation ID to one complete C.2-A envelope."""

    version: str
    algorithm: str
    credential_generation_id: str
    envelope: AuthenticatedRequestEnvelope
    generation_signature: str

    def __repr__(self) -> str:
        return (
            "GenerationBoundRequest("
            f"version={self.version!r}, algorithm={self.algorithm!r}, "
            f"credential_generation_id={self.credential_generation_id!r}, "
            f"envelope={self.envelope!r}, generation_signature=<redacted>)"
        )

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "algorithm": self.algorithm,
            "credentialGenerationId": self.credential_generation_id,
            "envelope": self.envelope.as_safe_dict(),
            "generationSignaturePresent": bool(self.generation_signature),
        }


@dataclass(frozen=True, slots=True, repr=False)
class GenerationBoundResult:
    """C.2-D proof binding a generation ID to one complete C.2-C result claim."""

    version: str
    algorithm: str
    credential_generation_id: str
    result: DispatchResultIdentity
    generation_signature: str

    def __repr__(self) -> str:
        return (
            "GenerationBoundResult("
            f"version={self.version!r}, algorithm={self.algorithm!r}, "
            f"credential_generation_id={self.credential_generation_id!r}, "
            f"result={self.result!r}, generation_signature=<redacted>)"
        )

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "algorithm": self.algorithm,
            "credentialGenerationId": self.credential_generation_id,
            "result": self.result.as_safe_dict(),
            "generationSignaturePresent": bool(self.generation_signature),
        }


GenerationCredentialResolver = Callable[
    [str, str],
    bytes | bytearray | memoryview | None,
]
GenerationReplayChecker = Callable[[EngineAuthBinding, str, str, int], bool]


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _require_generation_id(generation_id: Any) -> str:
    if type(generation_id) is not str or _GENERATION_ID_RE.fullmatch(generation_id) is None:
        raise CredentialRotationError("credential_generation_invalid")
    return generation_id


def _require_timestamp(value: Any, category: str) -> int:
    if type(value) is not int or value < 0:
        raise CredentialRotationError(category)
    return value


def _require_nonce(nonce: Any) -> str:
    if (
        type(nonce) is not str
        or len(nonce) != NONCE_HEX_LENGTH
        or _LOWER_HEX_RE.fullmatch(nonce) is None
    ):
        raise CredentialRotationError("nonce_invalid")
    return nonce


def _require_sha256_hex(value: Any, category: str) -> str:
    if (
        type(value) is not str
        or len(value) != SHA256_HEX_LENGTH
        or _LOWER_HEX_RE.fullmatch(value) is None
    ):
        raise CredentialRotationError(category)
    return value


def _validated_generation_credential(
    value: Any,
    *,
    category: str = "generation_credential_invalid",
) -> GenerationCredential:
    if type(value) is not GenerationCredential:
        raise CredentialRotationError(category)
    _require_generation_id(value.generation_id)
    if type(value.credential) is not EngineCredential:
        raise CredentialRotationError(category)
    try:
        _validated_resolver_key(value.binding)
    except ServiceAuthError:
        raise CredentialRotationError("credential_binding_invalid") from None
    secret = value.secret_bytes_for_transport()
    if type(secret) is not bytes or not MIN_CREDENTIAL_BYTES <= len(secret) <= MAX_CREDENTIAL_BYTES:
        raise CredentialRotationError("credential_invalid")
    return value


def _secret(value: GenerationCredential) -> bytes:
    validated = _validated_generation_credential(value)
    return validated.secret_bytes_for_transport()


def resolve_engine_credential_generation(
    binding: EngineAuthBinding,
    generation_id: str,
    resolver: GenerationCredentialResolver,
) -> GenerationCredential:
    """Resolve exactly one logical binding + generation without secret fallback."""

    generation = _require_generation_id(generation_id)
    if not callable(resolver):
        raise CredentialRotationError("credential_resolver_invalid")

    def scoped_resolver(credential_key: str):
        return resolver(credential_key, generation)

    try:
        credential = resolve_engine_credential(binding, scoped_resolver)
    except ServiceAuthError as exc:
        raise CredentialRotationError(exc.category) from None
    return GenerationCredential(generation_id=generation, credential=credential)


def build_rotation_set(
    *,
    current: GenerationCredential,
    previous: GenerationCredential | None,
    rotation_started_at: int,
    previous_valid_until: int | None,
) -> CredentialRotationSet:
    """Build one active rotation set with at most one bounded previous generation."""

    current_generation = _validated_generation_credential(current)
    started_at = _require_timestamp(rotation_started_at, "rotation_started_at_invalid")

    if previous is None:
        if previous_valid_until is not None:
            raise CredentialRotationError("rotation_grace_invalid")
        result = CredentialRotationSet(
            version=CREDENTIAL_ROTATION_CONTRACT_VERSION,
            current=current_generation,
            previous=None,
            rotation_started_at=started_at,
            previous_valid_until=None,
        )
        return result

    previous_generation = _validated_generation_credential(previous)
    if previous_generation.binding != current_generation.binding:
        raise CredentialRotationError("rotation_binding_mismatch")
    if previous_generation.generation_id == current_generation.generation_id:
        raise CredentialRotationError("credential_generation_collision")
    if hmac.compare_digest(_secret(current_generation), _secret(previous_generation)):
        raise CredentialRotationError("credential_material_reused")
    if previous_valid_until is None:
        raise CredentialRotationError("rotation_grace_invalid")
    valid_until = _require_timestamp(previous_valid_until, "rotation_grace_invalid")
    if valid_until <= started_at:
        raise CredentialRotationError("rotation_grace_invalid")
    if valid_until - started_at > MAX_ROTATION_GRACE_SECONDS:
        raise CredentialRotationError("rotation_grace_too_large")

    return CredentialRotationSet(
        version=CREDENTIAL_ROTATION_CONTRACT_VERSION,
        current=current_generation,
        previous=previous_generation,
        rotation_started_at=started_at,
        previous_valid_until=valid_until,
    )


def _require_rotation_set(rotation: Any) -> CredentialRotationSet:
    if type(rotation) is not CredentialRotationSet:
        raise CredentialRotationError("rotation_set_invalid")
    if rotation.version != CREDENTIAL_ROTATION_CONTRACT_VERSION:
        raise CredentialRotationError("rotation_contract_version_mismatch")
    return build_rotation_set(
        current=rotation.current,
        previous=rotation.previous,
        rotation_started_at=rotation.rotation_started_at,
        previous_valid_until=rotation.previous_valid_until,
    )


def select_signing_credential(
    rotation: CredentialRotationSet,
    *,
    now_seconds: int,
) -> GenerationCredential:
    """New proofs always use only the current generation after activation."""

    active = _require_rotation_set(rotation)
    now = _require_timestamp(now_seconds, "now_invalid")
    if now < active.rotation_started_at:
        raise CredentialRotationError("rotation_not_active")
    return active.current


def select_verification_credential(
    rotation: CredentialRotationSet,
    generation_id: str,
    *,
    now_seconds: int,
) -> GenerationCredential:
    """Select exactly the labeled generation; never try a list of secrets."""

    active = _require_rotation_set(rotation)
    generation = _require_generation_id(generation_id)
    now = _require_timestamp(now_seconds, "now_invalid")
    if now < active.rotation_started_at:
        raise CredentialRotationError("rotation_not_active")
    if generation == active.current.generation_id:
        return active.current
    if active.previous is not None and generation == active.previous.generation_id:
        if active.previous_valid_until is None or now >= active.previous_valid_until:
            raise CredentialRotationError("credential_generation_expired")
        return active.previous
    raise CredentialRotationError("credential_generation_unknown")


def build_replay_reservation(
    binding: EngineAuthBinding,
    generation_id: str,
    nonce: str,
    *,
    request_timestamp: int,
    max_request_age_seconds: int,
) -> ReplayReservation:
    """Build persistence-neutral generation-scoped nonce identity plus expiry."""

    try:
        _validated_resolver_key(binding)
    except ServiceAuthError:
        raise CredentialRotationError("credential_binding_invalid") from None
    generation = _require_generation_id(generation_id)
    accepted_nonce = _require_nonce(nonce)
    timestamp = _require_timestamp(request_timestamp, "timestamp_invalid")
    if (
        type(max_request_age_seconds) is not int
        or not 1 <= max_request_age_seconds <= MAX_REPLAY_RESERVATION_SECONDS
    ):
        raise CredentialRotationError("replay_reservation_ttl_invalid")
    if max_request_age_seconds < MIN_REPLAY_RESERVATION_SECONDS:
        raise CredentialRotationError("replay_reservation_ttl_too_short")

    key_payload = {
        "version": CREDENTIAL_ROTATION_CONTRACT_VERSION,
        "bindingVersion": binding.version,
        "callerIdentity": binding.caller_identity,
        "engine": binding.engine,
        "audienceIdentity": binding.audience_identity,
        "environment": binding.environment,
        "credentialKey": binding.credential_key,
        "credentialGenerationId": generation,
        "nonce": accepted_nonce,
    }
    return ReplayReservation(
        version=CREDENTIAL_ROTATION_CONTRACT_VERSION,
        key=hashlib.sha256(_canonical_json(key_payload)).hexdigest(),
        expires_at=timestamp + max_request_age_seconds,
    )


def _request_envelope_dict(envelope: AuthenticatedRequestEnvelope) -> dict[str, object]:
    if type(envelope) is not AuthenticatedRequestEnvelope:
        raise CredentialRotationError("request_envelope_invalid")
    return {
        "version": envelope.version,
        "algorithm": envelope.algorithm,
        "bindingVersion": envelope.binding_version,
        "callerIdentity": envelope.caller_identity,
        "engine": envelope.engine,
        "audienceIdentity": envelope.audience_identity,
        "environment": envelope.environment,
        "credentialKey": envelope.credential_key,
        "method": envelope.method,
        "path": envelope.path,
        "timestamp": envelope.timestamp,
        "nonce": envelope.nonce,
        "payloadBytes": envelope.payload_bytes,
        "payloadSha256": envelope.payload_sha256,
        "signature": envelope.signature,
    }


def _generation_request_auth_bytes(
    generation_id: str,
    envelope: AuthenticatedRequestEnvelope,
) -> bytes:
    return _canonical_json(
        {
            "version": GENERATION_REQUEST_PROOF_VERSION,
            "algorithm": GENERATION_AUTH_ALGORITHM,
            "credentialGenerationId": generation_id,
            "requestEnvelope": _request_envelope_dict(envelope),
        }
    )


def _require_generation_bound_request(request: Any) -> GenerationBoundRequest:
    if type(request) is not GenerationBoundRequest:
        raise CredentialRotationError("generation_request_invalid")
    if request.version != GENERATION_REQUEST_PROOF_VERSION:
        raise CredentialRotationError("generation_request_version_mismatch")
    if request.algorithm != GENERATION_AUTH_ALGORITHM:
        raise CredentialRotationError("generation_auth_algorithm_mismatch")
    _require_generation_id(request.credential_generation_id)
    _request_envelope_dict(request.envelope)
    _require_sha256_hex(
        request.generation_signature,
        "generation_request_signature_invalid",
    )
    return request


def sign_rotation_authenticated_request(
    rotation: CredentialRotationSet,
    *,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    payload: bytes,
    now_seconds: int,
) -> GenerationBoundRequest:
    """Sign one C.2-A request with the current generation and bind its generation."""

    selected = select_signing_credential(rotation, now_seconds=now_seconds)
    envelope = sign_authenticated_request(
        selected.credential,
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        payload=payload,
    )
    auth_bytes = _generation_request_auth_bytes(selected.generation_id, envelope)
    signature = hmac.new(_secret(selected), auth_bytes, hashlib.sha256).hexdigest()
    return GenerationBoundRequest(
        version=GENERATION_REQUEST_PROOF_VERSION,
        algorithm=GENERATION_AUTH_ALGORITHM,
        credential_generation_id=selected.generation_id,
        envelope=envelope,
        generation_signature=signature,
    )


def verify_rotation_authenticated_request(
    rotation: CredentialRotationSet,
    request: GenerationBoundRequest,
    *,
    observed_method: str,
    observed_path: str,
    payload: bytes,
    now_seconds: int,
    replay_checker: GenerationReplayChecker,
) -> GenerationCredential:
    """Verify generation proof before C.2-A can reserve replay state."""

    observed = _require_generation_bound_request(request)
    selected = select_verification_credential(
        rotation,
        observed.credential_generation_id,
        now_seconds=now_seconds,
    )
    auth_bytes = _generation_request_auth_bytes(
        observed.credential_generation_id,
        observed.envelope,
    )
    expected_signature = hmac.new(
        _secret(selected),
        auth_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(observed.generation_signature, expected_signature):
        raise CredentialRotationError("generation_request_signature_invalid")

    def generation_replay_checker(
        binding: EngineAuthBinding,
        nonce: str,
        timestamp: int,
    ) -> bool:
        return replay_checker(
            binding,
            observed.credential_generation_id,
            nonce,
            timestamp,
        )

    verify_authenticated_request(
        selected.credential,
        observed.envelope,
        observed_method=observed_method,
        observed_path=observed_path,
        payload=payload,
        now_seconds=now_seconds,
        replay_checker=generation_replay_checker,
    )
    return selected


def _result_identity_dict(result: DispatchResultIdentity) -> dict[str, object]:
    if type(result) is not DispatchResultIdentity:
        raise CredentialRotationError("dispatch_result_identity_invalid")
    return {
        "version": result.version,
        "authVersion": result.auth_version,
        "authAlgorithm": result.auth_algorithm,
        "bindingVersion": result.binding_version,
        "callerIdentity": result.caller_identity,
        "audienceIdentity": result.audience_identity,
        "environment": result.environment,
        "credentialKey": result.credential_key,
        "dispatchIdentitySha256": result.dispatch_identity_sha256,
        "planId": result.plan_id,
        "planSha256": result.plan_sha256,
        "jobId": result.job_id,
        "sourceArtifactId": result.source_artifact_id,
        "sourceSha256": result.source_sha256,
        "runId": result.run_id,
        "engine": result.engine,
        "candidateId": result.candidate_id,
        "candidateNamespace": result.candidate_namespace,
        "musicxmlArtifactId": result.musicxml_artifact_id,
        "diagnosticArtifactId": result.diagnostic_artifact_id,
        "resultPayloadBytes": result.result_payload_bytes,
        "resultPayloadSha256": result.result_payload_sha256,
        "signature": result.signature,
    }


def _generation_result_auth_bytes(
    generation_id: str,
    result: DispatchResultIdentity,
) -> bytes:
    return _canonical_json(
        {
            "version": GENERATION_RESULT_PROOF_VERSION,
            "algorithm": GENERATION_AUTH_ALGORITHM,
            "credentialGenerationId": generation_id,
            "dispatchResultIdentity": _result_identity_dict(result),
        }
    )


def _require_generation_bound_result(result: Any) -> GenerationBoundResult:
    if type(result) is not GenerationBoundResult:
        raise CredentialRotationError("generation_result_invalid")
    if result.version != GENERATION_RESULT_PROOF_VERSION:
        raise CredentialRotationError("generation_result_version_mismatch")
    if result.algorithm != GENERATION_AUTH_ALGORITHM:
        raise CredentialRotationError("generation_auth_algorithm_mismatch")
    _require_generation_id(result.credential_generation_id)
    _result_identity_dict(result.result)
    _require_sha256_hex(
        result.generation_signature,
        "generation_result_signature_invalid",
    )
    return result


def build_rotation_dispatch_result_identity(
    generation_credential: GenerationCredential,
    identity: DispatchIdentityBinding,
    result_payload: bytes,
) -> GenerationBoundResult:
    """Build a C.2-C result and bind it to the exact request credential generation."""

    selected = _validated_generation_credential(generation_credential)
    result = build_dispatch_result_identity(
        selected.credential,
        identity,
        result_payload,
    )
    auth_bytes = _generation_result_auth_bytes(selected.generation_id, result)
    signature = hmac.new(_secret(selected), auth_bytes, hashlib.sha256).hexdigest()
    return GenerationBoundResult(
        version=GENERATION_RESULT_PROOF_VERSION,
        algorithm=GENERATION_AUTH_ALGORITHM,
        credential_generation_id=selected.generation_id,
        result=result,
        generation_signature=signature,
    )


def require_rotation_dispatch_result_identity(
    generation_credential: GenerationCredential,
    expected_identity: DispatchIdentityBinding,
    result: GenerationBoundResult,
    result_payload: bytes,
) -> GenerationCredential:
    """Verify one result against the exact credential accepted for its request."""

    selected = _validated_generation_credential(generation_credential)
    observed = _require_generation_bound_result(result)
    auth_bytes = _generation_result_auth_bytes(
        observed.credential_generation_id,
        observed.result,
    )
    expected_signature = hmac.new(
        _secret(selected),
        auth_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(observed.generation_signature, expected_signature):
        raise CredentialRotationError("generation_result_signature_invalid")
    if observed.credential_generation_id != selected.generation_id:
        raise CredentialRotationError("generation_result_credential_mismatch")

    require_dispatch_result_identity(
        selected.credential,
        expected_identity,
        observed.result,
        result_payload,
    )
    return selected
