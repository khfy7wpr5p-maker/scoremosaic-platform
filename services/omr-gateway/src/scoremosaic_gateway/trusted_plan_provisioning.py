"""Authenticated trusted-plan provisioning foundation for Stage 4-B.

This module creates one bounded, canonical, HMAC-authenticated control-plane
request that can provision a verified Dispatch Input Capsule's orchestration plan
to the exact engine-owned receiver authority introduced by Stage 4-A.

Provisioning credentials use a separate resolver key/domain from C.1/C.2 dispatch
credentials. Production is deliberately not allowlisted. No HTTP route, network
I/O, retry, engine execution, job mutation, or receiver state mutation occurs here.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from hashlib import sha256
from hmac import new as hmac_new
import hmac
import json
import re
from typing import Any, Callable

from .config import EngineEndpoint
from .dispatch_input_capsule import (
    DispatchInputCapsule,
    DispatchInputCapsuleError,
    MAX_CAPSULE_PLAN_BYTES,
    verify_dispatch_input_capsule,
)
from .dispatch_target import APPROVED_ENGINE_ORIGINS
from .service_auth import (
    CALLER_SERVICE_IDENTITY,
    ENGINE_SERVICE_IDENTITIES,
    MAX_CREDENTIAL_BYTES,
    MIN_CREDENTIAL_BYTES,
)

TRUSTED_PLAN_PROVISIONING_VERSION = "scoremosaic-trusted-plan-provisioning-v1"
TRUSTED_PLAN_PROVISIONING_ALGORITHM = "hmac-sha256"
TRUSTED_PLAN_PROVISIONING_METHOD = "POST"
TRUSTED_PLAN_PROVISIONING_PATH = "/internal/trusted-plan"
MAX_PROVISIONING_REQUEST_BYTES = 128 * 1024
MAX_PROVISIONING_AGE_SECONDS = 60
ALLOWED_PROVISIONING_ENVIRONMENTS = frozenset({"test", "staging"})

_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_PLAN_ID_RE = re.compile(r"plan_[0-9a-f]{24}\Z")


class TrustedPlanProvisioningError(ValueError):
    """Stable fail-closed Stage 4-B provisioning category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class TrustedPlanProvisioningBinding:
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
class TrustedPlanProvisioningCredential:
    binding: TrustedPlanProvisioningBinding
    generation_id: str
    _secret: bytes = field(repr=False)

    def __repr__(self) -> str:
        return (
            "TrustedPlanProvisioningCredential("
            f"engine={self.binding.engine!r}, environment={self.binding.environment!r}, "
            f"generation_id={self.generation_id!r}, secret=<redacted>)"
        )

    def secret_bytes_for_transport(self) -> bytes:
        return bytes(self._secret)


@dataclass(frozen=True, slots=True, repr=False)
class TrustedPlanProvisioningRequest:
    version: str
    engine: str
    job_id: str
    run_id: str
    credential_generation_id: str
    issued_at: int
    canonical_request_sha256: str
    canonical_plan_sha256: str
    canonical_request_bytes: bytes = field(repr=False)
    signature: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.version != TRUSTED_PLAN_PROVISIONING_VERSION
            or self.engine not in ENGINE_SERVICE_IDENTITIES
            or type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.run_id) is not str
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or type(self.credential_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.credential_generation_id) is None
            or type(self.issued_at) is not int
            or self.issued_at < 0
            or type(self.canonical_request_sha256) is not str
            or _SHA256_RE.fullmatch(self.canonical_request_sha256) is None
            or type(self.canonical_plan_sha256) is not str
            or _SHA256_RE.fullmatch(self.canonical_plan_sha256) is None
            or type(self.canonical_request_bytes) is not bytes
            or not 1 <= len(self.canonical_request_bytes) <= MAX_PROVISIONING_REQUEST_BYTES
            or type(self.signature) is not str
            or _SHA256_RE.fullmatch(self.signature) is None
        ):
            raise TrustedPlanProvisioningError("trusted_plan_provisioning_result_invalid")
        if not hmac.compare_digest(
            sha256(self.canonical_request_bytes).hexdigest(),
            self.canonical_request_sha256,
        ):
            raise TrustedPlanProvisioningError("trusted_plan_provisioning_result_invalid")

    def __repr__(self) -> str:
        return (
            "TrustedPlanProvisioningRequest("
            f"version={self.version!r}, engine={self.engine!r}, job_id={self.job_id!r}, "
            f"run_id={self.run_id!r}, credential_generation_id={self.credential_generation_id!r}, "
            f"issued_at={self.issued_at!r}, canonical_request_sha256={self.canonical_request_sha256!r}, "
            f"canonical_plan_sha256={self.canonical_plan_sha256!r}, "
            "canonical_request_bytes=<redacted>, signature=<redacted>)"
        )

    @property
    def credential_export_allowed(self) -> bool:
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
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "credentialGenerationId": self.credential_generation_id,
            "issuedAt": self.issued_at,
            "canonicalRequestSha256": self.canonical_request_sha256,
            "canonicalRequestBytes": len(self.canonical_request_bytes),
            "canonicalPlanSha256": self.canonical_plan_sha256,
            "signaturePresent": True,
            "credentialExportAllowed": False,
            "networkProvisioningAllowed": False,
            "networkDispatchAllowed": False,
            "retryAllowed": False,
            "engineExecutionAllowed": False,
        }


