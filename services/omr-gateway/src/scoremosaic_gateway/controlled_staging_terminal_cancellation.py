"""Atomic pre-dispatch terminal cancellation for one controlled staging run.

This bounded slice advances only an exact provider-backed ``queued`` revision-1
engine run to ``cancelled`` revision 2. Before publication it deterministically
converges that run's candidate and all expected output artifacts to terminal
states, verifies D.2/D.4/D.5 evidence, and then publishes one HMAC-sealed
revision-2 convergence record atomically.

It resolves no credential, signs no request, starts no queue or worker, sends no
network request, executes no engine, writes no output artifact bytes, deletes no
artifact, and grants no retry, orchestration, approval, or publication authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import re

from .artifact_lifecycle import (
    ArtifactLifecycleError,
    CandidateArtifactLifecycle,
    transition_artifact,
    transition_candidate,
)
from .controlled_staging_job_lifecycle import (
    ControlledStagingJobLifecycleError,
    _validated_binding,
)
from .controlled_staging_queued_transition import (
    ControlledStagingQueuedTransitionError,
    _canonical_json_bytes as _queued_canonical_json_bytes,
    _derive_queued,
    _initial_record_under_lock,
    _verify_transition as _verify_queued_transition,
)
from .controlled_staging_transition_state import (
    ControlledStagingTransitionStateError,
    _transition_record_exists_under_lock,
    transition_record_path,
)
from .durable_idempotency import (
    DurableIdempotencyError,
    apply_durable_transition_idempotently,
)
from .durable_provenance import (
    DurableProvenanceError,
    append_durable_provenance_record_idempotently,
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
    _MAX_STATE_RECORD_BYTES,
    _decode_record,
)
from .orchestration import ENGINE_NAMES


CONTROLLED_STAGING_TERMINAL_CANCELLATION_VERSION = (
    "scoremosaic-controlled-staging-terminal-cancellation-v1"
)
CANCELLATION_REASON_CODE = "pre_dispatch_cancelled"
_CANCELLATION_MAC_FIELD = "cancellation_integrity_mac"
_CANCELLATION_MAC_DOMAIN = b"scoremosaic-controlled-staging-terminal-cancellation-v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")


class ControlledStagingTerminalCancellationError(ValueError):
    """Stable fail-closed category for pre-dispatch terminal cancellation."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        ) from None


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_input_invalid"
        )
    return value


def _require_engine(value: object) -> str:
    if type(value) is not str or value not in ENGINE_NAMES:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_engine_invalid"
        )
    return value


def _cancellation_mac(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> str:
    key = getattr(provider, "_state_integrity_key", None)
    if type(key) is not bytes or len(key) != 32:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        )
    if type(record) is not dict or _CANCELLATION_MAC_FIELD in record:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        )
    message = b"\0".join((_CANCELLATION_MAC_DOMAIN, _canonical_json_bytes(record)))
    return hmac_new(key, message, sha256).hexdigest()


def _seal_cancellation(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> dict[str, object]:
    sealed = dict(record)
    sealed[_CANCELLATION_MAC_FIELD] = _cancellation_mac(provider, record)
    return sealed


def _verify_cancellation(
    provider: StagingUploadProvider,
    sealed: dict[str, object],
) -> dict[str, object]:
    if type(sealed) is not dict or _CANCELLATION_MAC_FIELD not in sealed:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        )
    observed = sealed.get(_CANCELLATION_MAC_FIELD)
    if type(observed) is not str or _SHA256_RE.fullmatch(observed) is None:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        )
    record = dict(sealed)
    del record[_CANCELLATION_MAC_FIELD]
    expected = _cancellation_mac(provider, record)
    if not compare_digest(observed, expected):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        )
    return record


@dataclass(frozen=True, slots=True)
class _CancelledDerived:
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    record: dict[str, object]
    snapshot: object
    ledger: object
    provenance: object
    lifecycle: CandidateArtifactLifecycle
    manifest: object
    recovery: DurableRestartRecoveryDecision


