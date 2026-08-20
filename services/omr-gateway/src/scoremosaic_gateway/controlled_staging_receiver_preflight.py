"""Non-network authenticated receiver preflight for one controlled staging run.

This bounded slice composes the already-persisted dispatch intent, exact queued
revision-1 evidence, immutable source guard, C.2-E receiver verification, and the
durable staging replay reservation. It answers only whether one already-signed
request is safe to accept at the receiver boundary.

No HTTP route is registered. No request is sent, no engine is executed, no job
state is advanced, and no worker/orchestration authority is granted. The raw
nonce, signatures, payload bytes, and credential are kept internal; the returned
result contains only bounded non-secret hashes and immutable identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .config import EngineEndpoint
from .controlled_staging_dispatch_intent import (
    ControlledStagingDispatchIntentError,
    _canonical_json_bytes as _intent_canonical_json_bytes,
    _derive_intent,
    _load_and_verify_intent_under_lock,
    _verify_queued_and_not_terminal_under_lock,
)
from .controlled_staging_job_lifecycle import (
    ControlledStagingJobLifecycleError,
    _validated_binding,
)
from .controlled_staging_replay_reservation import (
    ControlledStagingReplayReservationError,
    ControlledStagingReplayReservationResult,
    reserve_controlled_staging_generation_replay,
)
from .controlled_staging_signing_preflight import (
    ControlledStagingSigningPreflightError,
    _existing_job_lock,
)
from .credential_rotation import CredentialRotationSet, GenerationBoundRequest
from .dispatch_identity import (
    MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES,
    DispatchIdentityError,
    build_dispatch_identity,
    dispatch_identity_payload,
)
from .dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    DISPATCH_METHOD,
    DISPATCH_PATH,
    DispatchTargetError,
    build_engine_dispatch_target,
)
from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError,
    MinimumStagingVerticalSliceResult,
    StagingUploadProvider,
)
from .orchestration import ENGINE_NAMES, OrchestrationContractError, build_orchestration_plan
from .receiver_verification import ReceiverVerificationError, verify_receiver_dispatch_request
from .service_auth import ServiceAuthError, build_engine_auth_binding


CONTROLLED_STAGING_RECEIVER_PREFLIGHT_VERSION = (
    "scoremosaic-controlled-staging-receiver-preflight-v1"
)
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


class ControlledStagingReceiverPreflightError(ValueError):
    """Stable fail-closed category for controlled staging receiver acceptance."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ControlledStagingReceiverPreflightResult:
    job_id: str
    source_artifact_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    dispatch_intent_sha256: str
    credential_generation_id: str
    request_timestamp: int
    request_nonce_sha256: str
    payload_bytes: int
    payload_sha256: str
    envelope_signature_sha256: str
    generation_signature_sha256: str
    replay_reservation_key: str
    replay_expires_at: int
    target_origin: str
    target_method: str
    target_path: str
    state: str
    revision: int

    def __post_init__(self) -> None:
        expected_origin = (
            APPROVED_ENGINE_ORIGINS["staging"].get(self.engine)
            if type(self.engine) is str
            else None
        )
        if (
            type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.source_artifact_id) is not str
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.engine) is not str
            or self.engine not in ENGINE_NAMES
            or type(self.run_id) is not str
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or type(self.dispatch_identity_sha256) is not str
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or type(self.dispatch_intent_sha256) is not str
            or _SHA256_RE.fullmatch(self.dispatch_intent_sha256) is None
            or type(self.credential_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.credential_generation_id) is None
            or type(self.request_timestamp) is not int
            or self.request_timestamp < 0
            or type(self.request_nonce_sha256) is not str
            or _SHA256_RE.fullmatch(self.request_nonce_sha256) is None
            or type(self.payload_bytes) is not int
            or not 1 <= self.payload_bytes <= MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
            or type(self.payload_sha256) is not str
            or _SHA256_RE.fullmatch(self.payload_sha256) is None
            or type(self.envelope_signature_sha256) is not str
            or _SHA256_RE.fullmatch(self.envelope_signature_sha256) is None
            or type(self.generation_signature_sha256) is not str
            or _SHA256_RE.fullmatch(self.generation_signature_sha256) is None
            or type(self.replay_reservation_key) is not str
            or _SHA256_RE.fullmatch(self.replay_reservation_key) is None
            or type(self.replay_expires_at) is not int
            or self.replay_expires_at < self.request_timestamp
            or type(self.target_origin) is not str
            or self.target_origin != expected_origin
            or type(self.target_method) is not str
            or self.target_method != DISPATCH_METHOD
            or type(self.target_path) is not str
            or self.target_path != DISPATCH_PATH
            or type(self.state) is not str
            or self.state != "queued"
            or type(self.revision) is not int
            or self.revision != 1
        ):
            raise ControlledStagingReceiverPreflightError(
                "staging_receiver_preflight_result_invalid"
            )

    @property
    def receiver_verified(self) -> bool:
        return True

    @property
    def replay_reserved(self) -> bool:
        return True

    @property
    def credential_export_allowed(self) -> bool:
        return False

    @property
    def raw_nonce_export_allowed(self) -> bool:
        return False

    @property
    def signed_request_export_allowed(self) -> bool:
        return False

    @property
    def payload_export_allowed(self) -> bool:
        return False

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    @property
    def queue_runtime_allowed(self) -> bool:
        return False

    @property
    def worker_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def dispatch_attempt_allowed(self) -> bool:
        return False

    @property
    def orchestration_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def replay_cleanup_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_RECEIVER_PREFLIGHT_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "dispatchIntentSha256": self.dispatch_intent_sha256,
            "credentialGenerationId": self.credential_generation_id,
            "requestTimestamp": self.request_timestamp,
            "requestNonceSha256": self.request_nonce_sha256,
            "payloadBytes": self.payload_bytes,
            "payloadSha256": self.payload_sha256,
            "envelopeSignatureSha256": self.envelope_signature_sha256,
            "generationSignatureSha256": self.generation_signature_sha256,
            "replayReservationKey": self.replay_reservation_key,
            "replayExpiresAt": self.replay_expires_at,
            "targetOrigin": self.target_origin,
            "targetMethod": self.target_method,
            "targetPath": self.target_path,
            "state": self.state,
            "revision": self.revision,
            "receiverVerified": True,
            "replayReserved": True,
            "credentialExportAllowed": False,
            "rawNonceExportAllowed": False,
            "signedRequestExportAllowed": False,
            "payloadExportAllowed": False,
            "jobStateMutationAllowed": False,
            "queueRuntimeAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "dispatchAttemptAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
            "replayCleanupAllowed": False,
        }


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_input_invalid"
        )
    return value


