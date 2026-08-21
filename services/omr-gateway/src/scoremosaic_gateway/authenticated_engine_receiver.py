"""Authenticated engine receiver security foundation for one controlled staging run.

The receiver deliberately keeps the incoming Dispatch Input Capsule untrusted.
It first performs bounded structural/self-consistency checks, resolves an
independent HMAC-protected trusted orchestration plan from receiver-owned state,
requires byte-for-byte plan and C.2-C identity convergence, and only then enters
the existing C.2-E authentication/replay boundary.

No HTTP route, network send, job-state transition, queue/worker runtime, retry,
or engine execution is enabled by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import hmac
from typing import Sequence

from .config import EngineEndpoint
from .controlled_staging_dispatch_wire import (
    ControlledStagingDispatchWireError,
    parse_controlled_staging_dispatch_wire,
)
from .controlled_staging_receiver_preflight import (
    ControlledStagingReceiverPreflightError,
    verify_controlled_staging_receiver_preflight,
)
from .controlled_staging_trusted_plan_store import (
    ControlledStagingTrustedPlanStoreError,
    ControlledStagingTrustedReceiverPlanResolver,
)
from .credential_rotation import CredentialRotationSet
from .dispatch_identity import DispatchIdentityError, dispatch_identity_payload
from .dispatch_input_capsule import (
    DispatchInputCapsule,
    DispatchInputCapsuleError,
    canonical_orchestration_plan_bytes,
    verify_dispatch_input_capsule,
)
from .dispatch_target import (
    DispatchTargetError,
    build_engine_dispatch_target,
)
from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceResult,
    StagingUploadProvider,
)
from .service_auth import ServiceAuthError, build_engine_auth_binding
from .trusted_receiver_plan_lookup import (
    TrustedReceiverPlanLookupError,
    resolve_trusted_receiver_plan,
)


AUTHENTICATED_ENGINE_RECEIVER_VERSION = "scoremosaic-authenticated-engine-receiver-v1"
_AUTHENTICATED_RECEIVER_SEAL = object()


class AuthenticatedEngineReceiverError(ValueError):
    """Stable fail-closed category for the composed receiver boundary."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require_endpoint(value: object) -> EngineEndpoint:
    if type(value) is not EngineEndpoint:
        raise AuthenticatedEngineReceiverError("authenticated_receiver_target_invalid")
    return value


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise AuthenticatedEngineReceiverError("authenticated_receiver_input_invalid")
    return value


def _require_rotation(value: object) -> CredentialRotationSet:
    if type(value) is not CredentialRotationSet:
        raise AuthenticatedEngineReceiverError("authenticated_receiver_credential_invalid")
    return value


def _require_capsule(value: object) -> DispatchInputCapsule:
    if type(value) is not DispatchInputCapsule:
        raise AuthenticatedEngineReceiverError("authenticated_receiver_capsule_invalid")
    return value


def _require_body(value: object) -> bytes:
    if type(value) is not bytes:
        raise AuthenticatedEngineReceiverError("authenticated_receiver_wire_invalid")
    return value


def _require_observed_target(method: object, path: object) -> tuple[str, str]:
    if type(method) is not str or type(path) is not str:
        raise AuthenticatedEngineReceiverError("authenticated_receiver_target_invalid")
    return method, path


def _require_now(value: object) -> int:
    if type(value) is not int or value < 0:
        raise AuthenticatedEngineReceiverError("authenticated_receiver_time_invalid")
    return value


def _safe_compare_bytes(left: bytes, right: bytes) -> bool:
    return len(left) == len(right) and hmac.compare_digest(left, right)