@dataclass(frozen=True, slots=True)
class ControlledStagingTerminalCancellationResult:
    job_id: str
    source_artifact_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    reason_code: str
    state: str
    revision: int
    idempotency_record_count: int
    provenance_record_count: int
    lifecycle_sha256: str
    storage_manifest_sha256: str
    provenance_chain_sha256: str
    persistence_state: str

    def __post_init__(self) -> None:
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
            or type(self.reason_code) is not str
            or self.reason_code != CANCELLATION_REASON_CODE
            or type(self.state) is not str
            or self.state != "cancelled"
            or type(self.revision) is not int
            or self.revision != 2
            or type(self.idempotency_record_count) is not int
            or self.idempotency_record_count != 2
            or type(self.provenance_record_count) is not int
            or self.provenance_record_count != 3
            or type(self.lifecycle_sha256) is not str
            or _SHA256_RE.fullmatch(self.lifecycle_sha256) is None
            or type(self.storage_manifest_sha256) is not str
            or _SHA256_RE.fullmatch(self.storage_manifest_sha256) is None
            or type(self.provenance_chain_sha256) is not str
            or _SHA256_RE.fullmatch(self.provenance_chain_sha256) is None
            or type(self.persistence_state) is not str
            or self.persistence_state not in {"written", "replay"}
        ):
            raise ControlledStagingTerminalCancellationError(
                "staging_cancellation_result_invalid"
            )

    @property
    def cancellation_allowed(self) -> bool:
        return False

    @property
    def queue_runtime_allowed(self) -> bool:
        return False

    @property
    def worker_allowed(self) -> bool:
        return False

    @property
    def credential_resolution_allowed(self) -> bool:
        return False

    @property
    def request_signing_allowed(self) -> bool:
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

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def output_storage_write_allowed(self) -> bool:
        return False

    @property
    def source_mutation_allowed(self) -> bool:
        return False

    @property
    def artifact_delete_allowed(self) -> bool:
        return False

    @property
    def teacher_review_allowed(self) -> bool:
        return False

    @property
    def approval_allowed(self) -> bool:
        return False

    @property
    def publication_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_TERMINAL_CANCELLATION_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "reasonCode": self.reason_code,
            "state": self.state,
            "revision": self.revision,
            "idempotencyRecordCount": self.idempotency_record_count,
            "provenanceRecordCount": self.provenance_record_count,
            "lifecycleSha256": self.lifecycle_sha256,
            "storageManifestSha256": self.storage_manifest_sha256,
            "provenanceChainSha256": self.provenance_chain_sha256,
            "persistenceState": self.persistence_state,
            "cancellationAllowed": False,
            "queueRuntimeAllowed": False,
            "workerAllowed": False,
            "credentialResolutionAllowed": False,
            "requestSigningAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
            "outputStorageWriteAllowed": False,
            "sourceMutationAllowed": False,
            "artifactDeleteAllowed": False,
            "teacherReviewAllowed": False,
            "approvalAllowed": False,
            "publicationAllowed": False,
        }


