"""Provider-backed Gate D lifecycle evidence for the controlled staging runtime.

The boundary begins only after the minimum staging vertical slice has written and
reverified one immutable source. It persists the deterministic D.1 planned state,
D.2 empty idempotency ledger, and D.4 initial provenance record for each planned
engine run. A restarted provider can restore that exact evidence into read-only
D.5 decisions. It creates no queue, worker, transition, transport, dispatch, or
engine authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from .artifact_lifecycle import (
    ArtifactLifecycleError,
    CandidateArtifactLifecycle,
    build_artifact_lifecycle,
)
from .dispatch_identity import DispatchIdentityError, build_dispatch_identity
from .durable_artifact_storage import (
    DurableArtifactStorageManifest,
    DurableArtifactStorageError,
    build_durable_artifact_storage_manifest,
)
from .durable_idempotency import (
    DurableIdempotencyError,
    DurableIdempotencyLedger,
    build_durable_idempotency_ledger,
)
from .durable_job_state import (
    DurableJobStateError,
    DurableJobStateSnapshot,
    build_durable_job_state,
)
from .durable_provenance import (
    DurableProvenanceChain,
    DurableProvenanceError,
    build_durable_provenance_chain,
)
from .durable_restart_recovery import (
    DurableRestartRecoveryDecision,
    DurableRestartRecoveryError,
    evaluate_durable_restart_recovery,
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
from .safe_source_job_binding import (
    SafeSourceJobBindingDecision,
    SafeSourceJobBindingError,
)
from .safe_source_job_binding_verification import (
    verify_safe_source_job_binding_decision,
)


CONTROLLED_STAGING_JOB_LIFECYCLE_VERSION = (
    "scoremosaic-controlled-staging-job-lifecycle-v1"
)
CONTROLLED_STAGING_JOB_RECOVERY_VERSION = (
    "scoremosaic-controlled-staging-job-recovery-v1"
)
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def _canonical_record_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class ControlledStagingJobLifecycleError(ValueError):
    """Stable fail-closed controlled staging lifecycle failure category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ControlledStagingRunEvidence:
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    state: str
    revision: int
    idempotency_record_count: int
    provenance_record_count: int
    provenance_chain_sha256: str

    def __post_init__(self) -> None:
        if type(self.engine) is not str or self.engine not in ENGINE_NAMES:
            raise ControlledStagingJobLifecycleError(
                "staging_job_lifecycle_result_invalid"
            )
        if type(self.run_id) is not str or _RUN_ID_RE.fullmatch(self.run_id) is None:
            raise ControlledStagingJobLifecycleError(
                "staging_job_lifecycle_result_invalid"
            )
        if (
            type(self.dispatch_identity_sha256) is not str
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or type(self.provenance_chain_sha256) is not str
            or _SHA256_RE.fullmatch(self.provenance_chain_sha256) is None
            or self.state != "planned"
            or type(self.revision) is not int
            or self.revision != 0
            or type(self.idempotency_record_count) is not int
            or self.idempotency_record_count != 0
            or type(self.provenance_record_count) is not int
            or self.provenance_record_count != 1
        ):
            raise ControlledStagingJobLifecycleError(
                "staging_job_lifecycle_result_invalid"
            )


@dataclass(frozen=True, slots=True)
class _ControlledStagingRunContext:
    snapshot: DurableJobStateSnapshot
    ledger: DurableIdempotencyLedger
    provenance: DurableProvenanceChain


@dataclass(frozen=True, slots=True)
class _ControlledStagingDerivedEvidence:
    record: dict[str, object]
    run_evidence: tuple[ControlledStagingRunEvidence, ...]
    run_contexts: tuple[_ControlledStagingRunContext, ...]
    lifecycle: CandidateArtifactLifecycle
    manifest: DurableArtifactStorageManifest


