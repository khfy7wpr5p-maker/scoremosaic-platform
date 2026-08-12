"""Provider-neutral external principal authentication contract for Gate E.1.

This module is deliberately disconnected from HTTP routing and provider SDKs. It
accepts one server-owned authentication policy, bounded opaque credential bytes,
and a verifier callback supplied by a later provider adapter. Successful
verification creates identity evidence only; it grants no authorization, upload,
job-creation, network-dispatch, or orchestration authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Callable


EXTERNAL_AUTH_CONTRACT_VERSION = "scoremosaic-external-auth-v1"
ALLOWED_ENVIRONMENTS = frozenset({"test", "staging", "production"})
MAX_PROVIDER_ID_LENGTH = 64
MAX_SUBJECT_ID_LENGTH = 128
MAX_CREDENTIAL_BYTES = 16_384
MAX_TIMESTAMP = (1 << 63) - 1

_PROVIDER_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_SUBJECT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@|+\-]{0,127}\Z")


class ExternalAuthError(ValueError):
    """Stable fail-closed external authentication-contract failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_canonical_provider_id(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= MAX_PROVIDER_ID_LENGTH
        and _PROVIDER_ID_RE.fullmatch(value) is not None
    )


def _is_canonical_subject_id(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= MAX_SUBJECT_ID_LENGTH
        and _SUBJECT_ID_RE.fullmatch(value) is not None
    )


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIMESTAMP


