"""Engine-side authenticated trusted-plan provisioning boundary for Stage 4-B.

The boundary accepts only one canonical provisioning request produced for this
exact engine, verifies deterministic orchestration semantics, freshness, a
purpose-specific provisioning credential, and the request HMAC, then delegates
the sole durable mutation to Stage 4-A's create-once EngineReceiverAuthority.

It registers no HTTP route and grants no network dispatch, retry, job mutation,
credential export, or engine execution authority.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import re
from typing import Any, Callable

from .receiver_authority import (
    ENGINE_NAME,
    EngineReceiverAuthority,
    EngineReceiverAuthorityError,
    MAX_CANONICAL_PLAN_BYTES,
    _validate_trusted_plan,
)

TRUSTED_PLAN_PROVISIONING_VERSION = "scoremosaic-trusted-plan-provisioning-v1"
TRUSTED_PLAN_PROVISIONING_ALGORITHM = "hmac-sha256"
TRUSTED_PLAN_PROVISIONING_METHOD = "POST"
TRUSTED_PLAN_PROVISIONING_PATH = "/internal/trusted-plan"
MAX_PROVISIONING_REQUEST_BYTES = 128 * 1024
MAX_PROVISIONING_AGE_SECONDS = 60
MIN_PROVISIONING_CREDENTIAL_BYTES = 32
MAX_PROVISIONING_CREDENTIAL_BYTES = 512
CALLER_SERVICE_IDENTITY = "scoremosaic-omr-gateway"

_ENGINE_CONFIG = {
    "audiveris": (
        "scoremosaic-audiveris-foundation",
        "http://audiveris-foundation:8082",
    ),
    "homr": (
        "scoremosaic-homr-foundation",
        "http://homr-foundation:8080",
    ),
    "clarity": (
        "scoremosaic-clarity-foundation",
        "http://clarity-foundation:8081",
    ),
}
_ALLOWED_ENVIRONMENTS = frozenset({"test", "staging"})
_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_PLAN_ID_RE = re.compile(r"plan_[0-9a-f]{24}\Z")

ProvisioningCredentialResolver = Callable[
    [str, str], bytes | bytearray | memoryview | None
]


class TrustedPlanProvisioningError(ValueError):
    """Stable fail-closed receiver provisioning category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class AcceptedTrustedPlanProvisioning:
    version: str
    engine: str
    environment: str
    job_id: str
    run_id: str
    credential_generation_id: str
    issued_at: int
    request_sha256: str
    canonical_plan_sha256: str
    nonce_sha256: str
    persistence_state: str

    def __post_init__(self) -> None:
        if (
            self.version != TRUSTED_PLAN_PROVISIONING_VERSION
            or self.engine != ENGINE_NAME
            or self.environment not in _ALLOWED_ENVIRONMENTS
            or type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.run_id) is not str
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or type(self.credential_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.credential_generation_id) is None
            or type(self.issued_at) is not int
            or self.issued_at < 0
            or type(self.request_sha256) is not str
            or _SHA256_RE.fullmatch(self.request_sha256) is None
            or type(self.canonical_plan_sha256) is not str
            or _SHA256_RE.fullmatch(self.canonical_plan_sha256) is None
            or type(self.nonce_sha256) is not str
            or _SHA256_RE.fullmatch(self.nonce_sha256) is None
            or self.persistence_state != "written"
        ):
            raise TrustedPlanProvisioningError("trusted_plan_provisioning_result_invalid")

    @property
    def authenticated(self) -> bool:
        return True

    @property
    def credential_export_allowed(self) -> bool:
        return False

    @property
    def raw_plan_export_allowed(self) -> bool:
        return False

    @property
    def network_provisioning_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
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
            "engine": self.engine,
            "environment": self.environment,
            "jobId": self.job_id,
            "runId": self.run_id,
            "credentialGenerationId": self.credential_generation_id,
            "issuedAt": self.issued_at,
            "requestSha256": self.request_sha256,
            "canonicalPlanSha256": self.canonical_plan_sha256,
            "nonceSha256": self.nonce_sha256,
            "persistenceState": self.persistence_state,
            "authenticated": True,
            "credentialExportAllowed": False,
            "rawPlanExportAllowed": False,
            "networkProvisioningAllowed": False,
            "networkDispatchAllowed": False,
            "retryAllowed": False,
            "jobStateMutationAllowed": False,
            "engineExecutionAllowed": False,
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
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_json_invalid") from None


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise TrustedPlanProvisioningError("trusted_plan_provisioning_json_invalid")
        result[key] = value
    return result


