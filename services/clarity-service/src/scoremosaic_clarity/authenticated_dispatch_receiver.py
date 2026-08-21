"""Engine-owned authenticated dispatch receiver for Stage 4-C.

This boundary verifies one exact controlled staging C.2-E wire request against
already-provisioned engine-owned trusted-plan state. It performs no engine
execution, no source retrieval, no job mutation, no retry, and no network send.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import re
from typing import Any, Callable, Sequence

from .receiver_authority import (
    ENGINE_NAME,
    EngineReceiverAuthority,
    EngineReceiverAuthorityError,
)

AUTH_BINDING_VERSION = "scoremosaic-s2s-auth-v1"
REQUEST_AUTH_VERSION = "scoremosaic-s2s-request-v1"
REQUEST_AUTH_ALGORITHM = "hmac-sha256"
ROTATION_CONTRACT_VERSION = "scoremosaic-s2s-rotation-v1"
GENERATION_REQUEST_PROOF_VERSION = "scoremosaic-s2s-request-generation-v1"
GENERATION_AUTH_ALGORITHM = "hmac-sha256"
DISPATCH_IDENTITY_VERSION = "scoremosaic-dispatch-identity-v1"
DISPATCH_METHOD = "POST"
DISPATCH_PATH = "/internal/transcribe"
CALLER_SERVICE_IDENTITY = "scoremosaic-omr-gateway"
RECEIVER_ENVIRONMENT = "staging"
MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES = 4096
MAX_HEADER_VALUE_BYTES = 256
MAX_REQUEST_AGE_SECONDS = 120
MAX_FUTURE_SKEW_SECONDS = 30
MAX_ROTATION_GRACE_SECONDS = 300
MAX_REPLAY_RESERVATION_SECONDS = 600
MIN_CREDENTIAL_BYTES = 32
MAX_CREDENTIAL_BYTES = 512

_ENGINE_AUDIENCES = {
    "audiveris": "scoremosaic-audiveris-foundation",
    "homr": "scoremosaic-homr-foundation",
    "clarity": "scoremosaic-clarity-foundation",
}
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
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_HEADER_NAME_RE = re.compile(r"[a-z0-9-]+\Z")
_ACCEPTED_SEAL = object()

DispatchCredentialResolver = Callable[
    [str, str], bytes | bytearray | memoryview | None
]


class AuthenticatedDispatchReceiverError(ValueError):
    """Stable bounded receiver error category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ReceiverCredentialRotation:
    """Receiver-owned accepted current/previous dispatch generations."""

    current_generation_id: str
    current_activated_at: int
    previous_generation_id: str | None = None
    previous_valid_until: int | None = None

    def __post_init__(self) -> None:
        if (
            type(self.current_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.current_generation_id) is None
            or type(self.current_activated_at) is not int
            or self.current_activated_at < 0
        ):
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_rotation_invalid"
            )
        if self.previous_generation_id is None:
            if self.previous_valid_until is not None:
                raise AuthenticatedDispatchReceiverError(
                    "dispatch_receiver_rotation_invalid"
                )
            return
        if (
            type(self.previous_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.previous_generation_id) is None
            or self.previous_generation_id == self.current_generation_id
            or type(self.previous_valid_until) is not int
            or self.previous_valid_until <= self.current_activated_at
            or self.previous_valid_until - self.current_activated_at
            > MAX_ROTATION_GRACE_SECONDS
        ):
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_rotation_invalid"
            )