def _require_endpoint(value: object) -> EngineEndpoint:
    if (
        type(value) is not EngineEndpoint
        or type(value.name) is not str
        or value.name not in ENGINE_NAMES
        or type(value.base_url) is not str
    ):
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_endpoint_invalid"
        )
    return value


def _require_rotation(value: object) -> CredentialRotationSet:
    if type(value) is not CredentialRotationSet:
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_credential_invalid"
        )
    return value


def _require_request(value: object) -> GenerationBoundRequest:
    if type(value) is not GenerationBoundRequest:
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_request_invalid"
        )
    return value


def _require_payload(value: object) -> bytes:
    if type(value) is not bytes or not value or len(value) > MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES:
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_payload_invalid"
        )
    return value


def _require_observed_target(method: object, path: object) -> tuple[str, str]:
    if type(method) is not str or type(path) is not str:
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_target_invalid"
        )
    return method, path


def _require_now(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_time_invalid"
        )
    return value


def _map_intent_error(exc: ControlledStagingDispatchIntentError) -> None:
    if exc.category == "staging_dispatch_intent_superseded":
        category = "staging_receiver_preflight_superseded"
    elif exc.category == "staging_dispatch_intent_queued_missing":
        category = "staging_receiver_preflight_queued_missing"
    elif exc.category == "staging_dispatch_intent_missing":
        category = "staging_receiver_preflight_intent_missing"
    elif exc.category == "staging_dispatch_intent_source_invalid":
        category = "staging_receiver_preflight_source_invalid"
    else:
        category = "staging_receiver_preflight_intent_invalid"
    raise ControlledStagingReceiverPreflightError(category) from None


