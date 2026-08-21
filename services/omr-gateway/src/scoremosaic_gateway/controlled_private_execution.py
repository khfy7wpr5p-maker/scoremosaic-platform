"""Authenticated one-shot Gateway -> engine execution boundary for Stage 5-B3b.

Execution is allowed only after exact capsule, authenticated dispatch evidence,
durable source-delivery evidence, and durable dispatching(2) state converge.
A create-once HMAC-sealed claim is published before network I/O. Any ambiguity
is reconciliation-only and never retried automatically. Result bytes are not
accepted or persisted here; Stage 6 owns result ingestion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from http.client import HTTPConnection, HTTPResponse
import json
import re
import socket
from typing import Any, Callable
from urllib.parse import urlsplit

from .config import EngineEndpoint
from .controlled_private_network_dispatch import ControlledPrivateNetworkDispatchResult
from .controlled_private_source_delivery import (
    CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION,
    ControlledPrivateSourceDeliveryError,
    ControlledPrivateSourceDeliveryResult,
    _CLAIM_MAC_FIELD as _SOURCE_CLAIM_MAC_FIELD,
    _EXPECTED_BOUNDARIES as _SOURCE_BOUNDARIES,
    _canonical_json as _source_canonical_json,
    _claim_key as _source_claim_key,
    _claim_mac as _source_claim_mac,
    _claim_path as _source_claim_path,
)
from .controlled_staging_dispatching_transition import (
    ControlledStagingDispatchingTransitionError,
    recover_controlled_staging_dispatching_run,
)
from .dispatch_input_capsule import (
    DispatchInputCapsule,
    DispatchInputCapsuleError,
    verify_dispatch_input_capsule,
)
from .dispatch_target import APPROVED_ENGINE_ORIGINS
from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError,
    MinimumStagingVerticalSliceResult,
    StagingUploadProvider,
    _MAX_STATE_RECORD_BYTES,
    _decode_record,
)
from .orchestration import MAX_ENGINE_TIMEOUT_SECONDS, MIN_ENGINE_TIMEOUT_SECONDS

CONTROLLED_PRIVATE_EXECUTION_VERSION = "scoremosaic-controlled-private-execution-v1"
AUTHENTICATED_EXECUTION_TRIGGER_VERSION = "scoremosaic-authenticated-execution-trigger-v1"
EXECUTION_TRIGGER_PATH = "/internal/execute"
CALLER_SERVICE_IDENTITY = "scoremosaic-omr-gateway"
MAX_REQUEST_BYTES = 4096
MAX_RESPONSE_BYTES = 16 * 1024
CONNECT_TIMEOUT_SECONDS = 10
RESPONSE_TIMEOUT_GRACE_SECONDS = 30
MAX_RESPONSE_TIMEOUT_SECONDS = MAX_ENGINE_TIMEOUT_SECONDS + RESPONSE_TIMEOUT_GRACE_SECONDS
_SIGNATURE_DOMAIN = b"scoremosaic-authenticated-execution-trigger-v1"
_CLAIM_DOMAIN = b"scoremosaic-controlled-private-execution-claim-v1"
_CLAIM_MAC_FIELD = "execution_trigger_claim_integrity_mac"
_AUDIENCES = {
    "audiveris": "scoremosaic-audiveris-foundation",
    "homr": "scoremosaic-homr-foundation",
    "clarity": "scoremosaic-clarity-foundation",
}
_GEN_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_ART_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_CAND_RE = re.compile(r"candidate_[0-9a-f]{24}\Z")
_REQUEST_HEADER_NAMES = (
    "content-type",
    "content-length",
    "x-scoremosaic-execution-generation",
    "x-scoremosaic-execution-timestamp",
    "x-scoremosaic-execution-nonce",
    "x-scoremosaic-execution-signature",
)


class ControlledPrivateExecutionError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class PrivateExecutionHttpResponse:
    status: int
    content_type: str
    body: bytes
    location: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.status) is not int
            or not 100 <= self.status <= 599
            or type(self.content_type) is not str
            or type(self.body) is not bytes
            or len(self.body) > MAX_RESPONSE_BYTES
            or (self.location is not None and type(self.location) is not str)
        ):
            raise ControlledPrivateExecutionError(
                "staging_execution_transport_response_invalid"
            )


ExecutionTransport = Callable[
    [str, str, tuple[tuple[str, str], ...], bytes, int, int],
    PrivateExecutionHttpResponse,
]


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticatedExecutionTriggerRequest:
    engine: str
    generation_id: str
    timestamp: int
    timeout_seconds: int
    nonce_sha256: str
    payload_sha256: str
    body: bytes = field(repr=False)
    headers: tuple[tuple[str, str], ...] = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.engine) is not str
            or self.engine not in _AUDIENCES
            or not _matches(_GEN_RE, self.generation_id)
            or type(self.timestamp) is not int
            or self.timestamp < 0
            or type(self.timeout_seconds) is not int
            or not MIN_ENGINE_TIMEOUT_SECONDS
            <= self.timeout_seconds
            <= MAX_ENGINE_TIMEOUT_SECONDS
            or not _matches(_SHA_RE, self.nonce_sha256)
            or not _matches(_SHA_RE, self.payload_sha256)
            or type(self.body) is not bytes
            or not 1 <= len(self.body) <= MAX_REQUEST_BYTES
            or type(self.headers) is not tuple
        ):
            raise ControlledPrivateExecutionError("staging_execution_request_invalid")
        observed: dict[str, str] = {}
        for pair in self.headers:
            if type(pair) is not tuple or len(pair) != 2:
                raise ControlledPrivateExecutionError("staging_execution_request_invalid")
            name, value = pair
            if type(name) is not str or type(value) is not str or name in observed:
                raise ControlledPrivateExecutionError("staging_execution_request_invalid")
            observed[name] = value
        if tuple(observed) != _REQUEST_HEADER_NAMES:
            raise ControlledPrivateExecutionError("staging_execution_request_invalid")
        if (
            observed["content-type"] != "application/json"
            or observed["content-length"] != str(len(self.body))
            or observed["x-scoremosaic-execution-generation"] != self.generation_id
            or observed["x-scoremosaic-execution-timestamp"] != str(self.timestamp)
            or not _matches(_NONCE_RE, observed["x-scoremosaic-execution-nonce"])
            or not _matches(_SHA_RE, observed["x-scoremosaic-execution-signature"])
        ):
            raise ControlledPrivateExecutionError("staging_execution_request_invalid")

    def __repr__(self) -> str:
        return (
            "AuthenticatedExecutionTriggerRequest("
            f"engine={self.engine!r}, generation_id={self.generation_id!r}, "
            f"timestamp={self.timestamp!r}, timeout_seconds={self.timeout_seconds!r}, "
            f"nonce_sha256={self.nonce_sha256!r}, payload_sha256={self.payload_sha256!r}, "
            "body=<redacted>, headers=<redacted>)"
        )

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
            "environment": "staging",
            "engine": self.engine,
            "credentialGenerationId": self.generation_id,
            "timestamp": self.timestamp,
            "timeoutSeconds": self.timeout_seconds,
            "nonceSha256": self.nonce_sha256,
            "payloadSha256": self.payload_sha256,
            "payloadBytes": len(self.body),
            "signaturePresent": True,
            "rawNonceExportAllowed": False,
            "signatureExportAllowed": False,
        }


@dataclass(frozen=True, slots=True)
class ControlledPrivateExecutionResult:
    version: str
    job_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    source_artifact_id: str
    source_sha256: str
    candidate_id: str
    target_origin: str
    claim_key: str
    http_status: int
    execution_attempt_count: int
    reconciliation_required_on_restart: bool

    def __post_init__(self) -> None:
        expected = (
            APPROVED_ENGINE_ORIGINS["staging"].get(self.engine)
            if type(self.engine) is str
            else None
        )
        if (
            self.version != CONTROLLED_PRIVATE_EXECUTION_VERSION
            or expected is None
            or type(self.target_origin) is not str
            or self.target_origin != expected
            or not _matches(_JOB_RE, self.job_id)
            or not _matches(_RUN_RE, self.run_id)
            or not _matches(_SHA_RE, self.dispatch_identity_sha256)
            or not _matches(_ART_RE, self.source_artifact_id)
            or not _matches(_SHA_RE, self.source_sha256)
            or not _matches(_CAND_RE, self.candidate_id)
            or not _matches(_SHA_RE, self.claim_key)
            or self.http_status != 200
            or self.execution_attempt_count != 1
            or self.reconciliation_required_on_restart is not True
        ):
            raise ControlledPrivateExecutionError("staging_execution_result_invalid")

    @property
    def engine_execution_performed(self) -> bool:
        return True

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def result_return_allowed(self) -> bool:
        return False

    @property
    def result_persistence_allowed(self) -> bool:
        return False

    @property
    def post_dispatch_job_mutation_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "environment": "staging",
            "jobId": self.job_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "candidateId": self.candidate_id,
            "targetOrigin": self.target_origin,
            "claimKey": self.claim_key,
            "httpStatus": 200,
            "executionAttemptCount": 1,
            "reconciliationRequiredOnRestart": True,
            "engineExecutionPerformed": True,
            "retryAllowed": False,
            "resultReturnAllowed": False,
            "resultPersistenceAllowed": False,
            "postDispatchJobMutationAllowed": False,
        }


def _canonical(value: Any, category: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise ControlledPrivateExecutionError(category) from None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise ControlledPrivateExecutionError("staging_execution_json_invalid")
        result[key] = value
    return result


def _endpoint(endpoint: object) -> EngineEndpoint:
    if type(endpoint) is not EngineEndpoint:
        raise ControlledPrivateExecutionError("staging_execution_endpoint_invalid")
    expected = APPROVED_ENGINE_ORIGINS["staging"].get(endpoint.name)
    if expected is None or endpoint.base_url != expected:
        raise ControlledPrivateExecutionError("staging_execution_endpoint_invalid")
    try:
        parsed = urlsplit(endpoint.base_url)
        port = parsed.port
    except ValueError:
        raise ControlledPrivateExecutionError("staging_execution_endpoint_invalid") from None
    if (
        parsed.scheme != "http"
        or parsed.hostname is None
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ControlledPrivateExecutionError("staging_execution_endpoint_invalid")
    return endpoint


def execution_trigger_credential_key(engine: str) -> str:
    audience = _AUDIENCES.get(engine)
    if audience is None:
        raise ControlledPrivateExecutionError("staging_execution_engine_invalid")
    return ":".join(
        (
            AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
            "staging",
            CALLER_SERVICE_IDENTITY,
            engine,
            audience,
        )
    )


def _planned_timeout(capsule: DispatchInputCapsule) -> int:
    try:
        plan = json.loads(
            capsule.canonical_plan_bytes.decode("ascii"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except ControlledPrivateExecutionError:
        raise ControlledPrivateExecutionError("staging_execution_plan_invalid") from None
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError):
        raise ControlledPrivateExecutionError("staging_execution_plan_invalid") from None
    runs = plan.get("engineRuns") if type(plan) is dict else None
    matches = (
        [
            item
            for item in runs
            if type(item) is dict
            and item.get("engine") == capsule.dispatch_identity.engine
            and item.get("runId") == capsule.dispatch_identity.run_id
        ]
        if type(runs) is list
        else []
    )
    if len(matches) != 1:
        raise ControlledPrivateExecutionError("staging_execution_plan_invalid")
    run = matches[0]
    timeout = run.get("timeoutSeconds")
    if (
        type(timeout) is not int
        or not MIN_ENGINE_TIMEOUT_SECONDS <= timeout <= MAX_ENGINE_TIMEOUT_SECONDS
        or run.get("candidateId") != capsule.dispatch_identity.candidate_id
        or run.get("attemptLimit") != 1
        or run.get("operation") != "transcribe"
    ):
        raise ControlledPrivateExecutionError("staging_execution_plan_invalid")
    return timeout


def _credential(
    resolver: Callable[[str, str], object], engine: str, generation: str
) -> bytes:
    if (
        not callable(resolver)
        or not _matches(_GEN_RE, generation)
        or engine not in _AUDIENCES
    ):
        raise ControlledPrivateExecutionError("staging_execution_credential_invalid")
    try:
        raw = resolver(execution_trigger_credential_key(engine), generation)
    except Exception:
        raise ControlledPrivateExecutionError(
            "staging_execution_credential_unavailable"
        ) from None
    if raw is None or type(raw) not in (bytes, bytearray, memoryview):
        raise ControlledPrivateExecutionError("staging_execution_credential_unavailable")
    try:
        size = raw.nbytes if type(raw) is memoryview else len(raw)
        secret = bytes(raw)
    except (BufferError, TypeError, ValueError):
        raise ControlledPrivateExecutionError(
            "staging_execution_credential_unavailable"
        ) from None
    if not 32 <= size <= 512:
        raise ControlledPrivateExecutionError("staging_execution_credential_unavailable")
    return secret


def build_authenticated_execution_trigger_request(
    *,
    capsule: DispatchInputCapsule,
    generation_id: str,
    credential_resolver: Callable[[str, str], object],
    now_seconds: int,
    nonce: str,
) -> AuthenticatedExecutionTriggerRequest:
    if (
        type(capsule) is not DispatchInputCapsule
        or type(now_seconds) is not int
        or now_seconds < 0
        or not _matches(_NONCE_RE, nonce)
    ):
        raise ControlledPrivateExecutionError("staging_execution_request_invalid")
    try:
        verify_dispatch_input_capsule(capsule)
    except DispatchInputCapsuleError:
        raise ControlledPrivateExecutionError("staging_execution_capsule_invalid") from None
    identity = capsule.dispatch_identity
    timeout = _planned_timeout(capsule)
    secret = _credential(credential_resolver, identity.engine, generation_id)
    body = _canonical(
        {
            "version": AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
            "environment": "staging",
            "engine": identity.engine,
            "jobId": identity.job_id,
            "runId": identity.run_id,
            "dispatchIdentitySha256": identity.identity_sha256,
            "sourceArtifactId": identity.source_artifact_id,
            "sourceSha256": capsule.source_sha256,
            "candidateId": identity.candidate_id,
            "timeoutSeconds": timeout,
        },
        "staging_execution_request_invalid",
    )
    if not 1 <= len(body) <= MAX_REQUEST_BYTES:
        raise ControlledPrivateExecutionError("staging_execution_request_invalid")
    audience = _AUDIENCES[identity.engine]
    credential_key = execution_trigger_credential_key(identity.engine)
    metadata = _canonical(
        {
            "version": AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
            "environment": "staging",
            "callerIdentity": CALLER_SERVICE_IDENTITY,
            "engine": identity.engine,
            "audienceIdentity": audience,
            "credentialKey": credential_key,
            "method": "POST",
            "path": EXECUTION_TRIGGER_PATH,
            "credentialGenerationId": generation_id,
            "timestamp": now_seconds,
            "nonce": nonce,
            "payloadBytes": len(body),
            "payloadSha256": sha256(body).hexdigest(),
        },
        "staging_execution_request_invalid",
    )
    signature = hmac_new(
        secret,
        b"\0".join((_SIGNATURE_DOMAIN, metadata, body)),
        sha256,
    ).hexdigest()
    headers = (
        ("content-type", "application/json"),
        ("content-length", str(len(body))),
        ("x-scoremosaic-execution-generation", generation_id),
        ("x-scoremosaic-execution-timestamp", str(now_seconds)),
        ("x-scoremosaic-execution-nonce", nonce),
        ("x-scoremosaic-execution-signature", signature),
    )
    return AuthenticatedExecutionTriggerRequest(
        engine=identity.engine,
        generation_id=generation_id,
        timestamp=now_seconds,
        timeout_seconds=timeout,
        nonce_sha256=sha256(nonce.encode("ascii")).hexdigest(),
        payload_sha256=sha256(body).hexdigest(),
        body=body,
        headers=headers,
    )


def _verify_source_claim(
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
    capsule: DispatchInputCapsule,
    result: ControlledPrivateSourceDeliveryResult,
) -> None:
    identity = capsule.dispatch_identity
    key = _source_claim_key(capsule, endpoint)
    if (
        result.claim_key != key
        or result.job_id != identity.job_id
        or result.engine != identity.engine
        or result.run_id != identity.run_id
        or result.dispatch_identity_sha256 != identity.identity_sha256
        or result.source_artifact_id != identity.source_artifact_id
        or result.source_size_bytes != capsule.source_size_bytes
        or result.source_sha256 != capsule.source_sha256
        or result.source_media_type != capsule.source_media_type
        or result.target_origin != endpoint.base_url
        or result.http_status != 201
        or result.source_attempt_count != 1
        or result.reconciliation_required_on_restart is not True
        or result.source_persisted is not True
        or result.engine_execution_allowed is not False
        or result.retry_allowed is not False
        or result.result_persistence_allowed is not False
        or result.post_dispatch_job_mutation_allowed is not False
    ):
        raise ControlledPrivateExecutionError("staging_execution_source_claim_invalid")
    record = {
        "version": CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION,
        "environment": "staging",
        "claimKey": key,
        "jobId": identity.job_id,
        "engine": identity.engine,
        "runId": identity.run_id,
        "dispatchIdentitySha256": identity.identity_sha256,
        "sourceArtifactId": identity.source_artifact_id,
        "sourceSizeBytes": capsule.source_size_bytes,
        "sourceSha256": capsule.source_sha256,
        "sourceMediaType": capsule.source_media_type,
        "targetOrigin": endpoint.base_url,
        "boundaries": dict(_SOURCE_BOUNDARIES),
    }
    try:
        raw = provider._read_file_no_follow(
            _source_claim_path(provider, key),
            max_bytes=_MAX_STATE_RECORD_BYTES,
            overflow_category="staging_state_corrupt",
        )
        stored = _decode_record(raw)
        if (
            type(stored) is not dict
            or _SOURCE_CLAIM_MAC_FIELD not in stored
            or _source_canonical_json(stored) != raw
        ):
            raise ControlledPrivateExecutionError(
                "staging_execution_source_claim_invalid"
            )
        observed = stored.get(_SOURCE_CLAIM_MAC_FIELD)
        unsealed = dict(stored)
        unsealed.pop(_SOURCE_CLAIM_MAC_FIELD, None)
        if (
            type(observed) is not str
            or not compare_digest(observed, _source_claim_mac(provider, unsealed))
            or unsealed != record
        ):
            raise ControlledPrivateExecutionError(
                "staging_execution_source_claim_invalid"
            )
    except ControlledPrivateExecutionError:
        raise
    except (ControlledPrivateSourceDeliveryError, MinimumStagingVerticalSliceError):
        raise ControlledPrivateExecutionError(
            "staging_execution_source_claim_invalid"
        ) from None


def _claim_key(
    capsule: DispatchInputCapsule, endpoint: EngineEndpoint, timeout: int
) -> str:
    identity = capsule.dispatch_identity
    return sha256(
        "\x1f".join(
            (
                CONTROLLED_PRIVATE_EXECUTION_VERSION,
                identity.job_id,
                identity.run_id,
                identity.identity_sha256,
                identity.source_artifact_id,
                capsule.source_sha256,
                identity.candidate_id,
                str(timeout),
                endpoint.base_url,
            )
        ).encode("utf-8")
    ).hexdigest()


def _claim_mac(provider: StagingUploadProvider, record: dict[str, Any]) -> str:
    key = getattr(provider, "_state_integrity_key", None)
    if type(key) is not bytes or len(key) != 32:
        raise ControlledPrivateExecutionError("staging_execution_state_invalid")
    return hmac_new(
        key,
        b"\0".join(
            (_CLAIM_DOMAIN, _canonical(record, "staging_execution_state_invalid"))
        ),
        sha256,
    ).hexdigest()


def _reserve_claim(
    provider: StagingUploadProvider,
    capsule: DispatchInputCapsule,
    endpoint: EngineEndpoint,
    timeout: int,
) -> str:
    identity = capsule.dispatch_identity
    key = _claim_key(capsule, endpoint, timeout)
    record = {
        "version": CONTROLLED_PRIVATE_EXECUTION_VERSION,
        "environment": "staging",
        "claimKey": key,
        "jobId": identity.job_id,
        "engine": identity.engine,
        "runId": identity.run_id,
        "dispatchIdentitySha256": identity.identity_sha256,
        "sourceArtifactId": identity.source_artifact_id,
        "sourceSha256": capsule.source_sha256,
        "candidateId": identity.candidate_id,
        "timeoutSeconds": timeout,
        "targetOrigin": endpoint.base_url,
        "boundaries": {
            "automaticRetryAllowed": False,
            "restartReexecutionAllowed": False,
            "redirectAllowed": False,
            "proxyRoutingAllowed": False,
            "resultReturnAllowed": False,
            "resultPersistenceAllowed": False,
            "postDispatchJobMutationAllowed": False,
            "reconciliationRequired": True,
        },
    }
    sealed = dict(record)
    sealed[_CLAIM_MAC_FIELD] = _claim_mac(provider, record)
    payload = _canonical(sealed, "staging_execution_state_invalid")
    if len(payload) > _MAX_STATE_RECORD_BYTES:
        raise ControlledPrivateExecutionError("staging_execution_state_invalid")
    path = (
        provider._root
        / "state"
        / "execution_trigger_claims"
        / key[:2]
        / f"{key}.json"
    )
    try:
        if provider._atomic_create(path, payload):
            return key
        raw = provider._read_file_no_follow(
            path,
            max_bytes=_MAX_STATE_RECORD_BYTES,
            overflow_category="staging_state_corrupt",
        )
        stored = _decode_record(raw)
    except MinimumStagingVerticalSliceError:
        raise ControlledPrivateExecutionError("staging_execution_state_invalid") from None
    if (
        type(stored) is not dict
        or _CLAIM_MAC_FIELD not in stored
        or _canonical(stored, "staging_execution_state_invalid") != raw
    ):
        raise ControlledPrivateExecutionError("staging_execution_state_invalid")
    observed = stored.get(_CLAIM_MAC_FIELD)
    unsealed = dict(stored)
    unsealed.pop(_CLAIM_MAC_FIELD, None)
    if (
        type(observed) is not str
        or not compare_digest(observed, _claim_mac(provider, unsealed))
        or unsealed != record
    ):
        raise ControlledPrivateExecutionError("staging_execution_state_invalid")
    raise ControlledPrivateExecutionError("staging_execution_reconciliation_required")


def _default_post(
    origin: str,
    path: str,
    headers: tuple[tuple[str, str], ...],
    body: bytes,
    connect_timeout: int,
    response_timeout: int,
) -> PrivateExecutionHttpResponse:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "http"
        or parsed.hostname is None
        or parsed.port is None
        or path != EXECUTION_TRIGGER_PATH
        or connect_timeout != CONNECT_TIMEOUT_SECONDS
        or not MIN_ENGINE_TIMEOUT_SECONDS + RESPONSE_TIMEOUT_GRACE_SECONDS
        <= response_timeout
        <= MAX_RESPONSE_TIMEOUT_SECONDS
    ):
        raise ControlledPrivateExecutionError(
            "staging_execution_transport_target_invalid"
        )
    connection = HTTPConnection(
        parsed.hostname,
        parsed.port,
        timeout=connect_timeout,
    )
    try:
        connection.connect()
        if connection.sock is None:
            raise OSError("execution_socket_unavailable")
        connection.sock.settimeout(response_timeout)
        connection.request("POST", path, body=body, headers=dict(headers))
        response: HTTPResponse = connection.getresponse()
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ControlledPrivateExecutionError("staging_execution_response_too_large")
        return PrivateExecutionHttpResponse(
            status=int(response.status),
            content_type=response.getheader("Content-Type", ""),
            body=raw,
            location=response.getheader("Location"),
        )
    except ControlledPrivateExecutionError:
        raise
    except (TimeoutError, socket.timeout, OSError):
        raise ControlledPrivateExecutionError("staging_execution_transport_failed") from None
    except Exception:
        raise ControlledPrivateExecutionError("staging_execution_transport_failed") from None
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _accepted(
    response: PrivateExecutionHttpResponse,
    capsule: DispatchInputCapsule,
    request: AuthenticatedExecutionTriggerRequest,
) -> None:
    if 300 <= response.status <= 399 or response.location is not None:
        raise ControlledPrivateExecutionError("staging_execution_redirect_forbidden")
    if response.status != 200:
        raise ControlledPrivateExecutionError("staging_execution_receiver_rejected")
    if response.content_type != "application/json; charset=utf-8":
        raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    try:
        value = json.loads(
            response.body.decode("ascii"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except ControlledPrivateExecutionError:
        raise ControlledPrivateExecutionError("staging_execution_response_invalid") from None
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError):
        raise ControlledPrivateExecutionError("staging_execution_response_invalid") from None
    if type(value) is not dict or set(value) != {
        "status",
        "kind",
        "evidence",
        "engineExecutionPerformed",
        "resultReturnAllowed",
        "resultPersistenceAllowed",
    }:
        raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    evidence = value.get("evidence")
    identity = capsule.dispatch_identity
    expected_evidence = {
        "version",
        "environment",
        "engine",
        "jobId",
        "runId",
        "dispatchIdentitySha256",
        "sourceArtifactId",
        "sourceSha256",
        "candidateId",
        "timeoutSeconds",
        "credentialGenerationId",
        "timestamp",
        "nonceSha256",
        "payloadSha256",
        "replayKey",
        "receiverAuthenticated",
        "engineExecutionPerformed",
        "retryAllowed",
        "resultReturnAllowed",
        "resultPersistenceAllowed",
        "gatewayStateMutationAllowed",
        "execution",
    }
    if (
        value.get("status") != "executed"
        or value.get("kind") != "execution"
        or value.get("engineExecutionPerformed") is not True
        or value.get("resultReturnAllowed") is not False
        or value.get("resultPersistenceAllowed") is not False
        or type(evidence) is not dict
        or set(evidence) != expected_evidence
        or evidence.get("version") != AUTHENTICATED_EXECUTION_TRIGGER_VERSION
        or evidence.get("environment") != "staging"
        or evidence.get("engine") != identity.engine
        or evidence.get("jobId") != identity.job_id
        or evidence.get("runId") != identity.run_id
        or evidence.get("dispatchIdentitySha256") != identity.identity_sha256
        or evidence.get("sourceArtifactId") != identity.source_artifact_id
        or evidence.get("sourceSha256") != capsule.source_sha256
        or evidence.get("candidateId") != identity.candidate_id
        or evidence.get("timeoutSeconds") != request.timeout_seconds
        or evidence.get("credentialGenerationId") != request.generation_id
        or evidence.get("timestamp") != request.timestamp
        or evidence.get("nonceSha256") != request.nonce_sha256
        or evidence.get("payloadSha256") != request.payload_sha256
        or not _matches(_SHA_RE, evidence.get("replayKey"))
        or evidence.get("receiverAuthenticated") is not True
        or evidence.get("engineExecutionPerformed") is not True
        or evidence.get("retryAllowed") is not False
        or evidence.get("resultReturnAllowed") is not False
        or evidence.get("resultPersistenceAllowed") is not False
        or evidence.get("gatewayStateMutationAllowed") is not False
    ):
        raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    execution = evidence.get("execution")
    expected_execution = {
        "version",
        "environment",
        "engine",
        "jobId",
        "runId",
        "dispatchIdentitySha256",
        "sourceArtifactId",
        "sourceSha256",
        "sourceMediaType",
        "candidateId",
        "claimKey",
        "outputCount",
        "outputs",
        "executionAttemptCount",
        "engineExecutionPerformed",
        "automaticRetryAllowed",
        "restartReexecutionAllowed",
        "resultReturnAllowed",
        "resultPersistenceAllowed",
        "gatewayStateMutationAllowed",
        "reconciliationRequiredOnRestart",
    }
    if (
        type(execution) is not dict
        or set(execution) != expected_execution
        or execution.get("version") != "scoremosaic-controlled-engine-execution-v1"
        or execution.get("environment") != "staging"
        or execution.get("engine") != identity.engine
        or execution.get("jobId") != identity.job_id
        or execution.get("runId") != identity.run_id
        or execution.get("dispatchIdentitySha256") != identity.identity_sha256
        or execution.get("sourceArtifactId") != identity.source_artifact_id
        or execution.get("sourceSha256") != capsule.source_sha256
        or execution.get("sourceMediaType") != capsule.source_media_type
        or execution.get("candidateId") != identity.candidate_id
        or not _matches(_SHA_RE, execution.get("claimKey"))
        or execution.get("executionAttemptCount") != 1
        or execution.get("engineExecutionPerformed") is not True
        or execution.get("automaticRetryAllowed") is not False
        or execution.get("restartReexecutionAllowed") is not False
        or execution.get("resultReturnAllowed") is not False
        or execution.get("resultPersistenceAllowed") is not False
        or execution.get("gatewayStateMutationAllowed") is not False
        or execution.get("reconciliationRequiredOnRestart") is not True
    ):
        raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    outputs = execution.get("outputs")
    if (
        type(outputs) is not list
        or not 1 <= len(outputs) <= 16
        or execution.get("outputCount") != len(outputs)
    ):
        raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    for output in outputs:
        if (
            type(output) is not dict
            or set(output) != {"sizeBytes", "sha256"}
            or type(output.get("sizeBytes")) is not int
            or not 1 <= output["sizeBytes"] <= 64 * 1024 * 1024
            or not _matches(_SHA_RE, output.get("sha256"))
        ):
            raise ControlledPrivateExecutionError("staging_execution_response_invalid")


def execute_controlled_private_engine_once(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
    capsule: DispatchInputCapsule,
    dispatch_result: ControlledPrivateNetworkDispatchResult,
    source_delivery_result: ControlledPrivateSourceDeliveryResult,
    generation_id: str,
    credential_resolver: Callable[[str, str], object],
    now_seconds: int,
    nonce: str,
    transport: ExecutionTransport = _default_post,
) -> ControlledPrivateExecutionResult:
    if (
        type(minimum_slice) is not MinimumStagingVerticalSliceResult
        or type(provider) is not StagingUploadProvider
        or type(dispatch_result) is not ControlledPrivateNetworkDispatchResult
        or type(source_delivery_result) is not ControlledPrivateSourceDeliveryResult
        or type(now_seconds) is not int
        or now_seconds < 0
        or not _matches(_NONCE_RE, nonce)
        or not callable(transport)
    ):
        raise ControlledPrivateExecutionError("staging_execution_input_invalid")
    checked_endpoint = _endpoint(endpoint)
    if type(capsule) is not DispatchInputCapsule:
        raise ControlledPrivateExecutionError("staging_execution_capsule_invalid")
    try:
        verify_dispatch_input_capsule(capsule)
    except DispatchInputCapsuleError:
        raise ControlledPrivateExecutionError("staging_execution_capsule_invalid") from None
    identity = capsule.dispatch_identity
    if identity.engine != checked_endpoint.name:
        raise ControlledPrivateExecutionError("staging_execution_capsule_invalid")
    if (
        dispatch_result.job_id != identity.job_id
        or dispatch_result.engine != identity.engine
        or dispatch_result.run_id != identity.run_id
        or dispatch_result.dispatch_identity_sha256 != identity.identity_sha256
        or dispatch_result.target_origin != checked_endpoint.base_url
        or dispatch_result.network_dispatch_performed is not True
        or dispatch_result.receiver_authenticated is not True
        or dispatch_result.trusted_plan_provisioned is not True
        or dispatch_result.source_transfer_allowed is not False
        or dispatch_result.engine_execution_allowed is not False
        or dispatch_result.result_persistence_allowed is not False
        or dispatch_result.retry_allowed is not False
        or dispatch_result.redirect_allowed is not False
        or dispatch_result.post_dispatch_job_mutation_allowed is not False
        or dispatch_result.reconciliation_required_on_restart is not True
    ):
        raise ControlledPrivateExecutionError(
            "staging_execution_dispatch_evidence_invalid"
        )
    if (
        source_delivery_result.job_id != identity.job_id
        or source_delivery_result.engine != identity.engine
        or source_delivery_result.run_id != identity.run_id
        or source_delivery_result.dispatch_identity_sha256 != identity.identity_sha256
        or source_delivery_result.source_artifact_id != identity.source_artifact_id
        or source_delivery_result.source_size_bytes != capsule.source_size_bytes
        or source_delivery_result.source_sha256 != capsule.source_sha256
        or source_delivery_result.source_media_type != capsule.source_media_type
        or source_delivery_result.target_origin != checked_endpoint.base_url
        or source_delivery_result.source_persisted is not True
        or source_delivery_result.engine_execution_allowed is not False
        or source_delivery_result.retry_allowed is not False
        or source_delivery_result.result_persistence_allowed is not False
        or source_delivery_result.post_dispatch_job_mutation_allowed is not False
        or source_delivery_result.reconciliation_required_on_restart is not True
    ):
        raise ControlledPrivateExecutionError("staging_execution_source_evidence_invalid")
    _verify_source_claim(
        provider,
        checked_endpoint,
        capsule,
        source_delivery_result,
    )
    timeout = _planned_timeout(capsule)
    try:
        recovery = recover_controlled_staging_dispatching_run(
            minimum_slice=minimum_slice,
            provider=provider,
            endpoint=checked_endpoint,
        )
    except ControlledStagingDispatchingTransitionError:
        raise ControlledPrivateExecutionError(
            "staging_execution_durable_state_invalid"
        ) from None
    if (
        recovery.state != "dispatching"
        or recovery.revision != 2
        or recovery.disposition != "reconciliation_required"
        or recovery.reconciliation_required is not True
        or recovery.retry_allowed
        or recovery.network_dispatch_allowed
        or recovery.automatic_execution_allowed
        or recovery.state_mutation_allowed
    ):
        raise ControlledPrivateExecutionError("staging_execution_durable_state_invalid")
    request = build_authenticated_execution_trigger_request(
        capsule=capsule,
        generation_id=generation_id,
        credential_resolver=credential_resolver,
        now_seconds=now_seconds,
        nonce=nonce,
    )
    if request.timeout_seconds != timeout:
        raise ControlledPrivateExecutionError("staging_execution_request_invalid")
    claim = _reserve_claim(provider, capsule, checked_endpoint, timeout)
    response_timeout = timeout + RESPONSE_TIMEOUT_GRACE_SECONDS
    if not (
        MIN_ENGINE_TIMEOUT_SECONDS + RESPONSE_TIMEOUT_GRACE_SECONDS
        <= response_timeout
        <= MAX_RESPONSE_TIMEOUT_SECONDS
    ):
        raise ControlledPrivateExecutionError("staging_execution_timeout_invalid")
    try:
        response = transport(
            checked_endpoint.base_url,
            EXECUTION_TRIGGER_PATH,
            request.headers,
            request.body,
            CONNECT_TIMEOUT_SECONDS,
            response_timeout,
        )
    except ControlledPrivateExecutionError:
        raise
    except Exception:
        raise ControlledPrivateExecutionError("staging_execution_transport_failed") from None
    if type(response) is not PrivateExecutionHttpResponse:
        raise ControlledPrivateExecutionError(
            "staging_execution_transport_response_invalid"
        )
    _accepted(response, capsule, request)
    return ControlledPrivateExecutionResult(
        version=CONTROLLED_PRIVATE_EXECUTION_VERSION,
        job_id=identity.job_id,
        engine=identity.engine,
        run_id=identity.run_id,
        dispatch_identity_sha256=identity.identity_sha256,
        source_artifact_id=identity.source_artifact_id,
        source_sha256=capsule.source_sha256,
        candidate_id=identity.candidate_id,
        target_origin=checked_endpoint.base_url,
        claim_key=claim,
        http_status=200,
        execution_attempt_count=1,
        reconciliation_required_on_restart=True,
    )
