"""Contract-only service-to-service authentication foundation for Gate C.1.

This module deliberately does not send network requests, read production secrets,
or enable orchestration. It defines fail-closed identity and credential binding that
later Gate C slices can wire into authenticated private transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .config import EngineEndpoint

AUTH_CONTRACT_VERSION = "scoremosaic-s2s-auth-v1"
CALLER_SERVICE_IDENTITY = "scoremosaic-omr-gateway"
ENGINE_SERVICE_IDENTITIES = {
    "audiveris": "scoremosaic-audiveris-foundation",
    "homr": "scoremosaic-homr-foundation",
    "clarity": "scoremosaic-clarity-foundation",
}
ALLOWED_ENVIRONMENTS = frozenset({"test", "staging", "production"})
MIN_CREDENTIAL_BYTES = 32
MAX_CREDENTIAL_BYTES = 512


class ServiceAuthError(ValueError):
    """Safe bounded authentication-contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class EngineAuthBinding:
    """Non-secret identity binding for one Gateway-to-engine relationship."""

    version: str
    environment: str
    caller_identity: str
    engine: str
    audience_identity: str
    credential_key: str

    def as_safe_dict(self) -> dict[str, str]:
        """Return only non-secret evidence suitable for diagnostics."""

        return {
            "version": self.version,
            "environment": self.environment,
            "callerIdentity": self.caller_identity,
            "engine": self.engine,
            "audienceIdentity": self.audience_identity,
            "credentialKey": self.credential_key,
        }


@dataclass(frozen=True, slots=True, repr=False)
class EngineCredential:
    """Opaque credential material whose repr never exposes the secret."""

    binding: EngineAuthBinding
    _secret: bytes = field(repr=False)

    def __repr__(self) -> str:
        return f"EngineCredential(binding={self.binding!r}, secret=<redacted>)"

    def secret_bytes_for_transport(self) -> bytes:
        """Return a defensive copy for a later authenticated transport adapter."""

        return bytes(self._secret)


CredentialResolver = Callable[[str], bytes | bytearray | memoryview | None]


def _credential_key(
    *,
    version: str,
    environment: str,
    caller_identity: str,
    engine: str,
    audience_identity: str,
) -> str:
    return ":".join(
        (
            version,
            environment,
            caller_identity,
            engine,
            audience_identity,
        )
    )


def _validated_resolver_key(binding: EngineAuthBinding) -> str:
    """Re-derive the resolver key only from validated non-secret binding fields."""

    if binding.version != AUTH_CONTRACT_VERSION:
        raise ServiceAuthError("auth_contract_version_mismatch")
    expected_audience = ENGINE_SERVICE_IDENTITIES.get(binding.engine)
    if expected_audience is None:
        raise ServiceAuthError("engine_not_allowed")
    if binding.audience_identity != expected_audience:
        raise ServiceAuthError("audience_identity_mismatch")
    if binding.caller_identity != CALLER_SERVICE_IDENTITY:
        raise ServiceAuthError("caller_identity_mismatch")
    if binding.environment not in ALLOWED_ENVIRONMENTS:
        raise ServiceAuthError("environment_not_allowed")

    expected_key = _credential_key(
        version=AUTH_CONTRACT_VERSION,
        environment=binding.environment,
        caller_identity=CALLER_SERVICE_IDENTITY,
        engine=binding.engine,
        audience_identity=expected_audience,
    )
    if binding.credential_key != expected_key:
        raise ServiceAuthError("credential_key_mismatch")
    return expected_key


def build_engine_auth_binding(
    endpoint: EngineEndpoint,
    environment: str,
) -> EngineAuthBinding:
    """Bind an approved engine endpoint key to one service identity and environment."""

    if endpoint.name not in ENGINE_SERVICE_IDENTITIES:
        raise ServiceAuthError("engine_not_allowed")
    if environment not in ALLOWED_ENVIRONMENTS:
        raise ServiceAuthError("environment_not_allowed")

    audience_identity = ENGINE_SERVICE_IDENTITIES[endpoint.name]
    credential_key = _credential_key(
        version=AUTH_CONTRACT_VERSION,
        environment=environment,
        caller_identity=CALLER_SERVICE_IDENTITY,
        engine=endpoint.name,
        audience_identity=audience_identity,
    )
    return EngineAuthBinding(
        version=AUTH_CONTRACT_VERSION,
        environment=environment,
        caller_identity=CALLER_SERVICE_IDENTITY,
        engine=endpoint.name,
        audience_identity=audience_identity,
        credential_key=credential_key,
    )


def require_binding_for_endpoint(
    binding: EngineAuthBinding,
    endpoint: EngineEndpoint,
) -> None:
    """Reject cross-engine, cross-audience, or resolver-key binding confusion."""

    expected_audience = ENGINE_SERVICE_IDENTITIES.get(endpoint.name)
    if expected_audience is None:
        raise ServiceAuthError("engine_not_allowed")
    if binding.version != AUTH_CONTRACT_VERSION:
        raise ServiceAuthError("auth_contract_version_mismatch")
    if binding.engine != endpoint.name:
        raise ServiceAuthError("engine_identity_mismatch")
    if binding.audience_identity != expected_audience:
        raise ServiceAuthError("audience_identity_mismatch")
    if binding.caller_identity != CALLER_SERVICE_IDENTITY:
        raise ServiceAuthError("caller_identity_mismatch")
    if binding.environment not in ALLOWED_ENVIRONMENTS:
        raise ServiceAuthError("environment_not_allowed")

    expected_key = _credential_key(
        version=AUTH_CONTRACT_VERSION,
        environment=binding.environment,
        caller_identity=CALLER_SERVICE_IDENTITY,
        engine=endpoint.name,
        audience_identity=expected_audience,
    )
    if binding.credential_key != expected_key:
        raise ServiceAuthError("credential_key_mismatch")


def resolve_engine_credential(
    binding: EngineAuthBinding,
    resolver: CredentialResolver,
) -> EngineCredential:
    """Resolve one environment- and engine-scoped opaque credential fail-closed."""

    resolver_key = _validated_resolver_key(binding)
    try:
        raw = resolver(resolver_key)
    except Exception:
        # Provider diagnostics can contain secret material. Never propagate them.
        raise ServiceAuthError("credential_unavailable") from None

    if raw is None:
        raise ServiceAuthError("credential_unavailable")
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise ServiceAuthError("credential_invalid")

    raw_size = raw.nbytes if isinstance(raw, memoryview) else len(raw)
    if not MIN_CREDENTIAL_BYTES <= raw_size <= MAX_CREDENTIAL_BYTES:
        raise ServiceAuthError("credential_invalid")

    secret = bytes(raw)
    return EngineCredential(binding=binding, _secret=secret)
