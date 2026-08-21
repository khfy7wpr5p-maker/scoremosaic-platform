"""Authenticated Stage 5-B3a execution trigger receiver.

One exact staging trigger may reach the B2 one-shot execution core only after
trusted plan, authenticated dispatch receipt, and immutable source state
converge. Authentication uses a purpose-separated credential domain. Replay is
reserved durably before execution. No result bytes, retry, Gateway mutation,
result persistence, source conversion, production activation, or UI is granted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import re
from typing import Any, Callable, Sequence

from .config import ServiceConfig
from .controlled_engine_execution import (
    ControlledEngineExecutionError,
    ControlledEngineExecutionResult,
    EngineExecutionClaimStore,
    Transcriber,
    execute_controlled_engine_once,
)
from .dispatch_acceptance import EngineDispatchAcceptanceStore
from .engine_execution_capability import (
    EngineExecutionCapabilityError,
    evaluate_engine_execution_eligibility,
)
from .receiver_authority import ENGINE_NAME, EngineReceiverAuthority, EngineReceiverAuthorityError
from .runtime import transcribe_file
from .source_delivery import EngineSourceStore

AUTHENTICATED_EXECUTION_TRIGGER_VERSION = "scoremosaic-authenticated-execution-trigger-v1"
EXECUTION_TRIGGER_METHOD = "POST"
EXECUTION_TRIGGER_PATH = "/internal/execute"
EXECUTION_TRIGGER_ENVIRONMENT = "staging"
EXECUTION_TRIGGER_MAX_BODY_BYTES = 4096
EXECUTION_TRIGGER_MAX_AGE_SECONDS = 60
EXECUTION_TRIGGER_MAX_FUTURE_SKEW_SECONDS = 30
EXECUTION_TRIGGER_MAX_ROTATION_GRACE_SECONDS = 300
EXECUTION_TRIGGER_REPLAY_SECONDS = 600
CALLER_SERVICE_IDENTITY = "scoremosaic-omr-gateway"
_SIGNATURE_DOMAIN = b"scoremosaic-authenticated-execution-trigger-v1"
_REPLAY_DOMAIN = b"scoremosaic-authenticated-execution-trigger-replay-v1"
_MIN_CREDENTIAL_BYTES = 32
_MAX_CREDENTIAL_BYTES = 512
_ENGINE_AUDIENCES = {
    "audiveris": "scoremosaic-audiveris-foundation",
    "homr": "scoremosaic-homr-foundation",
    "clarity": "scoremosaic-clarity-foundation",
}
AUDIENCE_IDENTITY = _ENGINE_AUDIENCES.get(ENGINE_NAME)
if AUDIENCE_IDENTITY is None:
    raise RuntimeError("execution trigger imported outside an engine package")

EXECUTION_TRIGGER_HEADER_NAMES = (
    "x-scoremosaic-execution-generation",
    "x-scoremosaic-execution-timestamp",
    "x-scoremosaic-execution-nonce",
    "x-scoremosaic-execution-signature",
)
_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_CANDIDATE_ID_RE = re.compile(r"candidate_[0-9a-f]{24}\Z")
ExecutionCredentialResolver = Callable[[str, str], bytes | bytearray | memoryview | None]


class AuthenticatedExecutionTriggerError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ExecutionCredentialRotation:
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
            raise AuthenticatedExecutionTriggerError("execution_trigger_rotation_invalid")
        if self.previous_generation_id is None:
            if self.previous_valid_until is not None:
                raise AuthenticatedExecutionTriggerError("execution_trigger_rotation_invalid")
            return
        if (
            type(self.previous_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.previous_generation_id) is None
            or self.previous_generation_id == self.current_generation_id
            or type(self.previous_valid_until) is not int
            or self.previous_valid_until <= self.current_activated_at
            or self.previous_valid_until - self.current_activated_at > EXECUTION_TRIGGER_MAX_ROTATION_GRACE_SECONDS
        ):
            raise AuthenticatedExecutionTriggerError("execution_trigger_rotation_invalid")


@dataclass(frozen=True, slots=True)
class EngineExecutionHttpContext:
    claim_store: EngineExecutionClaimStore
    config: ServiceConfig
    rotation: ExecutionCredentialRotation
    credential_resolver: ExecutionCredentialResolver
    transcriber: Transcriber = field(default=transcribe_file, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            type(self.claim_store) is not EngineExecutionClaimStore
            or type(self.config) is not ServiceConfig
            or type(self.rotation) is not ExecutionCredentialRotation
            or not callable(self.credential_resolver)
            or not callable(self.transcriber)
        ):
            raise AuthenticatedExecutionTriggerError("execution_trigger_context_invalid")


@dataclass(frozen=True, slots=True)
class AcceptedExecutionTrigger:
    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    source_artifact_id: str
    source_sha256: str
    candidate_id: str
    timeout_seconds: int
    credential_generation_id: str
    timestamp: int
    nonce_sha256: str
    payload_sha256: str
    replay_key: str
    execution: ControlledEngineExecutionResult = field(repr=False)

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
            "environment": EXECUTION_TRIGGER_ENVIRONMENT,
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "candidateId": self.candidate_id,
            "timeoutSeconds": self.timeout_seconds,
            "credentialGenerationId": self.credential_generation_id,
            "timestamp": self.timestamp,
            "nonceSha256": self.nonce_sha256,
            "payloadSha256": self.payload_sha256,
            "replayKey": self.replay_key,
            "receiverAuthenticated": True,
            "engineExecutionPerformed": True,
            "retryAllowed": False,
            "resultReturnAllowed": False,
            "resultPersistenceAllowed": False,
            "gatewayStateMutationAllowed": False,
            "execution": self.execution.as_safe_dict(),
        }


def execution_trigger_credential_key() -> str:
    return ":".join((
        AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
        EXECUTION_TRIGGER_ENVIRONMENT,
        CALLER_SERVICE_IDENTITY,
        ENGINE_NAME,
        AUDIENCE_IDENTITY,
    ))


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise AuthenticatedExecutionTriggerError("execution_trigger_json_invalid") from None


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise AuthenticatedExecutionTriggerError("execution_trigger_json_invalid")
        result[key] = value
    return result


def _decode_body(body: bytes) -> dict[str, Any]:
    if type(body) is not bytes or not 1 <= len(body) <= EXECUTION_TRIGGER_MAX_BODY_BYTES:
        raise AuthenticatedExecutionTriggerError("execution_trigger_body_invalid")
    try:
        value = json.loads(body.decode("ascii"), object_pairs_hook=_strict_pairs, parse_constant=lambda _v: (_ for _ in ()).throw(ValueError()))
    except AuthenticatedExecutionTriggerError:
        raise
    except Exception:
        raise AuthenticatedExecutionTriggerError("execution_trigger_json_invalid") from None
    if type(value) is not dict or not compare_digest(_canonical_json(value), body):
        raise AuthenticatedExecutionTriggerError("execution_trigger_json_invalid")
    if set(value) != {
        "version", "environment", "engine", "jobId", "runId",
        "dispatchIdentitySha256", "sourceArtifactId", "sourceSha256",
        "candidateId", "timeoutSeconds",
    }:
        raise AuthenticatedExecutionTriggerError("execution_trigger_body_invalid")
    return value


def _headers(headers: Sequence[tuple[str, str]]) -> dict[str, str]:
    if type(headers) not in {tuple, list}:
        raise AuthenticatedExecutionTriggerError("execution_trigger_headers_invalid")
    result: dict[str, str] = {}
    for pair in headers:
        if type(pair) is not tuple or len(pair) != 2:
            raise AuthenticatedExecutionTriggerError("execution_trigger_headers_invalid")
        name, value = pair
        if type(name) is not str or type(value) is not str:
            raise AuthenticatedExecutionTriggerError("execution_trigger_headers_invalid")
        lowered = name.lower()
        try:
            encoded = value.encode("ascii")
        except UnicodeEncodeError:
            raise AuthenticatedExecutionTriggerError("execution_trigger_headers_invalid") from None
        if (
            lowered in result or not name or not value or name != name.strip()
            or value != value.strip() or len(encoded) > 512
            or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name + value)
        ):
            raise AuthenticatedExecutionTriggerError("execution_trigger_headers_invalid")
        result[lowered] = value
    if tuple(result) != EXECUTION_TRIGGER_HEADER_NAMES:
        raise AuthenticatedExecutionTriggerError("execution_trigger_headers_invalid")
    return result


def _select_generation(rotation: ExecutionCredentialRotation, generation: str, request_timestamp: int, now_seconds: int) -> None:
    if generation == rotation.current_generation_id:
        if now_seconds < rotation.current_activated_at or request_timestamp < rotation.current_activated_at:
            raise AuthenticatedExecutionTriggerError("execution_trigger_generation_invalid")
        return
    if (
        rotation.previous_generation_id is not None
        and generation == rotation.previous_generation_id
        and rotation.previous_valid_until is not None
        and request_timestamp < rotation.current_activated_at
        and now_seconds <= rotation.previous_valid_until
    ):
        return
    raise AuthenticatedExecutionTriggerError("execution_trigger_generation_invalid")


def _credential(resolver: ExecutionCredentialResolver, generation: str) -> bytes:
    key = execution_trigger_credential_key()
    try:
        raw = resolver(key, generation)
    except Exception:
        raise AuthenticatedExecutionTriggerError("execution_trigger_credential_unavailable") from None
    if raw is None or type(raw) not in (bytes, bytearray, memoryview):
        raise AuthenticatedExecutionTriggerError("execution_trigger_credential_unavailable")
    try:
        raw_size = raw.nbytes if type(raw) is memoryview else len(raw)
        secret = bytes(raw)
    except (BufferError, TypeError, ValueError):
        raise AuthenticatedExecutionTriggerError("execution_trigger_credential_unavailable") from None
    if not _MIN_CREDENTIAL_BYTES <= raw_size <= _MAX_CREDENTIAL_BYTES:
        raise AuthenticatedExecutionTriggerError("execution_trigger_credential_unavailable")
    return secret


def _signature_message(generation: str, timestamp: int, nonce: str, body: bytes) -> bytes:
    metadata = _canonical_json({
        "version": AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
        "environment": EXECUTION_TRIGGER_ENVIRONMENT,
        "callerIdentity": CALLER_SERVICE_IDENTITY,
        "engine": ENGINE_NAME,
        "audienceIdentity": AUDIENCE_IDENTITY,
        "credentialKey": execution_trigger_credential_key(),
        "method": EXECUTION_TRIGGER_METHOD,
        "path": EXECUTION_TRIGGER_PATH,
        "credentialGenerationId": generation,
        "timestamp": timestamp,
        "nonce": nonce,
        "payloadBytes": len(body),
        "payloadSha256": sha256(body).hexdigest(),
    })
    return b"\0".join((_SIGNATURE_DOMAIN, metadata, body))


def _replay_key(generation: str, timestamp: int, nonce: str, payload_sha256: str) -> str:
    return sha256(b"\0".join((
        _REPLAY_DOMAIN,
        ENGINE_NAME.encode("ascii"),
        generation.encode("ascii"),
        str(timestamp).encode("ascii"),
        nonce.encode("ascii"),
        payload_sha256.encode("ascii"),
    ))).hexdigest()


def accept_authenticated_execution_trigger(
    *,
    authority: EngineReceiverAuthority,
    dispatch_acceptance_store: EngineDispatchAcceptanceStore,
    source_store: EngineSourceStore,
    http_context: EngineExecutionHttpContext,
    headers: Sequence[tuple[str, str]],
    body: bytes,
    now_seconds: int,
) -> AcceptedExecutionTrigger:
    if (
        type(authority) is not EngineReceiverAuthority
        or type(dispatch_acceptance_store) is not EngineDispatchAcceptanceStore
        or type(source_store) is not EngineSourceStore
        or type(http_context) is not EngineExecutionHttpContext
        or type(now_seconds) is not int or now_seconds < 0
    ):
        raise AuthenticatedExecutionTriggerError("execution_trigger_input_invalid")

    parsed_headers = _headers(headers)
    generation = parsed_headers["x-scoremosaic-execution-generation"]
    timestamp_text = parsed_headers["x-scoremosaic-execution-timestamp"]
    nonce = parsed_headers["x-scoremosaic-execution-nonce"]
    signature = parsed_headers["x-scoremosaic-execution-signature"]
    if (
        _GENERATION_RE.fullmatch(generation) is None
        or not timestamp_text.isdigit() or timestamp_text.startswith("0")
        or _NONCE_RE.fullmatch(nonce) is None or _SHA256_RE.fullmatch(signature) is None
    ):
        raise AuthenticatedExecutionTriggerError("execution_trigger_headers_invalid")
    timestamp = int(timestamp_text, 10)
    if timestamp > now_seconds + EXECUTION_TRIGGER_MAX_FUTURE_SKEW_SECONDS or now_seconds - timestamp > EXECUTION_TRIGGER_MAX_AGE_SECONDS:
        raise AuthenticatedExecutionTriggerError("execution_trigger_timestamp_invalid")

    payload = _decode_body(body)
    if (
        payload.get("version") != AUTHENTICATED_EXECUTION_TRIGGER_VERSION
        or payload.get("environment") != EXECUTION_TRIGGER_ENVIRONMENT
        or payload.get("engine") != ENGINE_NAME
        or type(payload.get("jobId")) is not str or _JOB_ID_RE.fullmatch(payload["jobId"]) is None
        or type(payload.get("runId")) is not str or _RUN_ID_RE.fullmatch(payload["runId"]) is None
        or type(payload.get("dispatchIdentitySha256")) is not str or _SHA256_RE.fullmatch(payload["dispatchIdentitySha256"]) is None
        or type(payload.get("sourceArtifactId")) is not str or _ARTIFACT_ID_RE.fullmatch(payload["sourceArtifactId"]) is None
        or type(payload.get("sourceSha256")) is not str or _SHA256_RE.fullmatch(payload["sourceSha256"]) is None
        or type(payload.get("candidateId")) is not str or _CANDIDATE_ID_RE.fullmatch(payload["candidateId"]) is None
        or type(payload.get("timeoutSeconds")) is not int or not 30 <= payload["timeoutSeconds"] <= 7200
    ):
        raise AuthenticatedExecutionTriggerError("execution_trigger_body_invalid")

    try:
        eligibility = evaluate_engine_execution_eligibility(
            authority=authority,
            dispatch_acceptance_store=dispatch_acceptance_store,
            source_store=source_store,
            job_id=payload["jobId"],
            run_id=payload["runId"],
            dispatch_identity_sha256=payload["dispatchIdentitySha256"],
        )
    except EngineExecutionCapabilityError:
        raise AuthenticatedExecutionTriggerError("execution_trigger_prerequisite_invalid") from None
    if (
        eligibility.source_artifact_id != payload["sourceArtifactId"]
        or not compare_digest(eligibility.source_sha256, payload["sourceSha256"])
        or eligibility.candidate_id != payload["candidateId"]
        or eligibility.timeout_seconds != payload["timeoutSeconds"]
    ):
        raise AuthenticatedExecutionTriggerError("execution_trigger_prerequisite_mismatch")

    _select_generation(http_context.rotation, generation, timestamp, now_seconds)
    secret = _credential(http_context.credential_resolver, generation)
    expected_signature = hmac_new(secret, _signature_message(generation, timestamp, nonce, body), sha256).hexdigest()
    if not compare_digest(expected_signature, signature):
        raise AuthenticatedExecutionTriggerError("execution_trigger_signature_invalid")

    payload_sha = sha256(body).hexdigest()
    replay_key = _replay_key(generation, timestamp, nonce, payload_sha)
    try:
        authority.reserve_replay(
            replay_key=replay_key,
            credential_generation_id=generation,
            request_timestamp=timestamp,
            replay_expires_at=timestamp + EXECUTION_TRIGGER_REPLAY_SECONDS,
        )
    except EngineReceiverAuthorityError:
        raise AuthenticatedExecutionTriggerError("execution_trigger_replay_or_state_invalid") from None

    try:
        execution = execute_controlled_engine_once(
            authority=authority,
            dispatch_acceptance_store=dispatch_acceptance_store,
            source_store=source_store,
            claim_store=http_context.claim_store,
            config=http_context.config,
            job_id=eligibility.job_id,
            run_id=eligibility.run_id,
            dispatch_identity_sha256=eligibility.dispatch_identity_sha256,
            transcriber=http_context.transcriber,
        )
    except ControlledEngineExecutionError as exc:
        category = "execution_trigger_reconciliation_required" if exc.category == "engine_execution_reconciliation_required" else "execution_trigger_execution_failed"
        raise AuthenticatedExecutionTriggerError(category) from None

    return AcceptedExecutionTrigger(
        engine=ENGINE_NAME,
        job_id=eligibility.job_id,
        run_id=eligibility.run_id,
        dispatch_identity_sha256=eligibility.dispatch_identity_sha256,
        source_artifact_id=eligibility.source_artifact_id,
        source_sha256=eligibility.source_sha256,
        candidate_id=eligibility.candidate_id,
        timeout_seconds=eligibility.timeout_seconds,
        credential_generation_id=generation,
        timestamp=timestamp,
        nonce_sha256=sha256(nonce.encode("ascii")).hexdigest(),
        payload_sha256=payload_sha,
        replay_key=replay_key,
        execution=execution,
    )