@dataclass(frozen=True, slots=True)
class ControlledStagingJobLifecycleResult:
    job_id: str
    source_artifact_id: str
    persistence_state: str
    runs: tuple[ControlledStagingRunEvidence, ...]

    def __post_init__(self) -> None:
        if (
            type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.source_artifact_id) is not str
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.persistence_state) is not str
            or self.persistence_state not in {"written", "replay"}
            or type(self.runs) is not tuple
            or any(type(run) is not ControlledStagingRunEvidence for run in self.runs)
            or tuple(run.engine for run in self.runs) != ENGINE_NAMES
        ):
            raise ControlledStagingJobLifecycleError(
                "staging_job_lifecycle_result_invalid"
            )

    @property
    def queue_allowed(self) -> bool:
        return False

    @property
    def worker_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def orchestration_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_JOB_LIFECYCLE_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "persistenceState": self.persistence_state,
            "runs": [
                {
                    "engine": run.engine,
                    "runId": run.run_id,
                    "dispatchIdentitySha256": run.dispatch_identity_sha256,
                    "state": run.state,
                    "revision": run.revision,
                    "idempotencyRecordCount": run.idempotency_record_count,
                    "provenanceRecordCount": run.provenance_record_count,
                    "provenanceChainSha256": run.provenance_chain_sha256,
                }
                for run in self.runs
            ],
            "queueAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
        }


@dataclass(frozen=True, slots=True)
class ControlledStagingJobRecoveryResult:
    """Read-only provider-backed D.5 decisions for one restored staging job."""

    job_id: str
    source_artifact_id: str
    runs: tuple[DurableRestartRecoveryDecision, ...]

    def __post_init__(self) -> None:
        if (
            type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.source_artifact_id) is not str
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.runs) is not tuple
            or any(type(run) is not DurableRestartRecoveryDecision for run in self.runs)
            or tuple(run.engine for run in self.runs) != ENGINE_NAMES
            or any(run.job_id != self.job_id for run in self.runs)
            or any(
                run.state != "planned"
                or run.revision != 0
                or run.disposition != "pre_dispatch_candidate"
                or run.terminal
                or run.reconciliation_required
                or run.automatic_execution_allowed
                or run.retry_allowed
                or run.network_dispatch_allowed
                or run.state_mutation_allowed
                for run in self.runs
            )
        ):
            raise ControlledStagingJobLifecycleError(
                "staging_job_recovery_result_invalid"
            )

    @property
    def automatic_execution_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def state_mutation_allowed(self) -> bool:
        return False

    @property
    def queue_allowed(self) -> bool:
        return False

    @property
    def worker_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def orchestration_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_JOB_RECOVERY_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "runs": [run.as_safe_dict() for run in self.runs],
            "automaticExecutionAllowed": False,
            "retryAllowed": False,
            "stateMutationAllowed": False,
            "queueAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
        }


def _validated_binding(
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
) -> SafeSourceJobBindingDecision:
    if (
        type(minimum_slice) is not MinimumStagingVerticalSliceResult
        or type(provider) is not StagingUploadProvider
    ):
        raise ControlledStagingJobLifecycleError(
            "staging_job_lifecycle_input_invalid"
        )
    binding = minimum_slice.binding
    if binding.environment != "staging":
        raise ControlledStagingJobLifecycleError("staging_environment_required")
    try:
        verify_safe_source_job_binding_decision(
            binding,
            finalization=minimum_slice.finalization,
        )
    except SafeSourceJobBindingError:
        raise ControlledStagingJobLifecycleError(
            "staging_job_source_binding_invalid"
        ) from None
    return binding


