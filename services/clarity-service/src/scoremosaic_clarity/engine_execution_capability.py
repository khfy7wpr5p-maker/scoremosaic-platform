"""Stage 5-B1 engine-owned execution capability and eligibility contract.

This boundary proves whether one already authenticated, dispatch-accepted and
durably stored source is eligible for this engine's pinned runtime. It performs
no process execution, network I/O, retry, result persistence, Gateway mutation,
or source conversion.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from types import MappingProxyType

from .dispatch_acceptance import DispatchAcceptanceStoreError, EngineDispatchAcceptanceStore
from .receiver_authority import ENGINE_NAME, EngineReceiverAuthority, EngineReceiverAuthorityError
from .source_delivery import EngineSourceStore, SourceDeliveryReceiverError

ENGINE_EXECUTION_CAPABILITY_VERSION = "scoremosaic-engine-execution-capability-v1"

ENGINE_EXECUTION_MEDIA_TYPES = MappingProxyType({
    "audiveris": frozenset({"application/pdf", "image/jpeg", "image/png"}),
    "homr": frozenset({"image/jpeg", "image/png"}),
    "clarity": frozenset({"application/pdf"}),
})
_MEDIA_SUFFIX = MappingProxyType({
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
})


class EngineExecutionCapabilityError(ValueError):
    """Stable fail-closed Stage 5-B1 error category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class EngineExecutionEligibility:
    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    source_artifact_id: str
    source_size_bytes: int
    source_sha256: str
    source_media_type: str
    runtime_input_suffix: str
    candidate_id: str
    candidate_namespace: str
    timeout_seconds: int

    def __post_init__(self) -> None:
        if (
            self.engine != ENGINE_NAME
            or self.source_media_type not in ENGINE_EXECUTION_MEDIA_TYPES[ENGINE_NAME]
            or self.runtime_input_suffix != _MEDIA_SUFFIX.get(self.source_media_type)
            or type(self.timeout_seconds) is not int
            or not 30 <= self.timeout_seconds <= 7200
        ):
            raise EngineExecutionCapabilityError("engine_execution_eligibility_invalid")

    @property
    def execution_eligible(self) -> bool:
        return True

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    @property
    def source_conversion_allowed(self) -> bool:
        return False

    @property
    def automatic_retry_allowed(self) -> bool:
        return False

    @property
    def result_persistence_allowed(self) -> bool:
        return False

    @property
    def gateway_state_mutation_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": ENGINE_EXECUTION_CAPABILITY_VERSION,
            "environment": "staging",
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSizeBytes": self.source_size_bytes,
            "sourceSha256": self.source_sha256,
            "sourceMediaType": self.source_media_type,
            "runtimeInputSuffix": self.runtime_input_suffix,
            "candidateId": self.candidate_id,
            "candidateNamespace": self.candidate_namespace,
            "timeoutSeconds": self.timeout_seconds,
            "executionEligible": True,
            "engineExecutionAllowed": False,
            "sourceConversionAllowed": False,
            "automaticRetryAllowed": False,
            "resultPersistenceAllowed": False,
            "gatewayStateMutationAllowed": False,
        }