ProvisioningCredentialResolver = Callable[
    [str, str], bytes | bytearray | memoryview | None
]


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


def _credential_key(*, environment: str, engine: str, audience_identity: str) -> str:
    return ":".join(
        (
            TRUSTED_PLAN_PROVISIONING_VERSION,
            environment,
            CALLER_SERVICE_IDENTITY,
            engine,
            audience_identity,
        )
    )


def _require_binding(binding: object) -> TrustedPlanProvisioningBinding:
    if type(binding) is not TrustedPlanProvisioningBinding:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_binding_invalid")
    audience = ENGINE_SERVICE_IDENTITIES.get(binding.engine)
    origins = APPROVED_ENGINE_ORIGINS.get(binding.environment)
    expected_origin = None if origins is None else origins.get(binding.engine)
    expected_key = (
        None
        if audience is None
        else _credential_key(
            environment=binding.environment,
            engine=binding.engine,
            audience_identity=audience,
        )
    )
    if (
        binding.version != TRUSTED_PLAN_PROVISIONING_VERSION
        or binding.environment not in ALLOWED_PROVISIONING_ENVIRONMENTS
        or binding.caller_identity != CALLER_SERVICE_IDENTITY
        or audience is None
        or binding.audience_identity != audience
        or binding.credential_key != expected_key
        or expected_origin is None
        or binding.origin != expected_origin
        or binding.method != TRUSTED_PLAN_PROVISIONING_METHOD
        or binding.path != TRUSTED_PLAN_PROVISIONING_PATH
    ):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_binding_invalid")
    return binding


def build_trusted_plan_provisioning_binding(
    endpoint: EngineEndpoint,
    *,
    environment: str,
) -> TrustedPlanProvisioningBinding:
    if type(endpoint) is not EngineEndpoint or type(endpoint.name) is not str:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_endpoint_invalid")
    audience = ENGINE_SERVICE_IDENTITIES.get(endpoint.name)
    origins = APPROVED_ENGINE_ORIGINS.get(environment)
    expected_origin = None if origins is None else origins.get(endpoint.name)
    if (
        environment not in ALLOWED_PROVISIONING_ENVIRONMENTS
        or audience is None
        or expected_origin is None
        or type(endpoint.base_url) is not str
        or endpoint.base_url != expected_origin
    ):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_endpoint_invalid")
    return _require_binding(
        TrustedPlanProvisioningBinding(
            version=TRUSTED_PLAN_PROVISIONING_VERSION,
            environment=environment,
            caller_identity=CALLER_SERVICE_IDENTITY,
            engine=endpoint.name,
            audience_identity=audience,
            credential_key=_credential_key(
                environment=environment,
                engine=endpoint.name,
                audience_identity=audience,
            ),
            origin=expected_origin,
            method=TRUSTED_PLAN_PROVISIONING_METHOD,
            path=TRUSTED_PLAN_PROVISIONING_PATH,
        )
    )