@dataclass(frozen=True, slots=True)
class AcceptedAuthenticatedDispatch:
    """Sealed non-executable evidence that the HTTP receiver gate passed."""

    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    credential_generation_id: str
    request_timestamp: int
    request_nonce_sha256: str
    payload_sha256: str
    replay_reservation_key: str
    replay_expires_at: int
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _ACCEPTED_SEAL
            or self.engine != ENGINE_NAME
            or type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.run_id) is not str
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or type(self.dispatch_identity_sha256) is not str
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or type(self.credential_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.credential_generation_id) is None
            or type(self.request_timestamp) is not int
            or self.request_timestamp < 0
            or type(self.request_nonce_sha256) is not str
            or _SHA256_RE.fullmatch(self.request_nonce_sha256) is None
            or type(self.payload_sha256) is not str
            or _SHA256_RE.fullmatch(self.payload_sha256) is None
            or type(self.replay_reservation_key) is not str
            or _SHA256_RE.fullmatch(self.replay_reservation_key) is None
            or type(self.replay_expires_at) is not int
            or self.replay_expires_at
            != self.request_timestamp + MAX_REPLAY_RESERVATION_SECONDS
        ):
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_result_invalid"
            )

    @property
    def receiver_authenticated(self) -> bool:
        return True

    @property
    def trusted_plan_converged(self) -> bool:
        return True

    @property
    def replay_reserved(self) -> bool:
        return True

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def source_access_allowed(self) -> bool:
        return False

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "environment": RECEIVER_ENVIRONMENT,
            "jobId": self.job_id,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "credentialGenerationId": self.credential_generation_id,
            "requestTimestamp": self.request_timestamp,
            "requestNonceSha256": self.request_nonce_sha256,
            "payloadSha256": self.payload_sha256,
            "replayReservationKey": self.replay_reservation_key,
            "replayExpiresAt": self.replay_expires_at,
            "receiverAuthenticated": True,
            "trustedPlanConverged": True,
            "replayReserved": True,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
            "sourceAccessAllowed": False,
            "jobStateMutationAllowed": False,
        }


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_json_invalid"
        ) from None


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_json_invalid"
            )
        result[key] = value
    return result


def _decode_canonical_body(raw: bytes) -> dict[str, Any]:
    if (
        type(raw) is not bytes
        or not raw
        or len(raw) > MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
    ):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_payload_invalid"
        )
    try:
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except AuthenticatedDispatchReceiverError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
        RecursionError,
    ):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_json_invalid"
        ) from None
    if type(value) is not dict or not compare_digest(_canonical_json_bytes(value), raw):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_json_invalid"
        )
    return value


def _expected_binding() -> dict[str, str]:
    audience = _ENGINE_AUDIENCES.get(ENGINE_NAME)
    if audience is None:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_binding_invalid"
        )
    credential_key = ":".join(
        (
            AUTH_BINDING_VERSION,
            RECEIVER_ENVIRONMENT,
            CALLER_SERVICE_IDENTITY,
            ENGINE_NAME,
            audience,
        )
    )
    return {
        "bindingVersion": AUTH_BINDING_VERSION,
        "callerIdentity": CALLER_SERVICE_IDENTITY,
        "engine": ENGINE_NAME,
        "audienceIdentity": audience,
        "environment": RECEIVER_ENVIRONMENT,
        "credentialKey": credential_key,
    }


def _require_ascii_header_value(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        )
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        ) from None
    if (
        len(encoded) > MAX_HEADER_VALUE_BYTES
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        )
    return value


def _normalize_headers(
    headers: Sequence[tuple[str, str]],
) -> dict[str, str]:
    if type(headers) not in {tuple, list} or len(headers) != len(WIRE_HEADER_NAMES):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        )
    normalized: dict[str, str] = {}
    for pair in headers:
        if type(pair) is not tuple or len(pair) != 2:
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_headers_invalid"
            )
        name, value = pair
        if type(name) is not str:
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_headers_invalid"
            )
        try:
            encoded_name = name.encode("ascii")
        except UnicodeEncodeError:
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_headers_invalid"
            ) from None
        lowered = name.lower()
        if (
            not encoded_name
            or len(encoded_name) > 128
            or name != name.strip()
            or _HEADER_NAME_RE.fullmatch(lowered) is None
            or lowered not in WIRE_HEADER_NAMES
            or lowered in normalized
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name)
        ):
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_headers_invalid"
            )
        normalized[lowered] = _require_ascii_header_value(value)
    if frozenset(normalized) != frozenset(WIRE_HEADER_NAMES):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        )
    return normalized


def _canonical_decimal(value: str, *, allow_zero: bool) -> int:
    if not value.isdigit() or (len(value) > 1 and value.startswith("0")):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        )
    try:
        parsed = int(value, 10)
    except ValueError:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        ) from None
    if parsed < (0 if allow_zero else 1):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        )
    return parsed


def _require_sha256(value: str) -> str:
    if _SHA256_RE.fullmatch(value) is None:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_headers_invalid"
        )
    return value


