"""Fail-closed receiver verification adapter foundation for Gate C.2-E.

This module composes the already-completed C.2-B target, C.2-C dispatch identity,
C.2-D credential-generation, and C.2-A authenticated-request contracts into one
receiver-side verification boundary. It deliberately does not register an HTTP
route, execute an OMR engine, send a network request, persist replay state, or
enable orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .authenticated_request import RequestAuthError
from .credential_rotation import (
    CredentialRotationError,
    CredentialRotationSet,
    GenerationBoundRequest,
    GenerationCredential,
    GenerationReplayChecker,
    verify_rotation_authenticated_request,
)
from .dispatch_identity import (
    DispatchIdentityBinding,
    DispatchIdentityError,
    require_authenticated_dispatch_identity,
)
from .dispatch_target import EngineDispatchTarget

RECEIVER_VERIFICATION_CONTRACT_VERSION = "scoremosaic-receiver-verification-v1"


class ReceiverVerificationError(ValueError):
    """Safe bounded Gate C.2-E receiver-verification failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedDispatchRequest:
    """Accepted receiver evidence without retaining raw request bytes or proofs."""

    version: str
    target: EngineDispatchTarget
    dispatch_identity: DispatchIdentityBinding
    generation_credential: GenerationCredential
    request_timestamp: int
    nonce: str
    payload_sha256: str

    def __repr__(self) -> str:
        return (
            "VerifiedDispatchRequest("
            f"version={self.version!r}, engine={self.dispatch_identity.engine!r}, "
            f"environment={self.target.environment!r}, "
            f"job_id={self.dispatch_identity.job_id!r}, "
            f"run_id={self.dispatch_identity.run_id!r}, "
            f"credential_generation_id={self.generation_credential.generation_id!r}, "
            f"request_timestamp={self.request_timestamp!r}, nonce={self.nonce!r}, "
            f"payload_sha256={self.payload_sha256!r}, credential=<redacted>)"
        )

    def as_safe_dict(self) -> dict[str, object]:
        """Return bounded non-secret evidence without request or credential proofs."""

        return {
            "version": self.version,
            "target": self.target.as_safe_dict(),
            "dispatchIdentity": self.dispatch_identity.as_safe_dict(),
            "credentialGenerationId": self.generation_credential.generation_id,
            "requestTimestamp": self.request_timestamp,
            "nonce": self.nonce,
            "payloadSha256": self.payload_sha256,
            "replayCheckPassed": True,
        }


def _raise_receiver_error(exc: Exception) -> None:
    category = getattr(exc, "category", None)
    if type(category) is not str or not category:
        category = "receiver_verification_failed"
    raise ReceiverVerificationError(category) from None


def _require_request_shape(request: Any) -> GenerationBoundRequest:
    if type(request) is not GenerationBoundRequest:
        raise ReceiverVerificationError("generation_request_invalid")
    return request


def _require_verified_binding(
    selected: GenerationCredential,
    target: EngineDispatchTarget,
    identity: DispatchIdentityBinding,
) -> None:
    """Defend the composed boundary against future lower-layer contract drift."""

    binding = selected.binding
    checks = (
        (binding.version, target.binding_version),
        (binding.caller_identity, target.caller_identity),
        (binding.engine, target.engine),
        (binding.audience_identity, target.audience_identity),
        (binding.environment, target.environment),
        (binding.credential_key, target.credential_key),
        (identity.engine, target.engine),
    )
    if any(observed != expected for observed, expected in checks):
        raise ReceiverVerificationError("receiver_binding_mismatch")


def verify_receiver_dispatch_request(
    orchestration_plan: Mapping[str, Any],
    target: EngineDispatchTarget,
    rotation: CredentialRotationSet,
    request: GenerationBoundRequest,
    *,
    observed_method: str,
    observed_path: str,
    payload: bytes,
    now_seconds: int,
    replay_checker: GenerationReplayChecker,
) -> VerifiedDispatchRequest:
    """Converge one private dispatch request into immutable verified evidence.

    Ordering is security-significant:

    1. Require the exact C.2-B target/envelope and C.2-C semantic dispatch payload.
       This is bounded, side-effect free validation and therefore cannot consume a
       replay reservation for a signed but semantically wrong job/source/run.
    2. Verify the C.2-D generation proof and the inner C.2-A HMAC/freshness/actual
       observed method+path. C.2-A reaches the supplied replay callback only after
       those cryptographic and transport-evidence checks succeed.
    3. Return one immutable typed result carrying the exact accepted generation
       credential needed by future C.2-D result verification.

    The adapter neither retains the raw payload nor invokes any engine runtime.
    """

    observed_request = _require_request_shape(request)

    try:
        identity = require_authenticated_dispatch_identity(
            orchestration_plan,
            target,
            observed_request.envelope,
            payload,
        )
    except DispatchIdentityError as exc:
        _raise_receiver_error(exc)

    try:
        selected = verify_rotation_authenticated_request(
            rotation,
            observed_request,
            observed_method=observed_method,
            observed_path=observed_path,
            payload=payload,
            now_seconds=now_seconds,
            replay_checker=replay_checker,
        )
    except (CredentialRotationError, RequestAuthError) as exc:
        _raise_receiver_error(exc)

    _require_verified_binding(selected, target, identity)

    envelope = observed_request.envelope
    return VerifiedDispatchRequest(
        version=RECEIVER_VERIFICATION_CONTRACT_VERSION,
        target=target,
        dispatch_identity=identity,
        generation_credential=selected,
        request_timestamp=envelope.timestamp,
        nonce=envelope.nonce,
        payload_sha256=envelope.payload_sha256,
    )
