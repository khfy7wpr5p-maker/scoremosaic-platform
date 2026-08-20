"""Ephemeral authenticated-signing preflight for one controlled staging run.

This bounded slice proves that one already-persisted, non-executable dispatch
intent can be signed by an explicitly supplied current credential generation.
It never resolves credentials, allocates a timestamp or nonce, persists a signed
request, exports a transferable signature, sends network traffic, advances D.1
state, starts a worker, or executes an engine.

The signed request exists only inside this function long enough to validate the
exact target and semantic dispatch identity. The returned result contains only
non-secret hashes and bounded metadata. The run remains ``queued`` revision 1,
and terminal revision-2 evidence supersedes the preflight fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .authenticated_request import (
    MAX_FUTURE_SKEW_SECONDS,
    MAX_REQUEST_AGE_SECONDS,
)
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
from .credential_rotation import (
    CredentialRotationError,
    CredentialRotationSet,
    select_signing_credential,
    sign_rotation_authenticated_request,
)
from .dispatch_identity import (
    MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES,
    DispatchIdentityError,
    build_dispatch_identity,
    dispatch_identity_payload,
    require_authenticated_dispatch_identity,
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
from .orchestration import (
    ENGINE_NAMES,
    OrchestrationContractError,
    build_orchestration_plan,
)
from .service_auth import ServiceAuthError, build_engine_auth_binding


CONTROLLED_STAGING_SIGNING_PREFLIGHT_VERSION = (
    "scoremosaic-controlled-staging-signing-preflight-v1"
)
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


class ControlledStagingSigningPreflightError(ValueError):
    """Stable fail-closed category for controlled staging signing proof."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ControlledStagingSigningPreflightResult:
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
            raise ControlledStagingSigningPreflightError(
                "staging_signing_preflight_result_invalid"
            )

    @property
    def signing_performed(self) -> bool:
        return True

    @property
    def credential_resolution_allowed(self) -> bool:
        return False

    @property
    def nonce_allocation_allowed(self) -> bool:
        return False

    @property
    def timestamp_allocation_allowed(self) -> bool:
        return False

    @property
    def signed_request_export_allowed(self) -> bool:
        return False

    @property
    def signature_export_allowed(self) -> bool:
        return False

    @property
    def persistence_allowed(self) -> bool:
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

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_SIGNING_PREFLIGHT_VERSION,
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
            "targetOrigin": self.target_origin,
            "targetMethod": self.target_method,
            "targetPath": self.target_path,
            "state": self.state,
            "revision": self.revision,
            "signingPerformed": True,
            "credentialResolutionAllowed": False,
            "nonceAllocationAllowed": False,
            "timestampAllocationAllowed": False,
            "signedRequestExportAllowed": False,
            "signatureExportAllowed": False,
            "persistenceAllowed": False,
            "jobStateMutationAllowed": False,
            "queueRuntimeAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "dispatchAttemptAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
        }


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_input_invalid"
        )
    return value


def _require_endpoint(value: object) -> EngineEndpoint:
    if (
        type(value) is not EngineEndpoint
        or type(value.name) is not str
        or value.name not in ENGINE_NAMES
        or type(value.base_url) is not str
    ):
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_endpoint_invalid"
        )
    return value


def _require_rotation(value: object) -> CredentialRotationSet:
    if type(value) is not CredentialRotationSet:
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_credential_invalid"
        )
    return value


def _require_time_inputs(timestamp: object, now_seconds: object) -> tuple[int, int]:
    if type(timestamp) is not int or timestamp < 0:
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_timestamp_invalid"
        )
    if type(now_seconds) is not int or now_seconds < 0:
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_timestamp_invalid"
        )
    if timestamp > now_seconds + MAX_FUTURE_SKEW_SECONDS:
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_timestamp_in_future"
        )
    if now_seconds - timestamp > MAX_REQUEST_AGE_SECONDS:
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_timestamp_expired"
        )
    return timestamp, now_seconds


def _require_nonce(value: object) -> str:
    if type(value) is not str or _NONCE_RE.fullmatch(value) is None:
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_nonce_invalid"
        )
    return value


def _map_intent_error(exc: ControlledStagingDispatchIntentError) -> None:
    if exc.category == "staging_dispatch_intent_superseded":
        category = "staging_signing_preflight_superseded"
    elif exc.category == "staging_dispatch_intent_queued_missing":
        category = "staging_signing_preflight_queued_missing"
    elif exc.category == "staging_dispatch_intent_missing":
        category = "staging_signing_preflight_intent_missing"
    elif exc.category == "staging_dispatch_intent_source_invalid":
        category = "staging_signing_preflight_source_invalid"
    else:
        category = "staging_signing_preflight_intent_invalid"
    raise ControlledStagingSigningPreflightError(category) from None