def _trusted_plan_dict(
    authority: EngineReceiverAuthority,
    job_id: str,
) -> tuple[object, dict[str, object]]:
    try:
        trusted = authority.load_trusted_plan(job_id=job_id)
        plan = json.loads(trusted.canonical_plan_bytes.decode("ascii"))
    except (EngineReceiverAuthorityError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise EngineExecutionCapabilityError("engine_execution_trusted_plan_invalid") from None
    if type(plan) is not dict:
        raise EngineExecutionCapabilityError("engine_execution_trusted_plan_invalid")
    return trusted, plan


def evaluate_engine_execution_eligibility(
    *,
    authority: EngineReceiverAuthority,
    dispatch_acceptance_store: EngineDispatchAcceptanceStore,
    source_store: EngineSourceStore,
    job_id: str,
    run_id: str,
    dispatch_identity_sha256: str,
) -> EngineExecutionEligibility:
    """Converge engine-owned trusted plan, dispatch receipt and stored source."""

    if (
        type(authority) is not EngineReceiverAuthority
        or type(dispatch_acceptance_store) is not EngineDispatchAcceptanceStore
        or type(source_store) is not EngineSourceStore
        or type(job_id) is not str
        or type(run_id) is not str
        or type(dispatch_identity_sha256) is not str
    ):
        raise EngineExecutionCapabilityError("engine_execution_input_invalid")

    trusted, plan = _trusted_plan_dict(authority, job_id)
    if trusted.engine != ENGINE_NAME or trusted.job_id != job_id or trusted.run_id != run_id:
        raise EngineExecutionCapabilityError("engine_execution_identity_mismatch")

    try:
        receipt = dispatch_acceptance_store.require(
            job_id=job_id,
            run_id=run_id,
            dispatch_identity_sha256=dispatch_identity_sha256,
        )
    except DispatchAcceptanceStoreError:
        raise EngineExecutionCapabilityError("engine_execution_dispatch_not_accepted") from None

    try:
        stored = source_store.load(job_id=job_id, run_id=run_id)
    except SourceDeliveryReceiverError:
        raise EngineExecutionCapabilityError("engine_execution_source_unavailable") from None

    if (
        receipt.engine != ENGINE_NAME
        or receipt.job_id != job_id
        or receipt.run_id != run_id
        or receipt.dispatch_identity_sha256 != dispatch_identity_sha256
        or stored.engine != ENGINE_NAME
        or stored.job_id != job_id
        or stored.run_id != run_id
        or stored.dispatch_identity_sha256 != dispatch_identity_sha256
    ):
        raise EngineExecutionCapabilityError("engine_execution_identity_mismatch")

    source = plan.get("sourceArtifact")
    runs = plan.get("engineRuns")
    if type(source) is not dict or type(runs) is not list:
        raise EngineExecutionCapabilityError("engine_execution_trusted_plan_invalid")
    run = next(
        (
            item
            for item in runs
            if type(item) is dict and item.get("engine") == ENGINE_NAME
        ),
        None,
    )
    if type(run) is not dict:
        raise EngineExecutionCapabilityError("engine_execution_trusted_plan_invalid")

    if (
        source.get("artifactId") != stored.source_artifact_id
        or source.get("sha256") != stored.source_sha256
        or source.get("sizeBytes") != stored.source_size_bytes
        or source.get("mediaType") != stored.source_media_type
        or source.get("immutable") is not True
        or run.get("runId") != run_id
        or run.get("inputArtifactId") != stored.source_artifact_id
        or run.get("operation") != "transcribe"
        or run.get("attemptLimit") != 1
        or type(run.get("candidateId")) is not str
        or type(run.get("candidateNamespace")) is not str
        or type(run.get("timeoutSeconds")) is not int
    ):
        raise EngineExecutionCapabilityError("engine_execution_plan_source_mismatch")

    if stored.source_media_type not in ENGINE_EXECUTION_MEDIA_TYPES[ENGINE_NAME]:
        raise EngineExecutionCapabilityError("engine_execution_media_type_unsupported")

    return EngineExecutionEligibility(
        engine=ENGINE_NAME,
        job_id=job_id,
        run_id=run_id,
        dispatch_identity_sha256=dispatch_identity_sha256,
        source_artifact_id=stored.source_artifact_id,
        source_size_bytes=stored.source_size_bytes,
        source_sha256=stored.source_sha256,
        source_media_type=stored.source_media_type,
        runtime_input_suffix=_MEDIA_SUFFIX[stored.source_media_type],
        candidate_id=run["candidateId"],
        candidate_namespace=run["candidateNamespace"],
        timeout_seconds=run["timeoutSeconds"],
    )