def resolve_trusted_plan_provisioning_credential(
    binding: TrustedPlanProvisioningBinding,
    *,
    generation_id: str,
    resolver: ProvisioningCredentialResolver,
) -> TrustedPlanProvisioningCredential:
    checked = _require_binding(binding)
    if type(generation_id) is not str or _GENERATION_RE.fullmatch(generation_id) is None:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_generation_invalid")
    if not callable(resolver):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable")
    try:
        raw = resolver(checked.credential_key, generation_id)
    except Exception:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable") from None
    if raw is None or type(raw) not in (bytes, bytearray, memoryview):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable")
    try:
        raw_size = raw.nbytes if type(raw) is memoryview else len(raw)
        secret = bytes(raw)
    except (BufferError, TypeError, ValueError):
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable") from None
    if not MIN_CREDENTIAL_BYTES <= raw_size <= MAX_CREDENTIAL_BYTES:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_unavailable")
    return TrustedPlanProvisioningCredential(
        binding=checked,
        generation_id=generation_id,
        _secret=secret,
    )


def _require_credential(value: object) -> TrustedPlanProvisioningCredential:
    if type(value) is not TrustedPlanProvisioningCredential:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_invalid")
    binding = _require_binding(value.binding)
    if type(value.generation_id) is not str or _GENERATION_RE.fullmatch(value.generation_id) is None:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_invalid")
    secret = value.secret_bytes_for_transport()
    if type(secret) is not bytes or not MIN_CREDENTIAL_BYTES <= len(secret) <= MAX_CREDENTIAL_BYTES:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_invalid")
    if binding is not value.binding:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_credential_invalid")
    return value


def _require_nonce(value: object) -> str:
    if type(value) is not str or _NONCE_RE.fullmatch(value) is None:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_nonce_invalid")
    return value


def build_trusted_plan_provisioning_request(
    *,
    capsule: DispatchInputCapsule,
    credential: TrustedPlanProvisioningCredential,
    issued_at: int,
    nonce: str,
) -> TrustedPlanProvisioningRequest:
    selected = _require_credential(credential)
    if type(issued_at) is not int or issued_at < 0:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_timestamp_invalid")
    accepted_nonce = _require_nonce(nonce)
    try:
        plan = verify_dispatch_input_capsule(capsule)
    except DispatchInputCapsuleError:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_capsule_invalid") from None
    identity = capsule.dispatch_identity
    if identity.engine != selected.binding.engine:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_engine_mismatch")
    matching_run = next(
        (run for run in plan["engineRuns"] if run.get("engine") == selected.binding.engine),
        None,
    )
    if type(matching_run) is not dict or matching_run.get("runId") != identity.run_id:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_capsule_invalid")
    if not 1 <= len(capsule.canonical_plan_bytes) <= MAX_CAPSULE_PLAN_BYTES:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_plan_invalid")

    body = {
        "version": TRUSTED_PLAN_PROVISIONING_VERSION,
        "algorithm": TRUSTED_PLAN_PROVISIONING_ALGORITHM,
        "environment": selected.binding.environment,
        "callerIdentity": selected.binding.caller_identity,
        "engine": selected.binding.engine,
        "audienceIdentity": selected.binding.audience_identity,
        "credentialKey": selected.binding.credential_key,
        "credentialGenerationId": selected.generation_id,
        "origin": selected.binding.origin,
        "method": selected.binding.method,
        "path": selected.binding.path,
        "issuedAt": issued_at,
        "nonce": accepted_nonce,
        "jobId": identity.job_id,
        "runId": identity.run_id,
        "orchestrationPlanId": identity.plan_id,
        "orchestrationPlanSha256": identity.plan_sha256,
        "canonicalPlanSha256": capsule.canonical_plan_sha256,
        "canonicalPlanBytes": len(capsule.canonical_plan_bytes),
        "canonicalPlanB64": base64.b64encode(capsule.canonical_plan_bytes).decode("ascii"),
    }
    canonical = _canonical_json_bytes(body)
    if not 1 <= len(canonical) <= MAX_PROVISIONING_REQUEST_BYTES:
        raise TrustedPlanProvisioningError("trusted_plan_provisioning_request_size_invalid")
    signature = hmac_new(
        selected.secret_bytes_for_transport(),
        canonical,
        sha256,
    ).hexdigest()
    return TrustedPlanProvisioningRequest(
        version=TRUSTED_PLAN_PROVISIONING_VERSION,
        engine=selected.binding.engine,
        job_id=identity.job_id,
        run_id=identity.run_id,
        credential_generation_id=selected.generation_id,
        issued_at=issued_at,
        canonical_request_sha256=sha256(canonical).hexdigest(),
        canonical_plan_sha256=capsule.canonical_plan_sha256,
        canonical_request_bytes=canonical,
        signature=signature,
    )