def _derive_cancelled(binding, engine: str):
    try:
        initial, queued = _derive_queued(binding, engine)
    except ControlledStagingQueuedTransitionError:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_contract_invalid"
        ) from None

    candidates = tuple(
        candidate
        for candidate in queued.lifecycle.candidates
        if candidate.run_id == queued.run_id and candidate.engine == engine
    )
    if len(candidates) != 1:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_contract_invalid"
        )
    candidate = candidates[0]
    lifecycle = queued.lifecycle

    try:
        for artifact in candidate.artifacts:
            lifecycle = transition_artifact(
                lifecycle,
                artifact.artifact_id,
                "abandoned",
                reason_code=CANCELLATION_REASON_CODE,
            )
        lifecycle = transition_candidate(
            lifecycle,
            candidate.candidate_id,
            "cancelled",
            reason_code=CANCELLATION_REASON_CODE,
        )
        transitioned = apply_durable_transition_idempotently(
            queued.ledger,
            queued.snapshot,
            "cancelled",
        )
        provenance_result = append_durable_provenance_record_idempotently(
            queued.provenance,
            transitioned.snapshot,
            queued.manifest,
            lifecycle=lifecycle,
        )
        recovery = evaluate_durable_restart_recovery(
            transitioned.snapshot,
            transitioned.ledger,
            queued.manifest,
            lifecycle=lifecycle,
            provenance=provenance_result.chain,
        )
    except (
        ArtifactLifecycleError,
        DurableIdempotencyError,
        DurableProvenanceError,
        DurableRestartRecoveryError,
    ):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_contract_invalid"
        ) from None

    if (
        recovery.state != "cancelled"
        or recovery.revision != 2
        or recovery.disposition != "terminal_preserved"
        or not recovery.terminal
        or recovery.reconciliation_required
        or recovery.automatic_execution_allowed
        or recovery.retry_allowed
        or recovery.network_dispatch_allowed
        or recovery.state_mutation_allowed
    ):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_contract_invalid"
        )

    cancelled_candidate = next(
        item
        for item in lifecycle.candidates
        if item.candidate_id == candidate.candidate_id
    )
    if (
        cancelled_candidate.state != "cancelled"
        or cancelled_candidate.reason_code != CANCELLATION_REASON_CODE
        or any(
            artifact.state != "abandoned"
            or artifact.reason_code != CANCELLATION_REASON_CODE
            or artifact.sha256 is not None
            or artifact.size_bytes is not None
            or artifact.media_type is not None
            for artifact in cancelled_candidate.artifacts
        )
        or any(
            record.candidate_id == cancelled_candidate.candidate_id
            for record in queued.manifest.records
        )
    ):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_contract_invalid"
        )

    record: dict[str, object] = {
        "version": CONTROLLED_STAGING_TERMINAL_CANCELLATION_VERSION,
        "environment": "staging",
        "job_id": binding.job_id,
        "source_artifact_id": binding.source_artifact_id,
        "engine": engine,
        "run_id": transitioned.snapshot.run_id,
        "dispatch_identity_sha256": transitioned.snapshot.dispatch_identity_sha256,
        "reason_code": CANCELLATION_REASON_CODE,
        "job_state": transitioned.snapshot.as_safe_dict(),
        "idempotency": transitioned.ledger.as_safe_dict(),
        "candidate_lifecycle": lifecycle.as_dict(),
        "storage_manifest": queued.manifest.as_safe_dict(),
        "provenance": provenance_result.chain.as_safe_dict(),
        "recovery": recovery.as_safe_dict(),
        "boundaries": {
            "cancellationAllowed": False,
            "queueRuntimeAllowed": False,
            "workerAllowed": False,
            "credentialResolutionAllowed": False,
            "requestSigningAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
            "outputStorageWriteAllowed": False,
            "sourceMutationAllowed": False,
            "artifactDeleteAllowed": False,
            "teacherReviewAllowed": False,
            "approvalAllowed": False,
            "publicationAllowed": False,
        },
    }
    return initial, queued, _CancelledDerived(
        engine=engine,
        run_id=transitioned.snapshot.run_id,
        dispatch_identity_sha256=transitioned.snapshot.dispatch_identity_sha256,
        record=record,
        snapshot=transitioned.snapshot,
        ledger=transitioned.ledger,
        provenance=provenance_result.chain,
        lifecycle=lifecycle,
        manifest=queued.manifest,
        recovery=recovery,
    )


def _verify_queued_under_lock(
    *,
    provider: StagingUploadProvider,
    binding,
    initial,
    queued,
) -> None:
    try:
        _initial_record_under_lock(
            provider=provider,
            binding=binding,
            expected=initial.record,
        )
    except ControlledStagingQueuedTransitionError:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        ) from None

    try:
        present = _transition_record_exists_under_lock(
            provider,
            job_id=binding.job_id,
            run_id=queued.run_id,
            revision=1,
        )
    except ControlledStagingTransitionStateError:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        ) from None

    if not present:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_queued_missing"
        )

    try:
        path = transition_record_path(
            provider,
            job_id=binding.job_id,
            run_id=queued.run_id,
            revision=1,
        )
        stored = _verify_queued_transition(
            provider,
            _decode_record(
                provider._read_file_no_follow(
                    path,
                    max_bytes=_MAX_STATE_RECORD_BYTES,
                    overflow_category="staging_state_corrupt",
                )
            ),
        )
    except (
        ControlledStagingQueuedTransitionError,
        ControlledStagingTransitionStateError,
        MinimumStagingVerticalSliceError,
    ):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        ) from None

    if _queued_canonical_json_bytes(stored) != _queued_canonical_json_bytes(
        queued.record
    ):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        )


def _result(
    *,
    binding,
    derived: _CancelledDerived,
    persistence_state: str,
) -> ControlledStagingTerminalCancellationResult:
    return ControlledStagingTerminalCancellationResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        engine=derived.engine,
        run_id=derived.run_id,
        dispatch_identity_sha256=derived.dispatch_identity_sha256,
        reason_code=CANCELLATION_REASON_CODE,
        state=derived.snapshot.state,
        revision=derived.snapshot.revision,
        idempotency_record_count=len(derived.ledger.records),
        provenance_record_count=len(derived.provenance.records),
        lifecycle_sha256=derived.lifecycle.lifecycle_sha256,
        storage_manifest_sha256=derived.manifest.manifest_sha256,
        provenance_chain_sha256=derived.provenance.chain_sha256,
        persistence_state=persistence_state,
    )