@dataclass(frozen=True, slots=True)
class AuthenticatedEngineReceiverResult:
    """Sealed non-executable evidence that the complete receiver gate passed."""

    version: str
    job_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    canonical_plan_sha256: str
    source_sha256: str
    source_size_bytes: int
    source_media_type: str
    credential_generation_id: str
    authenticated_payload_sha256: str
    replay_reservation_key: str
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _AUTHENTICATED_RECEIVER_SEAL:
            raise AuthenticatedEngineReceiverError("authenticated_receiver_result_invalid")
        if (
            self.version != AUTHENTICATED_ENGINE_RECEIVER_VERSION
            or type(self.job_id) is not str
            or type(self.engine) is not str
            or type(self.run_id) is not str
            or type(self.dispatch_identity_sha256) is not str
            or len(self.dispatch_identity_sha256) != 64
            or type(self.canonical_plan_sha256) is not str
            or len(self.canonical_plan_sha256) != 64
            or type(self.source_sha256) is not str
            or len(self.source_sha256) != 64
            or type(self.source_size_bytes) is not int
            or self.source_size_bytes < 1
            or type(self.source_media_type) is not str
            or type(self.credential_generation_id) is not str
            or type(self.authenticated_payload_sha256) is not str
            or len(self.authenticated_payload_sha256) != 64
            or type(self.replay_reservation_key) is not str
            or len(self.replay_reservation_key) != 64
        ):
            raise AuthenticatedEngineReceiverError("authenticated_receiver_result_invalid")

    @property
    def receiver_authenticated(self) -> bool:
        return True

    @property
    def trusted_plan_converged(self) -> bool:
        return True

    @property
    def capsule_authenticated(self) -> bool:
        return True

    @property
    def replay_reserved(self) -> bool:
        return True

    @property
    def credential_export_allowed(self) -> bool:
        return False

    @property
    def raw_input_export_allowed(self) -> bool:
        return False

    @property
    def job_state_mutation_allowed(self) -> bool:
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
            "environment": "staging",
            "jobId": self.job_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "canonicalPlanSha256": self.canonical_plan_sha256,
            "sourceSha256": self.source_sha256,
            "sourceSizeBytes": self.source_size_bytes,
            "sourceMediaType": self.source_media_type,
            "credentialGenerationId": self.credential_generation_id,
            "authenticatedPayloadSha256": self.authenticated_payload_sha256,
            "replayReservationKey": self.replay_reservation_key,
            "receiverAuthenticated": True,
            "trustedPlanConverged": True,
            "capsuleAuthenticated": True,
            "replayReserved": True,
            "credentialExportAllowed": False,
            "rawInputExportAllowed": False,
            "jobStateMutationAllowed": False,
            "networkDispatchAllowed": False,
            "retryAllowed": False,
            "engineExecutionAllowed": False,
        }