def _require_generation(value: str) -> str:
    if _GENERATION_RE.fullmatch(value) is None:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_generation_invalid"
        )
    return value


def _require_nonce(value: str) -> str:
    if _NONCE_RE.fullmatch(value) is None:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_nonce_invalid"
        )
    return value


def _semantic_precheck(
    *,
    authority: EngineReceiverAuthority,
    body: bytes,
) -> tuple[dict[str, Any], str, str]:
    """Resolve trusted state and require exact C.2-C bytes before authentication."""

    decoded = _decode_canonical_body(body)
    required = {
        "version",
        "planId",
        "planSha256",
        "jobId",
        "sourceArtifact",
        "engineRun",
    }
    job_id = decoded.get("jobId")
    run = decoded.get("engineRun")
    if (
        set(decoded) != required
        or decoded.get("version") != DISPATCH_IDENTITY_VERSION
        or type(job_id) is not str
        or _JOB_ID_RE.fullmatch(job_id) is None
        or type(run) is not dict
        or run.get("engine") != ENGINE_NAME
    ):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_identity_invalid"
        )

    try:
        trusted = authority.load_trusted_plan(job_id=job_id)
    except EngineReceiverAuthorityError:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_trusted_plan_invalid"
        ) from None

    try:
        plan = json.loads(
            trusted.canonical_plan_bytes.decode("ascii"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        AuthenticatedDispatchReceiverError,
    ):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_trusted_plan_invalid"
        ) from None
    if type(plan) is not dict:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_trusted_plan_invalid"
        )
    source = plan.get("sourceArtifact")
    runs = plan.get("engineRuns")
    if type(source) is not dict or type(runs) is not list:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_trusted_plan_invalid"
        )
    matching = [
        candidate
        for candidate in runs
        if type(candidate) is dict and candidate.get("engine") == ENGINE_NAME
    ]
    if len(matching) != 1:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_trusted_plan_invalid"
        )
    trusted_run = matching[0]
    artifacts = trusted_run.get("expectedArtifacts")
    if type(artifacts) is not list:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_trusted_plan_invalid"
        )
    by_kind = {
        artifact.get("kind"): artifact
        for artifact in artifacts
        if type(artifact) is dict
    }
    if set(by_kind) != {"musicxml", "diagnostic"}:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_trusted_plan_invalid"
        )
    expected = {
        "version": DISPATCH_IDENTITY_VERSION,
        "planId": plan.get("planId"),
        "planSha256": plan.get("planSha256"),
        "jobId": plan.get("jobId"),
        "sourceArtifact": {
            "artifactId": source.get("artifactId"),
            "artifactRef": source.get("artifactRef"),
            "sha256": source.get("sha256"),
            "sizeBytes": source.get("sizeBytes"),
            "mediaType": source.get("mediaType"),
        },
        "engineRun": {
            "runId": trusted_run.get("runId"),
            "engine": trusted_run.get("engine"),
            "candidateId": trusted_run.get("candidateId"),
            "candidateNamespace": trusted_run.get("candidateNamespace"),
            "expectedArtifacts": [
                {
                    "kind": "musicxml",
                    "artifactId": by_kind["musicxml"].get("artifactId"),
                },
                {
                    "kind": "diagnostic",
                    "artifactId": by_kind["diagnostic"].get("artifactId"),
                },
            ],
        },
    }
    expected_body = _canonical_json_bytes(expected)
    if not compare_digest(body, expected_body):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_identity_mismatch"
        )
    run_id = trusted_run.get("runId")
    if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_trusted_plan_invalid"
        )
    return expected, job_id, run_id


def _select_generation(
    rotation: ReceiverCredentialRotation,
    generation_id: str,
    *,
    now_seconds: int,
) -> str:
    if type(rotation) is not ReceiverCredentialRotation:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_rotation_invalid"
        )
    if type(now_seconds) is not int or now_seconds < 0:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_time_invalid"
        )
    if now_seconds < rotation.current_activated_at:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_rotation_not_active"
        )
    generation = _require_generation(generation_id)
    if generation == rotation.current_generation_id:
        return generation
    if generation == rotation.previous_generation_id:
        if (
            rotation.previous_valid_until is None
            or now_seconds >= rotation.previous_valid_until
        ):
            raise AuthenticatedDispatchReceiverError(
                "dispatch_receiver_generation_expired"
            )
        return generation
    raise AuthenticatedDispatchReceiverError(
        "dispatch_receiver_generation_unknown"
    )