def verify_controlled_staging_receiver_preflight(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
    rotation: CredentialRotationSet,
    request: GenerationBoundRequest,
    payload: bytes,
    observed_method: str,
    observed_path: str,
    now_seconds: int,
) -> ControlledStagingReceiverPreflightResult:
    """Verify one exact signed request without exposing transport/execution authority."""

    checked_provider = _require_provider(provider)
    checked_endpoint = _require_endpoint(endpoint)
    checked_rotation = _require_rotation(rotation)
    checked_request = _require_request(request)
    checked_payload = _require_payload(payload)
    checked_method, checked_path = _require_observed_target(
        observed_method,
        observed_path,
    )
    checked_now = _require_now(now_seconds)

    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_input_invalid"
        ) from None

    try:
        initial, queued, intent = _derive_intent(binding, checked_endpoint)
    except ControlledStagingDispatchIntentError as exc:
        _map_intent_error(exc)

    try:
        plan = build_orchestration_plan(
            binding.job_id,
            source_artifact_ref=binding.source_artifact_ref,
            source_sha256=binding.document_sha256,
            source_size_bytes=binding.source_size_bytes,
            source_media_type=binding.source_media_type,
            requested_engines=ENGINE_NAMES,
        )
        identity = build_dispatch_identity(plan.as_dict(), checked_endpoint.name)
        expected_payload = dispatch_identity_payload(identity)
        auth_binding = build_engine_auth_binding(checked_endpoint, "staging")
        target = build_engine_dispatch_target(auth_binding, checked_endpoint)
    except (
        OrchestrationContractError,
        DispatchIdentityError,
        ServiceAuthError,
        DispatchTargetError,
    ):
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_contract_invalid"
        ) from None

    expected_payload_sha256 = sha256(expected_payload).hexdigest()
    intent_sha256 = sha256(_intent_canonical_json_bytes(intent.record)).hexdigest()
    if (
        checked_payload != expected_payload
        or identity.job_id != binding.job_id
        or identity.source_artifact_id != binding.source_artifact_id
        or identity.run_id != intent.run_id
        or identity.engine != intent.engine
        or identity.identity_sha256 != intent.dispatch_identity_sha256
        or expected_payload_sha256 != intent.identity_payload_sha256
        or len(expected_payload) != intent.identity_payload_bytes
        or target.origin != intent.target_origin
        or target.method != intent.target_method
        or target.path != intent.target_path
        or queued.snapshot.state != "queued"
        or queued.snapshot.revision != 1
    ):
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_contract_invalid"
        )

    reservation_result: ControlledStagingReplayReservationResult | None = None

    def replay_checker(
        observed_binding,
        generation_id: str,
        nonce: str,
        request_timestamp: int,
    ) -> bool:
        nonlocal reservation_result
        if reservation_result is not None:
            return False
        try:
            reservation_result = reserve_controlled_staging_generation_replay(
                provider=checked_provider,
                binding=observed_binding,
                generation_id=generation_id,
                nonce=nonce,
                request_timestamp=request_timestamp,
            )
        except ControlledStagingReplayReservationError:
            raise
        return reservation_result.accepted

    try:
        with _existing_job_lock(checked_provider, binding.job_id):
            with checked_provider._verified_source_guard(
                binding
            ) as assert_source_stable:
                try:
                    _verify_queued_and_not_terminal_under_lock(
                        provider=checked_provider,
                        binding=binding,
                        initial=initial,
                        queued=queued,
                    )
                    _load_and_verify_intent_under_lock(
                        provider=checked_provider,
                        binding=binding,
                        derived=intent,
                    )
                except ControlledStagingDispatchIntentError as exc:
                    _map_intent_error(exc)
                assert_source_stable()

                try:
                    verified = verify_receiver_dispatch_request(
                        plan.as_dict(),
                        target,
                        checked_rotation,
                        checked_request,
                        observed_method=checked_method,
                        observed_path=checked_path,
                        payload=checked_payload,
                        now_seconds=checked_now,
                        replay_checker=replay_checker,
                    )
                except ReceiverVerificationError as exc:
                    raise ControlledStagingReceiverPreflightError(exc.category) from None

                if (
                    reservation_result is None
                    or reservation_result.accepted is not True
                    or reservation_result.replay_detected is not False
                    or verified.dispatch_identity != identity
                    or verified.target != target
                    or verified.request_timestamp != checked_request.envelope.timestamp
                    or verified.nonce != checked_request.envelope.nonce
                    or verified.payload_sha256 != expected_payload_sha256
                    or verified.generation_credential.generation_id
                    != checked_request.credential_generation_id
                ):
                    raise ControlledStagingReceiverPreflightError(
                        "staging_receiver_preflight_verification_invalid"
                    )

                try:
                    _verify_queued_and_not_terminal_under_lock(
                        provider=checked_provider,
                        binding=binding,
                        initial=initial,
                        queued=queued,
                    )
                    _load_and_verify_intent_under_lock(
                        provider=checked_provider,
                        binding=binding,
                        derived=intent,
                    )
                except ControlledStagingDispatchIntentError as exc:
                    _map_intent_error(exc)
                assert_source_stable()
    except ControlledStagingReceiverPreflightError:
        raise
    except ControlledStagingSigningPreflightError:
        raise ControlledStagingReceiverPreflightError(
            "staging_receiver_preflight_lock_invalid"
        ) from None
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_receiver_preflight_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_receiver_preflight_state_invalid"
        )
        raise ControlledStagingReceiverPreflightError(category) from None

    assert reservation_result is not None
    return ControlledStagingReceiverPreflightResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        engine=identity.engine,
        run_id=identity.run_id,
        dispatch_identity_sha256=identity.identity_sha256,
        dispatch_intent_sha256=intent_sha256,
        credential_generation_id=checked_request.credential_generation_id,
        request_timestamp=checked_request.envelope.timestamp,
        request_nonce_sha256=sha256(checked_request.envelope.nonce.encode("ascii")).hexdigest(),
        payload_bytes=len(checked_payload),
        payload_sha256=expected_payload_sha256,
        envelope_signature_sha256=sha256(
            checked_request.envelope.signature.encode("ascii")
        ).hexdigest(),
        generation_signature_sha256=sha256(
            checked_request.generation_signature.encode("ascii")
        ).hexdigest(),
        replay_reservation_key=reservation_result.reservation_key,
        replay_expires_at=reservation_result.expires_at,
        target_origin=target.origin,
        target_method=target.method,
        target_path=target.path,
        state="queued",
        revision=1,
    )