def _decode_canonical_request(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_PROVISIONING_REQUEST_BYTES:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_request_invalid")
    try:
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except TrustedPlanProvisioningError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_json_invalid") from None
    if type(value) is not dict or not compare_digest(_canonical_json_bytes(value), raw):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_json_invalid")
    return value


def _credential_key(*, environment: str, audience_identity: str) -> str:
    return ":".join(
        (
            TRUSTED_PLAN_PROVISIONING_VERSION,
            environment,
            CALLER_SERVICE_IDENTITY,
            ENGINE_NAME,
            audience_identity,
        )
    )


def _resolve_secret(
    credential_key: str,
    generation_id: str,
    resolver: ProvisioningCredentialResolver,
) -> bytes:
    if not callable(resolver):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable")
    try:
        raw = resolver(credential_key, generation_id)
    except Exception:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable") from None
    if raw is None or type(raw) not in (bytes, bytearray, memoryview):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable")
    try:
        raw_size = raw.nbytes if type(raw) is memoryview else len(raw)
        secret = bytes(raw)
    except (BufferError, TypeError, ValueError):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable") from None
    if not MIN_PROVISIONING_CREDENTIAL_BYTES <= raw_size <= MAX_PROVISIONING_CREDENTIAL_BYTES:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable")
    return secret


def _validated_body(
    request_bytes: bytes,
    *,
    now_seconds: int,
) -> tuple[dict[str, Any], bytes]:
    body = _decode_canonical_request(request_bytes)
    required = {
        "version",
        "algorithm",
        "environment",
        "callerIdentity",
        "engine",
        "audienceIdentity",
        "credentialKey",
        "credentialGenerationId",
        "origin",
        "method",
        "path",
        "issuedAt",
        "nonce",
        "jobId",
        "runId",
        "orchestrationPlanId",
        "orchestrationPlanSha256",
        "canonicalPlanSha256",
        "canonicalPlanBytes",
        "canonicalPlanB64",
    }
    audience, origin = _ENGINE_CONFIG[ENGINE_NAME]
    environment = body.get("environment")
    generation = body.get("credentialGenerationId")
    issued_at = body.get("issuedAt")
    nonce = body.get("nonce")
    job_id = body.get("jobId")
    run_id = body.get("runId")
    plan_id = body.get("orchestrationPlanId")
    plan_sha = body.get("orchestrationPlanSha256")
    canonical_sha = body.get("canonicalPlanSha256")
    canonical_size = body.get("canonicalPlanBytes")
    encoded = body.get("canonicalPlanB64")

    if (
        set(body) != required
        or body.get("version") != TRUSTED_PLAN_PROVISIONING_VERSION
        or body.get("algorithm") != TRUSTED_PLAN_PROVISIONING_ALGORITHM
        or environment not in _ALLOWED_ENVIRONMENTS
        or body.get("callerIdentity") != CALLER_SERVICE_IDENTITY
        or body.get("engine") != ENGINE_NAME
        or body.get("audienceIdentity") != audience
        or body.get("credentialKey") != _credential_key(
            environment=environment,
            audience_identity=audience,
        )
        or body.get("origin") != origin
        or body.get("method") != TRUSTED_PLAN_PROVISIONING_METHOD
        or body.get("path") != TRUSTED_PLAN_PROVISIONING_PATH
        or type(generation) is not str
        or _GENERATION_RE.fullmatch(generation) is None
        or type(issued_at) is not int
        or issued_at < 0
        or type(nonce) is not str
        or _NONCE_RE.fullmatch(nonce) is None
        or type(job_id) is not str
        or _JOB_ID_RE.fullmatch(job_id) is None
        or type(run_id) is not str
        or _RUN_ID_RE.fullmatch(run_id) is None
        or type(plan_id) is not str
        or _PLAN_ID_RE.fullmatch(plan_id) is None
        or type(plan_sha) is not str
        or _SHA256_RE.fullmatch(plan_sha) is None
        or type(canonical_sha) is not str
        or _SHA256_RE.fullmatch(canonical_sha) is None
        or type(canonical_size) is not int
        or type(canonical_size) is bool
        or not 1 <= canonical_size <= MAX_CANONICAL_PLAN_BYTES
        or type(encoded) is not str
        or type(now_seconds) is not int
        or now_seconds < 0
    ):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_request_invalid")
    if issued_at > now_seconds:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_not_yet_valid")
    if now_seconds - issued_at > MAX_PROVISIONING_AGE_SECONDS:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_expired")

    try:
        canonical_plan = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_plan_invalid") from None
    if (
        len(canonical_plan) != canonical_size
        or not compare_digest(sha256(canonical_plan).hexdigest(), canonical_sha)
    ):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_plan_invalid")

    try:
        plan = _validate_trusted_plan(canonical_plan, expected_job_id=job_id)
    except EngineReceiverAuthorityError:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_plan_invalid") from None
    matching_run = next(
        (run for run in plan["engineRuns"] if run.get("engine") == ENGINE_NAME),
        None,
    )
    if (
        type(matching_run) is not dict
        or matching_run.get("runId") != run_id
        or plan.get("planId") != plan_id
        or plan.get("planSha256") != plan_sha
    ):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_plan_invalid")
    return body, canonical_plan


def accept_trusted_plan_provisioning(
    *,
    authority: EngineReceiverAuthority,
    request_bytes: bytes,
    signature: str,
    now_seconds: int,
    credential_resolver: ProvisioningCredentialResolver,
) -> AcceptedTrustedPlanProvisioning:
    """Authenticate one provisioning request before create-once trusted-plan state."""

    if type(authority) is not EngineReceiverAuthority or authority.engine != ENGINE_NAME:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_authority_invalid")
    if type(signature) is not str or _SHA256_RE.fullmatch(signature) is None:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_signature_invalid")

    body, canonical_plan = _validated_body(request_bytes, now_seconds=now_seconds)
    credential_key = body["credentialKey"]
    generation_id = body["credentialGenerationId"]
    secret = _resolve_secret(credential_key, generation_id, credential_resolver)
    expected = hmac_new(secret, request_bytes, sha256).hexdigest()
    if not compare_digest(signature, expected):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_signature_invalid")

    try:
        stored = authority.register_trusted_plan(
            job_id=body["jobId"],
            canonical_plan_bytes=canonical_plan,
        )
    except EngineReceiverAuthorityError as exc:
        if exc.category == "receiver_authority_plan_conflict":
            category = "trusted_plan_provisioning_conflict"
        elif exc.category in {
            "receiver_authority_plan_input_invalid",
            "receiver_authority_plan_invalid",
        }:
            category = "trusted_plan_provisioning_plan_invalid"
        else:
            category = "trusted_plan_provisioning_state_invalid"
        raise TrustedPlanProvisioningError(category) from None

    if stored.persistence_state != "written":
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_replay_detected")

    nonce = body["nonce"]
    return AcceptedTrustedPlanProvisioning(
        version=TRUSTED_PLAN_PROVISIONING_VERSION,
        engine=ENGINE_NAME,
        environment=body["environment"],
        job_id=body["jobId"],
        run_id=body["runId"],
        credential_generation_id=generation_id,
        issued_at=body["issuedAt"],
        request_sha256=sha256(request_bytes).hexdigest(),
        canonical_plan_sha256=body["canonicalPlanSha256"],
        nonce_sha256=sha256(nonce.encode("ascii")).hexdigest(),
        persistence_state="written",
    )