def _resolve_secret(
    *,
    credential_key: str,
    generation_id: str,
    resolver: DispatchCredentialResolver,
) -> bytes:
    if not callable(resolver):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_credential_unavailable"
        )
    try:
        raw = resolver(credential_key, generation_id)
    except Exception:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_credential_unavailable"
        ) from None
    if raw is None or type(raw) not in (bytes, bytearray, memoryview):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_credential_unavailable"
        )
    try:
        raw_size = raw.nbytes if type(raw) is memoryview else len(raw)
        secret = bytes(raw)
    except (BufferError, TypeError, ValueError):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_credential_unavailable"
        ) from None
    if not MIN_CREDENTIAL_BYTES <= raw_size <= MAX_CREDENTIAL_BYTES:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_credential_unavailable"
        )
    return secret


def _request_envelope_dict(
    *,
    binding: dict[str, str],
    timestamp: int,
    nonce: str,
    payload_bytes: int,
    payload_sha256: str,
    request_signature: str,
) -> dict[str, object]:
    return {
        "version": REQUEST_AUTH_VERSION,
        "algorithm": REQUEST_AUTH_ALGORITHM,
        "bindingVersion": binding["bindingVersion"],
        "callerIdentity": binding["callerIdentity"],
        "engine": binding["engine"],
        "audienceIdentity": binding["audienceIdentity"],
        "environment": binding["environment"],
        "credentialKey": binding["credentialKey"],
        "method": DISPATCH_METHOD,
        "path": DISPATCH_PATH,
        "timestamp": timestamp,
        "nonce": nonce,
        "payloadBytes": payload_bytes,
        "payloadSha256": payload_sha256,
        "signature": request_signature,
    }


def _inner_auth_bytes(
    *,
    binding: dict[str, str],
    timestamp: int,
    nonce: str,
    payload_bytes: int,
    payload_sha256: str,
) -> bytes:
    return _canonical_json_bytes(
        {
            "algorithm": REQUEST_AUTH_ALGORITHM,
            "audienceIdentity": binding["audienceIdentity"],
            "bindingVersion": binding["bindingVersion"],
            "callerIdentity": binding["callerIdentity"],
            "credentialKey": binding["credentialKey"],
            "engine": binding["engine"],
            "environment": binding["environment"],
            "method": DISPATCH_METHOD,
            "nonce": nonce,
            "path": DISPATCH_PATH,
            "payloadBytes": payload_bytes,
            "payloadSha256": payload_sha256,
            "timestamp": timestamp,
            "version": REQUEST_AUTH_VERSION,
        }
    )


def _generation_auth_bytes(
    *,
    generation_id: str,
    envelope: dict[str, object],
) -> bytes:
    return _canonical_json_bytes(
        {
            "version": GENERATION_REQUEST_PROOF_VERSION,
            "algorithm": GENERATION_AUTH_ALGORITHM,
            "credentialGenerationId": generation_id,
            "requestEnvelope": envelope,
        }
    )