def _require_rotation_binding(selected, target) -> None:
    binding = selected.binding
    checks = (
        (binding.version, target.binding_version),
        (binding.caller_identity, target.caller_identity),
        (binding.engine, target.engine),
        (binding.audience_identity, target.audience_identity),
        (binding.environment, target.environment),
        (binding.credential_key, target.credential_key),
    )
    if any(observed != expected for observed, expected in checks):
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_credential_binding_mismatch"
        )


def build_controlled_staging_signing_preflight(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
    rotation: CredentialRotationSet,
    timestamp: int,
    nonce: str,
    now_seconds: int,
) -> ControlledStagingSigningPreflightResult:
    """Prove exact intent signing without exporting or persisting a signed request."""

    checked_provider = _require_provider(provider)
    checked_endpoint = _require_endpoint(endpoint)
    checked_rotation = _require_rotation(rotation)
    checked_timestamp, checked_now = _require_time_inputs(timestamp, now_seconds)
    checked_nonce = _require_nonce(nonce)

    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_input_invalid"
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
        payload = dispatch_identity_payload(identity)
        auth_binding = build_engine_auth_binding(checked_endpoint, "staging")
        target = build_engine_dispatch_target(auth_binding, checked_endpoint)
    except (
        OrchestrationContractError,
        DispatchIdentityError,
        ServiceAuthError,
        DispatchTargetError,
    ):
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_contract_invalid"
        ) from None

    payload_sha256 = sha256(payload).hexdigest()
    intent_sha256 = sha256(_intent_canonical_json_bytes(intent.record)).hexdigest()

    if (
        identity.job_id != binding.job_id
        or identity.source_artifact_id != binding.source_artifact_id
        or identity.run_id != intent.run_id
        or identity.engine != intent.engine
        or identity.identity_sha256 != intent.dispatch_identity_sha256
        or payload_sha256 != intent.identity_payload_sha256
        or len(payload) != intent.identity_payload_bytes
        or target.origin != intent.target_origin
        or target.method != intent.target_method
        or target.path != intent.target_path
        or queued.snapshot.state != "queued"
        or queued.snapshot.revision != 1
    ):
        raise ControlledStagingSigningPreflightError(
            "staging_signing_preflight_contract_invalid"
        )

    try:
        with checked_provider._job_lock(binding.job_id):
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
                    selected = select_signing_credential(
                        checked_rotation,
                        now_seconds=checked_now,
                    )
                except CredentialRotationError:
                    raise ControlledStagingSigningPreflightError(
                        "staging_signing_preflight_credential_invalid"
                    ) from None
                _require_rotation_binding(selected, target)

                try:
                    request = sign_rotation_authenticated_request(
                        checked_rotation,
                        method=target.method,
                        path=target.path,
                        timestamp=checked_timestamp,
                        nonce=checked_nonce,
                        payload=payload,
                        now_seconds=checked_now,
                    )
                    authenticated_identity = require_authenticated_dispatch_identity(
                        plan.as_dict(),
                        target,
                        request.envelope,
                        payload,
                    )
                except (CredentialRotationError, DispatchIdentityError):
                    raise ControlledStagingSigningPreflightError(
                        "staging_signing_preflight_signing_invalid"
                    ) from None

                if (
                    authenticated_identity.identity_sha256
                    != identity.identity_sha256
                    or request.credential_generation_id != selected.generation_id
                    or request.envelope.engine != identity.engine
                    or request.envelope.environment != "staging"
                    or request.envelope.method != target.method
                    or request.envelope.path != target.path
                    or request.envelope.timestamp != checked_timestamp
                    or request.envelope.nonce != checked_nonce
                    or request.envelope.payload_bytes != len(payload)
                    or request.envelope.payload_sha256 != payload_sha256
                ):
                    raise ControlledStagingSigningPreflightError(
                        "staging_signing_preflight_signing_invalid"
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
    except ControlledStagingSigningPreflightError:
        raise
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_signing_preflight_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_signing_preflight_state_invalid"
        )
        raise ControlledStagingSigningPreflightError(category) from None

    envelope_signature_sha256 = sha256(
        request.envelope.signature.encode("ascii")
    ).hexdigest()
    generation_signature_sha256 = sha256(
        request.generation_signature.encode("ascii")
    ).hexdigest()

    return ControlledStagingSigningPreflightResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        engine=identity.engine,
        run_id=identity.run_id,
        dispatch_identity_sha256=identity.identity_sha256,
        dispatch_intent_sha256=intent_sha256,
        credential_generation_id=request.credential_generation_id,
        request_timestamp=checked_timestamp,
        request_nonce_sha256=sha256(checked_nonce.encode("ascii")).hexdigest(),
        payload_bytes=len(payload),
        payload_sha256=payload_sha256,
        envelope_signature_sha256=envelope_signature_sha256,
        generation_signature_sha256=generation_signature_sha256,
        target_origin=target.origin,
        target_method=target.method,
        target_path=target.path,
        state="queued",
        revision=1,
    )