def _load_and_verify_cancellation_under_lock(
    *,
    provider: StagingUploadProvider,
    binding,
    cancelled: _CancelledDerived,
) -> None:
    try:
        if not _transition_record_exists_under_lock(
            provider,
            job_id=binding.job_id,
            run_id=cancelled.run_id,
            revision=2,
        ):
            raise ControlledStagingTerminalCancellationError(
                "staging_cancellation_missing"
            )
        path = transition_record_path(
            provider,
            job_id=binding.job_id,
            run_id=cancelled.run_id,
            revision=2,
        )
        stored = _verify_cancellation(
            provider,
            _decode_record(
                provider._read_file_no_follow(
                    path,
                    max_bytes=_MAX_STATE_RECORD_BYTES,
                    overflow_category="staging_state_corrupt",
                )
            ),
        )
    except ControlledStagingTerminalCancellationError:
        raise
    except (
        ControlledStagingTransitionStateError,
        MinimumStagingVerticalSliceError,
    ):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        ) from None

    if _canonical_json_bytes(stored) != _canonical_json_bytes(cancelled.record):
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        )


def cancel_controlled_staging_queued_run(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    engine: str,
) -> ControlledStagingTerminalCancellationResult:
    """Atomically publish exact ``queued(1) -> cancelled(2)`` convergence."""

    checked_provider = _require_provider(provider)
    checked_engine = _require_engine(engine)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_input_invalid"
        ) from None

    initial, queued, cancelled = _derive_cancelled(binding, checked_engine)
    path = transition_record_path(
        checked_provider,
        job_id=binding.job_id,
        run_id=cancelled.run_id,
        revision=2,
    )
    sealed_payload = _canonical_json_bytes(
        _seal_cancellation(checked_provider, cancelled.record)
    )
    if len(sealed_payload) > _MAX_STATE_RECORD_BYTES:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        )

    try:
        with checked_provider._job_lock(binding.job_id):
            with checked_provider._verified_source_guard(
                binding
            ) as assert_source_stable:
                _verify_queued_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    initial=initial,
                    queued=queued,
                )
                assert_source_stable()
                created = checked_provider._atomic_create(
                    path,
                    sealed_payload,
                    prepublish_check=assert_source_stable,
                    postpublish_check=assert_source_stable,
                )
                if created:
                    persistence_state = "written"
                else:
                    _load_and_verify_cancellation_under_lock(
                        provider=checked_provider,
                        binding=binding,
                        cancelled=cancelled,
                    )
                    assert_source_stable()
                    persistence_state = "replay"
    except ControlledStagingTerminalCancellationError:
        raise
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_cancellation_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_cancellation_state_invalid"
        )
        raise ControlledStagingTerminalCancellationError(category) from None
    except ControlledStagingTransitionStateError:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        ) from None

    return _result(
        binding=binding,
        derived=cancelled,
        persistence_state=persistence_state,
    )


def recover_controlled_staging_cancelled_run(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    engine: str,
) -> DurableRestartRecoveryDecision:
    """Restore exact revision-2 cancellation evidence and return read-only D.5."""

    checked_provider = _require_provider(provider)
    checked_engine = _require_engine(engine)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_input_invalid"
        ) from None

    initial, queued, cancelled = _derive_cancelled(binding, checked_engine)

    try:
        with checked_provider._job_lock(binding.job_id):
            with checked_provider._verified_source_guard(
                binding
            ) as assert_source_stable:
                _verify_queued_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    initial=initial,
                    queued=queued,
                )
                _load_and_verify_cancellation_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    cancelled=cancelled,
                )
                assert_source_stable()
    except ControlledStagingTerminalCancellationError:
        raise
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_cancellation_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_cancellation_state_invalid"
        )
        raise ControlledStagingTerminalCancellationError(category) from None
    except ControlledStagingTransitionStateError:
        raise ControlledStagingTerminalCancellationError(
            "staging_cancellation_state_invalid"
        ) from None

    return cancelled.recovery