def _replay_key(
    *,
    binding: dict[str, str],
    generation_id: str,
    nonce: str,
) -> str:
    payload = {
        "version": ROTATION_CONTRACT_VERSION,
        "bindingVersion": binding["bindingVersion"],
        "callerIdentity": binding["callerIdentity"],
        "engine": binding["engine"],
        "audienceIdentity": binding["audienceIdentity"],
        "environment": binding["environment"],
        "credentialKey": binding["credentialKey"],
        "credentialGenerationId": generation_id,
        "nonce": nonce,
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def accept_authenticated_dispatch(
    *,
    authority: EngineReceiverAuthority,
    rotation: ReceiverCredentialRotation,
    headers: Sequence[tuple[str, str]],
    body: bytes,
    observed_method: str,
    observed_path: str,
    now_seconds: int,
    credential_resolver: DispatchCredentialResolver,
) -> AcceptedAuthenticatedDispatch:
    """Verify one C.2-E request and persist only its durable replay tombstone."""

    if type(authority) is not EngineReceiverAuthority or authority.engine != ENGINE_NAME:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_authority_invalid"
        )
    if observed_method != DISPATCH_METHOD or observed_path != DISPATCH_PATH:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_target_invalid"
        )

    # Frozen C.2-E ordering: semantic/trusted-plan convergence deliberately
    # precedes credential resolution and cryptographic acceptance.
    _identity, job_id, run_id = _semantic_precheck(
        authority=authority,
        body=body,
    )
    normalized = _normalize_headers(headers)
    generation = _select_generation(
        rotation,
        normalized[_HEADER_GENERATION],
        now_seconds=now_seconds,
    )
    timestamp = _canonical_decimal(
        normalized[_HEADER_TIMESTAMP],
        allow_zero=True,
    )
    nonce = _require_nonce(normalized[_HEADER_NONCE])
    payload_bytes = _canonical_decimal(
        normalized[_HEADER_PAYLOAD_BYTES],
        allow_zero=False,
    )
    if payload_bytes > MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_payload_invalid"
        )
    payload_sha256 = _require_sha256(normalized[_HEADER_PAYLOAD_SHA256])
    request_signature = _require_sha256(normalized[_HEADER_REQUEST_SIGNATURE])
    generation_signature = _require_sha256(
        normalized[_HEADER_GENERATION_SIGNATURE]
    )
    if type(now_seconds) is not int or now_seconds < 0:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_time_invalid"
        )

    binding = _expected_binding()
    secret = _resolve_secret(
        credential_key=binding["credentialKey"],
        generation_id=generation,
        resolver=credential_resolver,
    )
    envelope = _request_envelope_dict(
        binding=binding,
        timestamp=timestamp,
        nonce=nonce,
        payload_bytes=payload_bytes,
        payload_sha256=payload_sha256,
        request_signature=request_signature,
    )

    expected_generation_signature = hmac_new(
        secret,
        _generation_auth_bytes(
            generation_id=generation,
            envelope=envelope,
        ),
        sha256,
    ).hexdigest()
    if not compare_digest(
        generation_signature,
        expected_generation_signature,
    ):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_generation_signature_invalid"
        )

    # Inner C.2-A checks occur only after the generation proof passed.
    if timestamp > now_seconds + MAX_FUTURE_SKEW_SECONDS:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_timestamp_in_future"
        )
    if now_seconds - timestamp > MAX_REQUEST_AGE_SECONDS:
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_timestamp_expired"
        )
    if payload_bytes != len(body):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_payload_size_mismatch"
        )
    observed_digest = sha256(body).hexdigest()
    if not compare_digest(payload_sha256, observed_digest):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_payload_digest_mismatch"
        )

    expected_request_signature = hmac_new(
        secret,
        _inner_auth_bytes(
            binding=binding,
            timestamp=timestamp,
            nonce=nonce,
            payload_bytes=payload_bytes,
            payload_sha256=payload_sha256,
        ),
        sha256,
    ).hexdigest()
    if not compare_digest(request_signature, expected_request_signature):
        raise AuthenticatedDispatchReceiverError(
            "dispatch_receiver_request_signature_invalid"
        )

    replay_key = _replay_key(
        binding=binding,
        generation_id=generation,
        nonce=nonce,
    )
    replay_expires_at = timestamp + MAX_REPLAY_RESERVATION_SECONDS
    try:
        authority.reserve_replay(
            replay_key=replay_key,
            credential_generation_id=generation,
            request_timestamp=timestamp,
            replay_expires_at=replay_expires_at,
        )
    except EngineReceiverAuthorityError as exc:
        if exc.category == "receiver_authority_replay_detected":
            category = "dispatch_receiver_replay_detected"
        else:
            category = "dispatch_receiver_replay_state_invalid"
        raise AuthenticatedDispatchReceiverError(category) from None

    return AcceptedAuthenticatedDispatch(
        engine=ENGINE_NAME,
        job_id=job_id,
        run_id=run_id,
        dispatch_identity_sha256=sha256(body).hexdigest(),
        credential_generation_id=generation,
        request_timestamp=timestamp,
        request_nonce_sha256=sha256(nonce.encode("ascii")).hexdigest(),
        payload_sha256=payload_sha256,
        replay_reservation_key=replay_key,
        replay_expires_at=replay_expires_at,
        _seal=_ACCEPTED_SEAL,
    )