def _derive_initial_evidence(
    binding: SafeSourceJobBindingDecision,
) -> _ControlledStagingDerivedEvidence:
    try:
        plan = build_orchestration_plan(
            binding.job_id,
            source_artifact_ref=binding.source_artifact_ref,
            source_sha256=binding.document_sha256,
            source_size_bytes=binding.source_size_bytes,
            source_media_type=binding.source_media_type,
            requested_engines=ENGINE_NAMES,
        )
        lifecycle = build_artifact_lifecycle(plan.as_dict())
        manifest = build_durable_artifact_storage_manifest(lifecycle)
    except (
        OrchestrationContractError,
        ArtifactLifecycleError,
        DurableArtifactStorageError,
    ):
        raise ControlledStagingJobLifecycleError(
            "staging_job_contract_invalid"
        ) from None
    if (
        plan.plan_id != binding.orchestration_plan_id
        or plan.plan_sha256 != binding.orchestration_plan_sha256
        or lifecycle.lifecycle_id != binding.lifecycle_id
        or lifecycle.lifecycle_sha256 != binding.lifecycle_sha256
        or manifest.manifest_sha256 != binding.storage_manifest_sha256
    ):
        raise ControlledStagingJobLifecycleError(
            "staging_job_contract_invalid"
        )

    run_records: list[dict[str, object]] = []
    run_evidence: list[ControlledStagingRunEvidence] = []
    run_contexts: list[_ControlledStagingRunContext] = []
    try:
        for engine in ENGINE_NAMES:
            identity = build_dispatch_identity(plan.as_dict(), engine)
            snapshot = build_durable_job_state(identity)
            ledger = build_durable_idempotency_ledger(snapshot)
            provenance = build_durable_provenance_chain(
                snapshot,
                manifest,
                lifecycle=lifecycle,
            )
            run_records.append(
                {
                    "engine": engine,
                    "run_id": identity.run_id,
                    "dispatch_identity_sha256": identity.identity_sha256,
                    "job_state": snapshot.as_safe_dict(),
                    "idempotency": ledger.as_safe_dict(),
                    "provenance": provenance.as_safe_dict(),
                }
            )
            run_evidence.append(
                ControlledStagingRunEvidence(
                    engine=engine,
                    run_id=identity.run_id,
                    dispatch_identity_sha256=identity.identity_sha256,
                    state=snapshot.state,
                    revision=snapshot.revision,
                    idempotency_record_count=len(ledger.records),
                    provenance_record_count=len(provenance.records),
                    provenance_chain_sha256=provenance.chain_sha256,
                )
            )
            run_contexts.append(
                _ControlledStagingRunContext(
                    snapshot=snapshot,
                    ledger=ledger,
                    provenance=provenance,
                )
            )
    except (
        DispatchIdentityError,
        DurableJobStateError,
        DurableIdempotencyError,
        DurableProvenanceError,
    ):
        raise ControlledStagingJobLifecycleError(
            "staging_job_contract_invalid"
        ) from None

    record: dict[str, object] = {
        "version": CONTROLLED_STAGING_JOB_LIFECYCLE_VERSION,
        "environment": "staging",
        "job_id": binding.job_id,
        "source_artifact_id": binding.source_artifact_id,
        "source_sha256": binding.document_sha256,
        "orchestration_plan_id": plan.plan_id,
        "orchestration_plan_sha256": plan.plan_sha256,
        "lifecycle_id": lifecycle.lifecycle_id,
        "lifecycle_sha256": lifecycle.lifecycle_sha256,
        "storage_manifest_sha256": manifest.manifest_sha256,
        "runs": run_records,
        "boundaries": {
            "queueAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
        },
    }
    return _ControlledStagingDerivedEvidence(
        record=record,
        run_evidence=tuple(run_evidence),
        run_contexts=tuple(run_contexts),
        lifecycle=lifecycle,
        manifest=manifest,
    )


def run_controlled_staging_job_lifecycle(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
) -> ControlledStagingJobLifecycleResult:
    """Persist exact initial Gate D evidence without activating execution."""

    binding = _validated_binding(minimum_slice, provider)
    try:
        provider.read_source(binding)
    except MinimumStagingVerticalSliceError:
        raise ControlledStagingJobLifecycleError(
            "staging_job_source_invalid"
        ) from None
    derived = _derive_initial_evidence(binding)
    try:
        persistence_state = provider.persist_job_lifecycle_record(
            binding=binding,
            record=derived.record,
        )
    except MinimumStagingVerticalSliceError:
        raise ControlledStagingJobLifecycleError(
            "staging_job_lifecycle_state_invalid"
        ) from None

    return ControlledStagingJobLifecycleResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        persistence_state=persistence_state,
        runs=derived.run_evidence,
    )


def recover_controlled_staging_job_lifecycle(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
) -> ControlledStagingJobRecoveryResult:
    """Restore exact planned evidence and evaluate D.5 without mutating state."""

    binding = _validated_binding(minimum_slice, provider)
    derived = _derive_initial_evidence(binding)
    try:
        stored = provider.read_job_lifecycle_record(binding=binding)
    except MinimumStagingVerticalSliceError:
        raise ControlledStagingJobLifecycleError(
            "staging_job_lifecycle_state_invalid"
        ) from None
    if _canonical_record_bytes(stored) != _canonical_record_bytes(derived.record):
        raise ControlledStagingJobLifecycleError(
            "staging_job_lifecycle_state_invalid"
        )

    try:
        decisions = tuple(
            evaluate_durable_restart_recovery(
                context.snapshot,
                context.ledger,
                derived.manifest,
                lifecycle=derived.lifecycle,
                provenance=context.provenance,
            )
            for context in derived.run_contexts
        )
    except DurableRestartRecoveryError:
        raise ControlledStagingJobLifecycleError(
            "staging_job_recovery_invalid"
        ) from None
    return ControlledStagingJobRecoveryResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        runs=decisions,
    )
