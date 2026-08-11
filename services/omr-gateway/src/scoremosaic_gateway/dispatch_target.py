"""Contract-only engine dispatch target allowlist for Gate C.2-B.

This module deliberately does not send network requests, register engine routes,
resolve credentials, or enable orchestration. It binds an already-validated C.1
service identity to one exact private engine origin and one exact authenticated
request target before C.2-A signing is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlsplit

from .authenticated_request import (
    AuthenticatedRequestEnvelope,
    sign_authenticated_request,
)
from .config import EngineEndpoint
from .service_auth import (
    EngineAuthBinding,
    EngineCredential,
    ENGINE_SERVICE_IDENTITIES,
    ServiceAuthError,
    require_binding_for_endpoint,
)

DISPATCH_TARGET_CONTRACT_VERSION = "scoremosaic-engine-dispatch-target-v1"
DISPATCH_METHOD = "POST"
DISPATCH_PATH = "/internal/transcribe"

# Production is deliberately absent. Gate C.2-B only records the exact private
# origins used by current test/staging foundations; production activation needs
# a separate reviewed allowlist update. Both mapping levels are immutable so an
# importing caller cannot alter this security policy in place at runtime.
APPROVED_ENGINE_ORIGINS = MappingProxyType(
    {
        "test": MappingProxyType(
            {
                "audiveris": "http://audiveris-foundation:8082",
                "homr": "http://homr-foundation:8080",
                "clarity": "http://clarity-foundation:8081",
            }
        ),
        "staging": MappingProxyType(
            {
                "audiveris": "http://audiveris-foundation:8082",
                "homr": "http://homr-foundation:8080",
                "clarity": "http://clarity-foundation:8081",
            }
        ),
    }
)


class DispatchTargetError(ValueError):
    """Safe bounded dispatch-target contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class EngineDispatchTarget:
    """Non-secret exact target for one future private engine request."""

    version: str
    binding_version: str
    caller_identity: str
    engine: str
    audience_identity: str
    environment: str
    credential_key: str
    origin: str
    method: str
    path: str

    def as_safe_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "bindingVersion": self.binding_version,
            "callerIdentity": self.caller_identity,
            "engine": self.engine,
            "audienceIdentity": self.audience_identity,
            "environment": self.environment,
            "credentialKey": self.credential_key,
            "origin": self.origin,
            "method": self.method,
            "path": self.path,
        }


def _require_endpoint_shape(endpoint: EngineEndpoint) -> None:
    if type(endpoint) is not EngineEndpoint:
        raise DispatchTargetError("endpoint_invalid")
    if type(endpoint.name) is not str:
        raise DispatchTargetError("engine_not_allowed")
    if endpoint.name not in ENGINE_SERVICE_IDENTITIES:
        raise DispatchTargetError("engine_not_allowed")
    if type(endpoint.base_url) is not str:
        raise DispatchTargetError("engine_origin_invalid")

    try:
        parsed = urlsplit(endpoint.base_url)
        parsed.port
    except ValueError:
        raise DispatchTargetError("engine_origin_invalid") from None

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise DispatchTargetError("engine_origin_invalid")
    if parsed.username is not None or parsed.password is not None:
        raise DispatchTargetError("engine_origin_invalid")
    if parsed.query or parsed.fragment:
        raise DispatchTargetError("engine_origin_invalid")
    if parsed.path not in {"", "/"}:
        raise DispatchTargetError("engine_origin_invalid")


def _require_allowlisted_origin(binding: EngineAuthBinding, endpoint: EngineEndpoint) -> str:
    environment_origins = APPROVED_ENGINE_ORIGINS.get(binding.environment)
    if environment_origins is None:
        raise DispatchTargetError("dispatch_environment_not_configured")

    expected_origin = environment_origins.get(endpoint.name)
    if expected_origin is None:
        raise DispatchTargetError("engine_not_allowed")
    if endpoint.base_url != expected_origin:
        raise DispatchTargetError("engine_origin_mismatch")
    return expected_origin