@dataclass(frozen=True, slots=True)
class ExternalAuthPolicy:
    """Server-owned provider allowlist for one deployment environment.

    The contract intentionally has no default provider list. A later provider
    integration must construct this policy from server configuration rather than
    accepting it from an external request.
    """

    version: str
    environment: str
    allowed_provider_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != EXTERNAL_AUTH_CONTRACT_VERSION:
            raise ExternalAuthError("auth_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalAuthError("environment_not_allowed")
        if type(self.allowed_provider_ids) is not tuple or not self.allowed_provider_ids:
            raise ExternalAuthError("provider_policy_invalid")

        seen: set[str] = set()
        for provider_id in self.allowed_provider_ids:
            if not _is_canonical_provider_id(provider_id):
                raise ExternalAuthError("provider_policy_invalid")
            if provider_id in seen:
                raise ExternalAuthError("provider_policy_invalid")
            seen.add(provider_id)


@dataclass(frozen=True, slots=True)
class VerifiedExternalIdentity:
    """Provider-adapter output which still requires E.1 convergence checks.

    Construction alone is not authentication authority. Only
    :func:`authenticate_external_principal` can turn exact verifier output into an
    authenticated principal after policy, provider, subject, and lifetime checks.
    """

    provider_id: str
    subject_id: str
    issued_at_epoch_s: int
    expires_at_epoch_s: int


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticatedExternalPrincipal:
    """Bounded authentication result with no authorization authority."""

    version: str
    environment: str
    provider_id: str
    subject_id: str
    principal_id: str
    authenticated_at_epoch_s: int
    expires_at_epoch_s: int

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != EXTERNAL_AUTH_CONTRACT_VERSION:
            raise ExternalAuthError("auth_contract_version_mismatch")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise ExternalAuthError("environment_not_allowed")
        if not _is_canonical_provider_id(self.provider_id):
            raise ExternalAuthError("provider_invalid")
        if not _is_canonical_subject_id(self.subject_id):
            raise ExternalAuthError("subject_invalid")
        if not _is_timestamp(self.authenticated_at_epoch_s):
            raise ExternalAuthError("verification_invalid")
        if not _is_timestamp(self.expires_at_epoch_s):
            raise ExternalAuthError("verification_invalid")
        if self.expires_at_epoch_s <= self.authenticated_at_epoch_s:
            raise ExternalAuthError("credential_expired")

        expected_principal_id = _principal_id(
            version=self.version,
            environment=self.environment,
            provider_id=self.provider_id,
            subject_id=self.subject_id,
        )
        if type(self.principal_id) is not str or self.principal_id != expected_principal_id:
            raise ExternalAuthError("principal_identity_mismatch")

    def __repr__(self) -> str:
        return (
            "AuthenticatedExternalPrincipal("
            f"version={self.version!r}, environment={self.environment!r}, "
            f"provider_id={self.provider_id!r}, principal_id={self.principal_id!r}, "
            "subject_id=<redacted>)"
        )

    def as_safe_dict(self) -> dict[str, str | bool]:
        """Return privacy-bounded identity evidence without credential or subject."""

        return {
            "version": self.version,
            "environment": self.environment,
            "providerId": self.provider_id,
            "principalId": self.principal_id,
            "authenticationState": "authenticated",
            "authorizationGranted": False,
            "uploadAllowed": False,
            "jobCreationAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


ExternalIdentityVerifier = Callable[
    [str, bytes],
    VerifiedExternalIdentity | None,
]


def _credential_bytes(value: object) -> bytes:
    if type(value) not in (bytes, bytearray, memoryview):
        raise ExternalAuthError("credential_invalid")

    try:
        if type(value) is memoryview:
            if value.ndim != 1 or value.itemsize != 1 or value.format not in {"B", "b", "c"}:
                raise ExternalAuthError("credential_invalid")
            size = value.nbytes
        else:
            size = len(value)
    except (BufferError, TypeError, ValueError):
        raise ExternalAuthError("credential_invalid") from None

    if not 1 <= size <= MAX_CREDENTIAL_BYTES:
        raise ExternalAuthError("credential_invalid")

    try:
        return bytes(value)
    except (BufferError, TypeError, ValueError):
        raise ExternalAuthError("credential_invalid") from None


def _principal_id(
    *,
    version: str,
    environment: str,
    provider_id: str,
    subject_id: str,
) -> str:
    payload = b"\0".join(
        (
            version.encode("ascii"),
            environment.encode("ascii"),
            provider_id.encode("ascii"),
            subject_id.encode("ascii"),
        )
    )
    return sha256(payload).hexdigest()


def _validate_verified_identity(
    *,
    identity: VerifiedExternalIdentity,
    provider_id: str,
    observed_at_epoch_s: int,
) -> None:
    if not _is_canonical_provider_id(identity.provider_id):
        raise ExternalAuthError("verification_invalid")
    if identity.provider_id != provider_id:
        raise ExternalAuthError("provider_identity_mismatch")
    if not _is_canonical_subject_id(identity.subject_id):
        raise ExternalAuthError("subject_invalid")
    if not _is_timestamp(identity.issued_at_epoch_s) or not _is_timestamp(
        identity.expires_at_epoch_s
    ):
        raise ExternalAuthError("verification_invalid")
    if identity.expires_at_epoch_s <= identity.issued_at_epoch_s:
        raise ExternalAuthError("verification_invalid")
    if identity.issued_at_epoch_s > observed_at_epoch_s:
        raise ExternalAuthError("credential_not_yet_valid")
    if identity.expires_at_epoch_s <= observed_at_epoch_s:
        raise ExternalAuthError("credential_expired")


def authenticate_external_principal(
    *,
    policy: ExternalAuthPolicy,
    provider_id: str,
    credential: bytes | bytearray | memoryview,
    verifier: ExternalIdentityVerifier,
    observed_at_epoch_s: int,
) -> AuthenticatedExternalPrincipal:
    """Authenticate one external identity without granting any authorization.

    Provider verification is an injected authority seam for a later adapter. The
    presented provider must already be in a server-owned allowlist. Provider
    exceptions are collapsed to one stable category so provider diagnostics and
    credential material never cross this boundary.
    """

    if type(policy) is not ExternalAuthPolicy:
        raise ExternalAuthError("auth_policy_invalid")
    # Re-run policy structural checks so restored/deserialized policy-like data
    # cannot bypass the constructor through object tricks or subclassing.
    policy.__post_init__()

    if not _is_canonical_provider_id(provider_id):
        raise ExternalAuthError("provider_invalid")
    if provider_id not in policy.allowed_provider_ids:
        raise ExternalAuthError("provider_not_allowed")
    if not _is_timestamp(observed_at_epoch_s):
        raise ExternalAuthError("verification_invalid")
    if not callable(verifier):
        raise ExternalAuthError("verifier_invalid")

    credential_bytes = _credential_bytes(credential)

    try:
        verified = verifier(provider_id, credential_bytes)
    except Exception:
        raise ExternalAuthError("authentication_unavailable") from None

    if verified is None:
        raise ExternalAuthError("authentication_failed")
    if type(verified) is not VerifiedExternalIdentity:
        raise ExternalAuthError("verification_invalid")

    _validate_verified_identity(
        identity=verified,
        provider_id=provider_id,
        observed_at_epoch_s=observed_at_epoch_s,
    )

    principal_id = _principal_id(
        version=EXTERNAL_AUTH_CONTRACT_VERSION,
        environment=policy.environment,
        provider_id=verified.provider_id,
        subject_id=verified.subject_id,
    )
    return AuthenticatedExternalPrincipal(
        version=EXTERNAL_AUTH_CONTRACT_VERSION,
        environment=policy.environment,
        provider_id=verified.provider_id,
        subject_id=verified.subject_id,
        principal_id=principal_id,
        authenticated_at_epoch_s=observed_at_epoch_s,
        expires_at_epoch_s=verified.expires_at_epoch_s,
    )
