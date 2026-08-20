"""Read-only dispatch preflight for one exact queued staging engine run.

This module composes already-completed C.1/C.2-B/C.2-C foundations with exact
provider-backed queued Gate D evidence. It deliberately resolves no credential,
signs no request, writes no state, sends no network request, advances no job
state, starts no worker, and executes no engine.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .config import EngineEndpoint
from .controlled_staging_job_lifecycle import (
    ControlledStagingJobLifecycleError,
    _validated_binding,
)
from .controlled_staging_queued_transition import (
    ControlledStagingQueuedTransitionError,
    recover_controlled_staging_queued_run,
)
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
    MinimumStagingVerticalSliceResult,
    StagingUploadProvider,
)
from .orchestration import (
    ENGINE_NAMES,
    OrchestrationContractError,
    build_orchestration_plan,
)
from .service_auth import ServiceAuthError, build_engine_auth_binding


CONTROLLED_STAGING_DISPATCH_PREFLIGHT_VERSION = (
    "scoremosaic-controlled-staging-dispatch-preflight-v1"
)
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ControlledStagingDispatchPreflightError(ValueError):
    """Stable fail-closed category for the staging dispatch preflight."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ControlledStagingDispatchPreflightResult:
    job_id: str
    source_artifact_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    state: str
    revision: int
    target_origin: str
    target_method: str
    target_path: str
    identity_payload_bytes: int

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
            or self.state != "queued"
            or type(self.revision) is not int
            or self.revision != 1
            or type(self.target_origin) is not str
            or self.target_origin != expected_origin
            or type(self.target_method) is not str
            or self.target_method != DISPATCH_METHOD
            or type(self.target_path) is not str
            or self.target_path != DISPATCH_PATH
            or type(self.identity_payload_bytes) is not int
            or not 1
            <= self.identity_payload_bytes
            <= MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
        ):
            raise ControlledStagingDispatchPreflightError(
                "staging_dispatch_preflight_result_invalid"
            )

    @property
    def credential_resolution_allowed(self) -> bool:
        return False

    @property
    def request_signing_allowed(self) -> bool:
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
    def state_mutation_allowed(self) -> bool:
        return False

    @property
    def orchestration_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_DISPATCH_PREFLIGHT_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "state": self.state,
            "revision": self.revision,
            "targetOrigin": self.target_origin,
            "targetMethod": self.target_method,
            "targetPath": self.target_path,
            "identityPayloadBytes": self.identity_payload_bytes,
            "credentialResolutionAllowed": False,
            "requestSigningAllowed": False,
            "queueRuntimeAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "stateMutationAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
        }


def build_controlled_staging_dispatch_preflight(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
) -> ControlledStagingDispatchPreflightResult:
    """Validate one queued staging run against the exact future dispatch target.

    The returned object is evidence only. It grants no authority to resolve a
    credential, sign a request, send traffic, mutate durable state, or execute an
    engine.
    """

    if (
        type(minimum_slice) is not MinimumStagingVerticalSliceResult
        or type(provider) is not StagingUploadProvider
        or type(endpoint) is not EngineEndpoint
        or type(endpoint.name) is not str
        or endpoint.name not in ENGINE_NAMES
    ):
        raise ControlledStagingDispatchPreflightError(
            "staging_dispatch_preflight_input_invalid"
        )

    try:
        binding = _validated_binding(minimum_slice, provider)
        queued = recover_controlled_staging_queued_run(
            minimum_slice=minimum_slice,
            provider=provider,
            engine=endpoint.name,
        )
    except (ControlledStagingJobLifecycleError, ControlledStagingQueuedTransitionError):
        raise ControlledStagingDispatchPreflightError(
            "staging_dispatch_preflight_queued_invalid"
        ) from None

    if (
        queued.job_id != binding.job_id
        or queued.engine != endpoint.name
        or queued.state != "queued"
        or queued.revision != 1
        or queued.disposition != "pre_dispatch_candidate"
        or queued.terminal
        or queued.reconciliation_required
        or queued.automatic_execution_allowed
        or queued.retry_allowed
        or queued.network_dispatch_allowed
        or queued.state_mutation_allowed
    ):
        raise ControlledStagingDispatchPreflightError(
            "staging_dispatch_preflight_queued_invalid"
        )

    try:
        plan = build_orchestration_plan(
            binding.job_id,
            source_artifact_ref=binding.source_artifact_ref,
            source_sha256=binding.document_sha256,
            source_size_bytes=binding.source_size_bytes,
            source_media_type=binding.source_media_type,
            requested_engines=ENGINE_NAMES,
        )
        if (
            plan.plan_id != binding.orchestration_plan_id
            or plan.plan_sha256 != binding.orchestration_plan_sha256
            or plan.source_artifact.artifact_id != binding.source_artifact_id
        ):
            raise ControlledStagingDispatchPreflightError(
                "staging_dispatch_preflight_contract_invalid"
            )

        identity = build_dispatch_identity(plan.as_dict(), endpoint.name)
        payload = dispatch_identity_payload(identity)
    except ControlledStagingDispatchPreflightError:
        raise
    except (OrchestrationContractError, DispatchIdentityError):
        raise ControlledStagingDispatchPreflightError(
            "staging_dispatch_preflight_contract_invalid"
        ) from None

    if (
        identity.job_id != binding.job_id
        or identity.source_artifact_id != binding.source_artifact_id
        or identity.source_artifact_ref != binding.source_artifact_ref
        or identity.source_sha256 != binding.document_sha256
        or identity.source_size_bytes != binding.source_size_bytes
        or identity.source_media_type != binding.source_media_type
        or identity.plan_id != binding.orchestration_plan_id
        or identity.plan_sha256 != binding.orchestration_plan_sha256
        or identity.run_id != queued.run_id
        or identity.engine != queued.engine
        or identity.identity_sha256 != queued.dispatch_identity_sha256
    ):
        raise ControlledStagingDispatchPreflightError(
            "staging_dispatch_preflight_identity_mismatch"
        )

    try:
        auth_binding = build_engine_auth_binding(endpoint, "staging")
        target = build_engine_dispatch_target(auth_binding, endpoint)
    except (ServiceAuthError, DispatchTargetError):
        raise ControlledStagingDispatchPreflightError(
            "staging_dispatch_preflight_target_invalid"
        ) from None

    if (
        target.environment != "staging"
        or target.engine != identity.engine
        or target.method != DISPATCH_METHOD
        or target.path != DISPATCH_PATH
    ):
        raise ControlledStagingDispatchPreflightError(
            "staging_dispatch_preflight_target_invalid"
        )

    return ControlledStagingDispatchPreflightResult(
        job_id=identity.job_id,
        source_artifact_id=identity.source_artifact_id,
        engine=identity.engine,
        run_id=identity.run_id,
        dispatch_identity_sha256=identity.identity_sha256,
        state=queued.state,
        revision=queued.revision,
        target_origin=target.origin,
        target_method=target.method,
        target_path=target.path,
        identity_payload_bytes=len(payload),
    )