def _require_target_integrity(target: EngineDispatchTarget) -> None:
    if type(target) is not EngineDispatchTarget:
        raise DispatchTargetError("dispatch_target_invalid")
    if target.version != DISPATCH_TARGET_CONTRACT_VERSION:
        raise DispatchTargetError("dispatch_target_version_mismatch")
    if target.method != DISPATCH_METHOD:
        raise DispatchTargetError("dispatch_method_mismatch")
    if target.path != DISPATCH_PATH:
        raise DispatchTargetError("dispatch_path_mismatch")

    endpoint = EngineEndpoint(target.engine, target.origin)
    _require_endpoint_shape(endpoint)
    binding = EngineAuthBinding(
        version=target.binding_version,
        environment=target.environment,
        caller_identity=target.caller_identity,
        engine=target.engine,
        audience_identity=target.audience_identity,
        credential_key=target.credential_key,
    )
    try:
        require_binding_for_endpoint(binding, endpoint)
    except ServiceAuthError as exc:
        raise DispatchTargetError(exc.category) from None
    _require_allowlisted_origin(binding, endpoint)


def build_engine_dispatch_target(
    binding: EngineAuthBinding,
    endpoint: EngineEndpoint,
) -> EngineDispatchTarget:
    """Fail closed unless identity, environment, and exact origin are allowlisted."""

    if type(binding) is not EngineAuthBinding:
        raise DispatchTargetError("binding_invalid")
    _require_endpoint_shape(endpoint)

    try:
        require_binding_for_endpoint(binding, endpoint)
    except ServiceAuthError as exc:
        raise DispatchTargetError(exc.category) from None

    expected_origin = _require_allowlisted_origin(binding, endpoint)
    target = EngineDispatchTarget(
        version=DISPATCH_TARGET_CONTRACT_VERSION,
        binding_version=binding.version,
        caller_identity=binding.caller_identity,
        engine=binding.engine,
        audience_identity=binding.audience_identity,
        environment=binding.environment,
        credential_key=binding.credential_key,
        origin=expected_origin,
        method=DISPATCH_METHOD,
        path=DISPATCH_PATH,
    )
    _require_target_integrity(target)
    return target


def require_envelope_for_dispatch_target(
    target: EngineDispatchTarget,
    envelope: AuthenticatedRequestEnvelope,
) -> None:
    """Require a C.2-A envelope to match the exact C.2-B target metadata."""

    _require_target_integrity(target)
    if type(envelope) is not AuthenticatedRequestEnvelope:
        raise DispatchTargetError("envelope_invalid")

    checks = (
        (envelope.binding_version, target.binding_version, "binding_version_mismatch"),
        (envelope.caller_identity, target.caller_identity, "caller_identity_mismatch"),
        (envelope.engine, target.engine, "engine_identity_mismatch"),
        (
            envelope.audience_identity,
            target.audience_identity,
            "audience_identity_mismatch",
        ),
        (envelope.environment, target.environment, "environment_mismatch"),
        (envelope.credential_key, target.credential_key, "credential_key_mismatch"),
        (envelope.method, target.method, "dispatch_method_mismatch"),
        (envelope.path, target.path, "dispatch_path_mismatch"),
    )
    for observed, expected, category in checks:
        if observed != expected:
            raise DispatchTargetError(category)


def sign_authenticated_dispatch_request(
    credential: EngineCredential,
    endpoint: EngineEndpoint,
    *,
    timestamp: int,
    nonce: str,
    payload: bytes,
) -> AuthenticatedRequestEnvelope:
    """Validate the exact target before C.2-A signing touches credential bytes."""

    if type(credential) is not EngineCredential:
        raise DispatchTargetError("credential_invalid")

    target = build_engine_dispatch_target(credential.binding, endpoint)
    envelope = sign_authenticated_request(
        credential,
        method=target.method,
        path=target.path,
        timestamp=timestamp,
        nonce=nonce,
        payload=payload,
    )
    require_envelope_for_dispatch_target(target, envelope)
    return envelope