def authenticate_controlled_staging_engine_receiver(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
    rotation: CredentialRotationSet,
    capsule: DispatchInputCapsule,
    headers: Sequence[tuple[str, str]],
    body: bytes,
    observed_method: str,
    observed_path: str,
    now_seconds: int,
) -> AuthenticatedEngineReceiverResult:
    """Converge untrusted capsule + wire into sealed authenticated evidence.

    Security-significant ordering:

    1. Validate the capsule only as untrusted, self-consistent bounded content.
       This has no persistence, replay, credential, network, or execution side effect.
    2. Parse bounded wire framing against the receiver-owned exact target.
    3. Resolve the trusted plan from the receiver-owned HMAC-protected store using
       only the signed C.2-C body as an untrusted lookup hint, then require the
       incoming capsule plan and identity to reproduce that trusted plan exactly.
    4. Only after all plan/source/identity convergence checks pass, invoke the
       existing controlled C.2-E receiver preflight. C.2-E verifies generation,
       HMAC, freshness, observed target, and finally reserves replay state.

    The returned evidence cannot execute an engine or mutate authoritative state.
    """

    checked_provider = _require_provider(provider)
    checked_endpoint = _require_endpoint(endpoint)
    checked_rotation = _require_rotation(rotation)
    checked_capsule = _require_capsule(capsule)
    checked_body = _require_body(body)
    checked_method, checked_path = _require_observed_target(
        observed_method,
        observed_path,
    )
    checked_now = _require_now(now_seconds)

    # Incoming plan/source remain untrusted here. This call proves only internal
    # deterministic/hash/media convergence and performs no side effect.
    try:
        untrusted_plan = verify_dispatch_input_capsule(checked_capsule)
        incoming_plan_bytes = canonical_orchestration_plan_bytes(untrusted_plan)
        incoming_identity_payload = dispatch_identity_payload(
            checked_capsule.dispatch_identity
        )
    except (DispatchInputCapsuleError, DispatchIdentityError, TypeError, ValueError):
        raise AuthenticatedEngineReceiverError(
            "authenticated_receiver_capsule_invalid"
        ) from None

    try:
        auth_binding = build_engine_auth_binding(checked_endpoint, "staging")
        target = build_engine_dispatch_target(auth_binding, checked_endpoint)
    except (ServiceAuthError, DispatchTargetError, TypeError, ValueError):
        raise AuthenticatedEngineReceiverError(
            "authenticated_receiver_target_invalid"
        ) from None

    try:
        request = parse_controlled_staging_dispatch_wire(
            target=target,
            headers=headers,
            body=checked_body,
            observed_method=checked_method,
            observed_path=checked_path,
        )
    except ControlledStagingDispatchWireError:
        raise AuthenticatedEngineReceiverError(
            "authenticated_receiver_wire_invalid"
        ) from None

    try:
        trusted_resolution = resolve_trusted_receiver_plan(
            payload=checked_body,
            expected_engine=checked_endpoint.name,
            resolver=ControlledStagingTrustedReceiverPlanResolver(checked_provider),
        )
        trusted_plan_bytes = canonical_orchestration_plan_bytes(
            trusted_resolution.plan_mapping()
        )
    except (
        TrustedReceiverPlanLookupError,
        ControlledStagingTrustedPlanStoreError,
        DispatchInputCapsuleError,
    ):
        raise AuthenticatedEngineReceiverError(
            "authenticated_receiver_trusted_plan_invalid"
        ) from None

    if (
        not _safe_compare_bytes(incoming_plan_bytes, trusted_plan_bytes)
        or not _safe_compare_bytes(incoming_identity_payload, checked_body)
        or checked_capsule.dispatch_identity.engine != checked_endpoint.name
        or checked_capsule.dispatch_identity.job_id != trusted_resolution.job_id
        or checked_capsule.dispatch_identity.run_id != trusted_resolution.run_id
        or checked_capsule.dispatch_identity.identity_sha256
        != trusted_resolution.dispatch_identity_sha256
        or checked_capsule.canonical_plan_sha256
        != trusted_resolution.canonical_plan_sha256
        or checked_capsule.source_sha256
        != checked_capsule.dispatch_identity.source_sha256
    ):
        raise AuthenticatedEngineReceiverError(
            "authenticated_receiver_convergence_failed"
        )

    try:
        verified = verify_controlled_staging_receiver_preflight(
            minimum_slice=minimum_slice,
            provider=checked_provider,
            endpoint=checked_endpoint,
            rotation=checked_rotation,
            request=request,
            payload=checked_body,
            observed_method=checked_method,
            observed_path=checked_path,
            now_seconds=checked_now,
        )
    except ControlledStagingReceiverPreflightError as exc:
        # Preserve the existing bounded C.2-E category so replay/freshness/
        # generation failures remain observable without exposing secrets.
        raise AuthenticatedEngineReceiverError(exc.category) from None

    if (
        verified.job_id != checked_capsule.dispatch_identity.job_id
        or verified.engine != checked_capsule.dispatch_identity.engine
        or verified.run_id != checked_capsule.dispatch_identity.run_id
        or verified.dispatch_identity_sha256
        != checked_capsule.dispatch_identity.identity_sha256
        or verified.payload_sha256 != sha256(checked_body).hexdigest()
        or verified.payload_bytes != len(checked_body)
        or verified.receiver_verified is not True
        or verified.replay_reserved is not True
    ):
        raise AuthenticatedEngineReceiverError(
            "authenticated_receiver_postauth_convergence_failed"
        )

    return AuthenticatedEngineReceiverResult(
        version=AUTHENTICATED_ENGINE_RECEIVER_VERSION,
        job_id=verified.job_id,
        engine=verified.engine,
        run_id=verified.run_id,
        dispatch_identity_sha256=verified.dispatch_identity_sha256,
        canonical_plan_sha256=checked_capsule.canonical_plan_sha256,
        source_sha256=checked_capsule.source_sha256,
        source_size_bytes=checked_capsule.source_size_bytes,
        source_media_type=checked_capsule.source_media_type,
        credential_generation_id=verified.credential_generation_id,
        authenticated_payload_sha256=verified.payload_sha256,
        replay_reservation_key=verified.replay_reservation_key,
        _seal=_AUTHENTICATED_RECEIVER_SEAL,
    )
