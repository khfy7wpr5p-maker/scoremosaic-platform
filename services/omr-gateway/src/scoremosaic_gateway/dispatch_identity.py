"""Contract-only job/source/run/result identity binding for Gate C.2-C.

This module deliberately does not send network requests, register engine routes,
resolve credentials, persist replay state, or enable orchestration. It derives
one closed dispatch-control identity from one detached, verified orchestration
plan snapshot and requires the exact canonical identity bytes to be covered by
the existing C.2-A authenticated envelope and C.2-B target binding.

At a receiver, C.2-A cryptographic verification and replay checking remain a
separate mandatory step. Result identity claims are additionally authenticated
with the same engine-scoped credential binding so an unkeyed digest cannot be
substituted together with modified result bytes.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Any, Mapping

from .authenticated_request import AuthenticatedRequestEnvelope
from .dispatch_target import (
    DispatchTargetError,
    EngineDispatchTarget,
    require_envelope_for_dispatch_target,
)
from .orchestration import (
    ACCEPTED_SOURCE_MEDIA_TYPES,
    ENGINE_NAMES,
    MAX_SOURCE_BYTES,
    OrchestrationContractError,
    verify_orchestration_plan,
)
from .service_auth import (
    EngineAuthBinding,
    EngineCredential,
    MAX_CREDENTIAL_BYTES,
    MIN_CREDENTIAL_BYTES,
    ServiceAuthError,
    _validated_resolver_key,
)

DISPATCH_IDENTITY_CONTRACT_VERSION = "scoremosaic-dispatch-identity-v1"
DISPATCH_RESULT_IDENTITY_CONTRACT_VERSION = "scoremosaic-dispatch-result-identity-v1"
DISPATCH_RESULT_AUTH_VERSION = "scoremosaic-dispatch-result-auth-v1"
DISPATCH_RESULT_AUTH_ALGORITHM = "hmac-sha256"
MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES = 4096
MAX_RESULT_PAYLOAD_BYTES = 200 * 1024 * 1024

_JOB_ID_RE = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_PLAN_ID_RE = re.compile(r"^plan_[a-f0-9]{24}$")
_RUN_ID_RE = re.compile(r"^run_[a-f0-9]{24}$")
_CANDIDATE_ID_RE = re.compile(r"^candidate_[a-f0-9]{24}$")
_ARTIFACT_ID_RE = re.compile(r"^artifact_[a-f0-9]{24}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")


class DispatchIdentityError(ValueError):
    """Safe bounded dispatch identity contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _require_pattern(value: Any, pattern: re.Pattern[str], category: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise DispatchIdentityError(category)
    return value


def _require_ref(value: Any, category: str) -> str:
    if type(value) is not str or _SAFE_REF_RE.fullmatch(value) is None:
        raise DispatchIdentityError(category)
    if value.startswith("/") or "\\" in value or "//" in value:
        raise DispatchIdentityError(category)
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise DispatchIdentityError(category)
    return value


def _require_bytes(
    payload: Any,
    *,
    empty_allowed: bool,
    maximum: int,
    invalid_category: str,
    size_category: str,
) -> bytes:
    if type(payload) is not bytes:
        raise DispatchIdentityError(invalid_category)
    if (not empty_allowed and not payload) or len(payload) > maximum:
        raise DispatchIdentityError(size_category)
    return payload


def _snapshot_orchestration_plan(
    orchestration_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Detach one complete plan snapshot before verification and derivation."""

    if not isinstance(orchestration_plan, Mapping):
        raise DispatchIdentityError("orchestration_plan_invalid")
    try:
        return deepcopy(dict(orchestration_plan))
    except Exception:
        raise DispatchIdentityError("orchestration_plan_invalid") from None


@dataclass(frozen=True, slots=True)
class DispatchIdentityBinding:
    """Immutable semantic identity for exactly one planned engine dispatch."""

    version: str
    plan_id: str
    plan_sha256: str
    job_id: str
    source_artifact_id: str
    source_artifact_ref: str
    source_sha256: str
    source_size_bytes: int
    source_media_type: str
    run_id: str
    engine: str
    candidate_id: str
    candidate_namespace: str
    musicxml_artifact_id: str
    diagnostic_artifact_id: str

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(dispatch_identity_payload(self)).hexdigest()

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "sourceArtifactRef": self.source_artifact_ref,
            "sourceSha256": self.source_sha256,
            "sourceSizeBytes": self.source_size_bytes,
            "sourceMediaType": self.source_media_type,
            "runId": self.run_id,
            "engine": self.engine,
            "candidateId": self.candidate_id,
            "candidateNamespace": self.candidate_namespace,
            "musicxmlArtifactId": self.musicxml_artifact_id,
            "diagnosticArtifactId": self.diagnostic_artifact_id,
            "identitySha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True, repr=False)
class DispatchResultIdentity:
    """Authenticated identity claim for exact bytes returned by one engine run."""

    version: str
    auth_version: str
    auth_algorithm: str
    binding_version: str
    caller_identity: str
    audience_identity: str
    environment: str
    credential_key: str
    dispatch_identity_sha256: str
    plan_id: str
    plan_sha256: str
    job_id: str
    source_artifact_id: str
    source_sha256: str
    run_id: str
    engine: str
    candidate_id: str
    candidate_namespace: str
    musicxml_artifact_id: str
    diagnostic_artifact_id: str
    result_payload_bytes: int
    result_payload_sha256: str
    signature: str

    def __repr__(self) -> str:
        return (
            "DispatchResultIdentity("
            f"version={self.version!r}, auth_version={self.auth_version!r}, "
            f"auth_algorithm={self.auth_algorithm!r}, engine={self.engine!r}, "
            f"environment={self.environment!r}, job_id={self.job_id!r}, "
            f"run_id={self.run_id!r}, candidate_id={self.candidate_id!r}, "
            f"result_payload_bytes={self.result_payload_bytes!r}, "
            f"result_payload_sha256={self.result_payload_sha256!r}, "
            "signature=<redacted>)"
        )

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "authVersion": self.auth_version,
            "authAlgorithm": self.auth_algorithm,
            "bindingVersion": self.binding_version,
            "callerIdentity": self.caller_identity,
            "audienceIdentity": self.audience_identity,
            "environment": self.environment,
            "credentialKey": self.credential_key,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "runId": self.run_id,
            "engine": self.engine,
            "candidateId": self.candidate_id,
            "candidateNamespace": self.candidate_namespace,
            "musicxmlArtifactId": self.musicxml_artifact_id,
            "diagnosticArtifactId": self.diagnostic_artifact_id,
            "resultPayloadBytes": self.result_payload_bytes,
            "resultPayloadSha256": self.result_payload_sha256,
            "signaturePresent": bool(self.signature),
        }


def _require_dispatch_identity_shape(identity: DispatchIdentityBinding) -> None:
    if type(identity) is not DispatchIdentityBinding:
        raise DispatchIdentityError("dispatch_identity_invalid")
    if identity.version != DISPATCH_IDENTITY_CONTRACT_VERSION:
        raise DispatchIdentityError("dispatch_identity_version_mismatch")

    _require_pattern(identity.plan_id, _PLAN_ID_RE, "plan_id_invalid")
    _require_pattern(identity.plan_sha256, _SHA256_RE, "plan_sha256_invalid")
    _require_pattern(identity.job_id, _JOB_ID_RE, "job_id_invalid")
    _require_pattern(
        identity.source_artifact_id,
        _ARTIFACT_ID_RE,
        "source_artifact_id_invalid",
    )
    _require_ref(identity.source_artifact_ref, "source_artifact_ref_invalid")
    _require_pattern(identity.source_sha256, _SHA256_RE, "source_sha256_invalid")
    if (
        type(identity.source_size_bytes) is not int
        or not 1 <= identity.source_size_bytes <= MAX_SOURCE_BYTES
    ):
        raise DispatchIdentityError("source_size_invalid")
    if identity.source_media_type not in ACCEPTED_SOURCE_MEDIA_TYPES:
        raise DispatchIdentityError("source_media_type_invalid")

    _require_pattern(identity.run_id, _RUN_ID_RE, "run_id_invalid")
    if identity.engine not in ENGINE_NAMES:
        raise DispatchIdentityError("engine_invalid")
    _require_pattern(identity.candidate_id, _CANDIDATE_ID_RE, "candidate_id_invalid")
    _require_ref(identity.candidate_namespace, "candidate_namespace_invalid")
    expected_namespace = (
        f"candidates/{identity.job_id}/{identity.engine}/{identity.candidate_id}"
    )
    if identity.candidate_namespace != expected_namespace:
        raise DispatchIdentityError("candidate_namespace_mismatch")

    _require_pattern(
        identity.musicxml_artifact_id,
        _ARTIFACT_ID_RE,
        "musicxml_artifact_id_invalid",
    )
    _require_pattern(
        identity.diagnostic_artifact_id,
        _ARTIFACT_ID_RE,
        "diagnostic_artifact_id_invalid",
    )
    artifact_ids = {
        identity.source_artifact_id,
        identity.musicxml_artifact_id,
        identity.diagnostic_artifact_id,
    }
    if len(artifact_ids) != 3:
        raise DispatchIdentityError("artifact_identity_collision")


def dispatch_identity_payload(identity: DispatchIdentityBinding) -> bytes:
    """Serialize one closed canonical control payload for C.2-A signing."""

    _require_dispatch_identity_shape(identity)
    payload = {
        "version": identity.version,
        "planId": identity.plan_id,
        "planSha256": identity.plan_sha256,
        "jobId": identity.job_id,
        "sourceArtifact": {
            "artifactId": identity.source_artifact_id,
            "artifactRef": identity.source_artifact_ref,
            "sha256": identity.source_sha256,
            "sizeBytes": identity.source_size_bytes,
            "mediaType": identity.source_media_type,
        },
        "engineRun": {
            "runId": identity.run_id,
            "engine": identity.engine,
            "candidateId": identity.candidate_id,
            "candidateNamespace": identity.candidate_namespace,
            "expectedArtifacts": [
                {
                    "kind": "musicxml",
                    "artifactId": identity.musicxml_artifact_id,
                },
                {
                    "kind": "diagnostic",
                    "artifactId": identity.diagnostic_artifact_id,
                },
            ],
        },
    }
    encoded = _canonical_json(payload)
    if not encoded or len(encoded) > MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES:
        raise DispatchIdentityError("dispatch_identity_payload_size_invalid")
    return encoded


def build_dispatch_identity(
    orchestration_plan: Mapping[str, Any],
    engine: str,
) -> DispatchIdentityBinding:
    """Derive one identity from the exact detached plan snapshot that was verified."""

    if type(engine) is not str or engine not in ENGINE_NAMES:
        raise DispatchIdentityError("engine_invalid")

    plan = _snapshot_orchestration_plan(orchestration_plan)
    try:
        verify_orchestration_plan(plan)
    except (OrchestrationContractError, TypeError, ValueError, KeyError):
        raise DispatchIdentityError("orchestration_plan_invalid") from None

    runs = [run for run in plan["engineRuns"] if run["engine"] == engine]
    if len(runs) != 1:
        raise DispatchIdentityError("engine_not_planned")
    run = runs[0]
    source = plan["sourceArtifact"]
    expected_by_kind = {
        artifact["kind"]: artifact for artifact in run["expectedArtifacts"]
    }

    identity = DispatchIdentityBinding(
        version=DISPATCH_IDENTITY_CONTRACT_VERSION,
        plan_id=plan["planId"],
        plan_sha256=plan["planSha256"],
        job_id=plan["jobId"],
        source_artifact_id=source["artifactId"],
        source_artifact_ref=source["artifactRef"],
        source_sha256=source["sha256"],
        source_size_bytes=source["sizeBytes"],
        source_media_type=source["mediaType"],
        run_id=run["runId"],
        engine=run["engine"],
        candidate_id=run["candidateId"],
        candidate_namespace=run["candidateNamespace"],
        musicxml_artifact_id=expected_by_kind["musicxml"]["artifactId"],
        diagnostic_artifact_id=expected_by_kind["diagnostic"]["artifactId"],
    )
    _require_dispatch_identity_shape(identity)
    dispatch_identity_payload(identity)
    return identity


def require_authenticated_dispatch_identity(
    orchestration_plan: Mapping[str, Any],
    target: EngineDispatchTarget,
    envelope: AuthenticatedRequestEnvelope,
    payload: bytes,
) -> DispatchIdentityBinding:
    """Bind C.2-B/C.2-A metadata to the exact planned dispatch identity bytes.

    This validates semantic identity plus envelope payload metadata. A receiver
    must still call ``verify_authenticated_request`` with its credential and
    replay checker to establish cryptographic authenticity before accepting the
    request.
    """

    try:
        require_envelope_for_dispatch_target(target, envelope)
    except DispatchTargetError as exc:
        raise DispatchIdentityError(exc.category) from None

    expected = build_dispatch_identity(orchestration_plan, target.engine)
    body = _require_bytes(
        payload,
        empty_allowed=False,
        maximum=MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES,
        invalid_category="dispatch_identity_payload_invalid",
        size_category="dispatch_identity_payload_size_invalid",
    )
    expected_body = dispatch_identity_payload(expected)
    if not hmac.compare_digest(body, expected_body):
        raise DispatchIdentityError("dispatch_identity_payload_mismatch")

    if type(envelope.payload_bytes) is not int or envelope.payload_bytes != len(body):
        raise DispatchIdentityError("authenticated_payload_size_mismatch")
    observed_digest = hashlib.sha256(body).hexdigest()
    if (
        type(envelope.payload_sha256) is not str
        or not hmac.compare_digest(envelope.payload_sha256, observed_digest)
    ):
        raise DispatchIdentityError("authenticated_payload_digest_mismatch")
    return expected


def _credential_secret_for_result(
    credential: EngineCredential,
    expected_engine: str,
) -> tuple[EngineAuthBinding, bytes]:
    if type(credential) is not EngineCredential:
        raise DispatchIdentityError("credential_invalid")
    try:
        _validated_resolver_key(credential.binding)
    except ServiceAuthError:
        raise DispatchIdentityError("credential_binding_invalid") from None
    if credential.binding.engine != expected_engine:
        raise DispatchIdentityError("credential_engine_mismatch")

    secret = credential.secret_bytes_for_transport()
    if type(secret) is not bytes:
        raise DispatchIdentityError("credential_invalid")
    if not MIN_CREDENTIAL_BYTES <= len(secret) <= MAX_CREDENTIAL_BYTES:
        raise DispatchIdentityError("credential_invalid")
    return credential.binding, secret


def _require_result_identity_shape(result: DispatchResultIdentity) -> None:
    if type(result) is not DispatchResultIdentity:
        raise DispatchIdentityError("result_identity_invalid")
    if result.version != DISPATCH_RESULT_IDENTITY_CONTRACT_VERSION:
        raise DispatchIdentityError("result_identity_version_mismatch")
    if result.auth_version != DISPATCH_RESULT_AUTH_VERSION:
        raise DispatchIdentityError("result_auth_version_mismatch")
    if result.auth_algorithm != DISPATCH_RESULT_AUTH_ALGORITHM:
        raise DispatchIdentityError("result_auth_algorithm_mismatch")

    _require_pattern(
        result.dispatch_identity_sha256,
        _SHA256_RE,
        "result_dispatch_identity_sha256_invalid",
    )
    _require_pattern(result.plan_id, _PLAN_ID_RE, "result_plan_id_invalid")
    _require_pattern(result.plan_sha256, _SHA256_RE, "result_plan_sha256_invalid")
    _require_pattern(result.job_id, _JOB_ID_RE, "result_job_id_invalid")
    _require_pattern(
        result.source_artifact_id,
        _ARTIFACT_ID_RE,
        "result_source_artifact_id_invalid",
    )
    _require_pattern(
        result.source_sha256,
        _SHA256_RE,
        "result_source_sha256_invalid",
    )
    _require_pattern(result.run_id, _RUN_ID_RE, "result_run_id_invalid")
    if result.engine not in ENGINE_NAMES:
        raise DispatchIdentityError("result_engine_invalid")
    _require_pattern(
        result.candidate_id,
        _CANDIDATE_ID_RE,
        "result_candidate_id_invalid",
    )
    _require_ref(result.candidate_namespace, "result_candidate_namespace_invalid")
    _require_pattern(
        result.musicxml_artifact_id,
        _ARTIFACT_ID_RE,
        "result_musicxml_artifact_id_invalid",
    )
    _require_pattern(
        result.diagnostic_artifact_id,
        _ARTIFACT_ID_RE,
        "result_diagnostic_artifact_id_invalid",
    )
    if result.musicxml_artifact_id == result.diagnostic_artifact_id:
        raise DispatchIdentityError("result_artifact_identity_collision")
    if (
        type(result.result_payload_bytes) is not int
        or not 1 <= result.result_payload_bytes <= MAX_RESULT_PAYLOAD_BYTES
    ):
        raise DispatchIdentityError("result_payload_size_invalid")
    _require_pattern(
        result.result_payload_sha256,
        _SHA256_RE,
        "result_payload_sha256_invalid",
    )
    _require_pattern(result.signature, _SHA256_RE, "result_signature_invalid")


def _result_auth_bytes(
    *,
    binding: EngineAuthBinding,
    dispatch_identity_sha256: str,
    plan_id: str,
    plan_sha256: str,
    job_id: str,
    source_artifact_id: str,
    source_sha256: str,
    run_id: str,
    engine: str,
    candidate_id: str,
    candidate_namespace: str,
    musicxml_artifact_id: str,
    diagnostic_artifact_id: str,
    result_payload_bytes: int,
    result_payload_sha256: str,
) -> bytes:
    return _canonical_json(
        {
            "authVersion": DISPATCH_RESULT_AUTH_VERSION,
            "authAlgorithm": DISPATCH_RESULT_AUTH_ALGORITHM,
            "bindingVersion": binding.version,
            "callerIdentity": binding.caller_identity,
            "audienceIdentity": binding.audience_identity,
            "environment": binding.environment,
            "credentialKey": binding.credential_key,
            "resultIdentityVersion": DISPATCH_RESULT_IDENTITY_CONTRACT_VERSION,
            "dispatchIdentitySha256": dispatch_identity_sha256,
            "planId": plan_id,
            "planSha256": plan_sha256,
            "jobId": job_id,
            "sourceArtifactId": source_artifact_id,
            "sourceSha256": source_sha256,
            "runId": run_id,
            "engine": engine,
            "candidateId": candidate_id,
            "candidateNamespace": candidate_namespace,
            "musicxmlArtifactId": musicxml_artifact_id,
            "diagnosticArtifactId": diagnostic_artifact_id,
            "resultPayloadBytes": result_payload_bytes,
            "resultPayloadSha256": result_payload_sha256,
        }
    )


def build_dispatch_result_identity(
    credential: EngineCredential,
    identity: DispatchIdentityBinding,
    result_payload: bytes,
) -> DispatchResultIdentity:
    """Authenticate exact returned bytes and lineage with one engine credential."""

    _require_dispatch_identity_shape(identity)
    binding, secret = _credential_secret_for_result(credential, identity.engine)
    body = _require_bytes(
        result_payload,
        empty_allowed=False,
        maximum=MAX_RESULT_PAYLOAD_BYTES,
        invalid_category="result_payload_invalid",
        size_category="result_payload_size_invalid",
    )
    result_payload_sha256 = hashlib.sha256(body).hexdigest()
    auth_bytes = _result_auth_bytes(
        binding=binding,
        dispatch_identity_sha256=identity.identity_sha256,
        plan_id=identity.plan_id,
        plan_sha256=identity.plan_sha256,
        job_id=identity.job_id,
        source_artifact_id=identity.source_artifact_id,
        source_sha256=identity.source_sha256,
        run_id=identity.run_id,
        engine=identity.engine,
        candidate_id=identity.candidate_id,
        candidate_namespace=identity.candidate_namespace,
        musicxml_artifact_id=identity.musicxml_artifact_id,
        diagnostic_artifact_id=identity.diagnostic_artifact_id,
        result_payload_bytes=len(body),
        result_payload_sha256=result_payload_sha256,
    )
    signature = hmac.new(secret, auth_bytes, hashlib.sha256).hexdigest()
    result = DispatchResultIdentity(
        version=DISPATCH_RESULT_IDENTITY_CONTRACT_VERSION,
        auth_version=DISPATCH_RESULT_AUTH_VERSION,
        auth_algorithm=DISPATCH_RESULT_AUTH_ALGORITHM,
        binding_version=binding.version,
        caller_identity=binding.caller_identity,
        audience_identity=binding.audience_identity,
        environment=binding.environment,
        credential_key=binding.credential_key,
        dispatch_identity_sha256=identity.identity_sha256,
        plan_id=identity.plan_id,
        plan_sha256=identity.plan_sha256,
        job_id=identity.job_id,
        source_artifact_id=identity.source_artifact_id,
        source_sha256=identity.source_sha256,
        run_id=identity.run_id,
        engine=identity.engine,
        candidate_id=identity.candidate_id,
        candidate_namespace=identity.candidate_namespace,
        musicxml_artifact_id=identity.musicxml_artifact_id,
        diagnostic_artifact_id=identity.diagnostic_artifact_id,
        result_payload_bytes=len(body),
        result_payload_sha256=result_payload_sha256,
        signature=signature,
    )
    _require_result_identity_shape(result)
    return result


def require_dispatch_result_identity(
    credential: EngineCredential,
    expected_identity: DispatchIdentityBinding,
    result: DispatchResultIdentity,
    result_payload: bytes,
) -> None:
    """Fail closed unless result lineage, bytes, credential binding, and MAC match."""

    _require_dispatch_identity_shape(expected_identity)
    _require_result_identity_shape(result)
    body = _require_bytes(
        result_payload,
        empty_allowed=False,
        maximum=MAX_RESULT_PAYLOAD_BYTES,
        invalid_category="result_payload_invalid",
        size_category="result_payload_size_invalid",
    )

    dispatch_checks = (
        (result.dispatch_identity_sha256, expected_identity.identity_sha256),
        (result.plan_id, expected_identity.plan_id),
        (result.plan_sha256, expected_identity.plan_sha256),
        (result.job_id, expected_identity.job_id),
        (result.source_artifact_id, expected_identity.source_artifact_id),
        (result.source_sha256, expected_identity.source_sha256),
        (result.run_id, expected_identity.run_id),
        (result.engine, expected_identity.engine),
        (result.candidate_id, expected_identity.candidate_id),
        (result.candidate_namespace, expected_identity.candidate_namespace),
    )
    if any(observed != expected for observed, expected in dispatch_checks):
        raise DispatchIdentityError("result_dispatch_identity_mismatch")

    artifact_checks = (
        (result.musicxml_artifact_id, expected_identity.musicxml_artifact_id),
        (result.diagnostic_artifact_id, expected_identity.diagnostic_artifact_id),
    )
    if any(observed != expected for observed, expected in artifact_checks):
        raise DispatchIdentityError("result_artifact_identity_mismatch")

    if result.result_payload_bytes != len(body):
        raise DispatchIdentityError("result_payload_size_mismatch")
    observed_digest = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(result.result_payload_sha256, observed_digest):
        raise DispatchIdentityError("result_payload_digest_mismatch")

    binding, secret = _credential_secret_for_result(
        credential,
        expected_identity.engine,
    )
    binding_checks = (
        (result.binding_version, binding.version),
        (result.caller_identity, binding.caller_identity),
        (result.audience_identity, binding.audience_identity),
        (result.environment, binding.environment),
        (result.credential_key, binding.credential_key),
    )
    if any(observed != expected for observed, expected in binding_checks):
        raise DispatchIdentityError("result_auth_binding_mismatch")

    auth_bytes = _result_auth_bytes(
        binding=binding,
        dispatch_identity_sha256=result.dispatch_identity_sha256,
        plan_id=result.plan_id,
        plan_sha256=result.plan_sha256,
        job_id=result.job_id,
        source_artifact_id=result.source_artifact_id,
        source_sha256=result.source_sha256,
        run_id=result.run_id,
        engine=result.engine,
        candidate_id=result.candidate_id,
        candidate_namespace=result.candidate_namespace,
        musicxml_artifact_id=result.musicxml_artifact_id,
        diagnostic_artifact_id=result.diagnostic_artifact_id,
        result_payload_bytes=result.result_payload_bytes,
        result_payload_sha256=result.result_payload_sha256,
    )
    expected_signature = hmac.new(secret, auth_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(result.signature, expected_signature):
        raise DispatchIdentityError("result_signature_invalid")
