"""Persist the first bounded controlled-staging D.1 transition.

This module advances exactly one fixed engine run from ``planned`` revision 0 to
``queued`` revision 1. ``queued`` is durable lifecycle evidence only: no queue
runtime, worker, transport, dispatch, orchestration, or engine execution is
created or authorized here. A durable revision-2 terminal record supersedes the
queued snapshot and prevents replay/recovery from presenting stale pre-dispatch
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
from pathlib import Path
import re

from .controlled_staging_job_lifecycle import (
    ControlledStagingJobLifecycleError,
    _canonical_record_bytes,
    _derive_initial_evidence,
    _validated_binding,
)
from .controlled_staging_transition_state import (
    ControlledStagingTransitionStateError,
    _transition_record_exists_under_lock,
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


CONTROLLED_STAGING_QUEUED_TRANSITION_VERSION = (
    "scoremosaic-controlled-staging-queued-transition-v1"
)
_TRANSITION_MAC_FIELD = "transition_integrity_mac"
_TRANSITION_MAC_DOMAIN = b"scoremosaic-controlled-staging-queued-transition-v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")


class ControlledStagingQueuedTransitionError(ValueError):
    """Stable fail-closed category for the bounded queued-transition slice."""

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
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        ) from None


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_input_invalid"
        )
    return value


def _require_engine(value: object) -> str:
    if type(value) is not str or value not in ENGINE_NAMES:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_engine_invalid"
        )
    return value


def _transition_path(
    provider: StagingUploadProvider,
    *,
    job_id: str,
    run_id: str,
) -> Path:
    if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        )
    return (
        provider._root
        / "state"
        / "job_transitions"
        / job_id
        / f"{run_id}-revision-1.json"
    )


def _transition_mac(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> str:
    key = getattr(provider, "_state_integrity_key", None)
    if type(key) is not bytes or len(key) != 32:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        )
    if type(record) is not dict or _TRANSITION_MAC_FIELD in record:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        )
    message = b"\0".join((_TRANSITION_MAC_DOMAIN, _canonical_json_bytes(record)))
    return hmac_new(key, message, sha256).hexdigest()


def _seal_transition(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> dict[str, object]:
    sealed = dict(record)
    sealed[_TRANSITION_MAC_FIELD] = _transition_mac(provider, record)
    return sealed


def _verify_transition(
    provider: StagingUploadProvider,
    sealed: dict[str, object],
) -> dict[str, object]:
    if type(sealed) is not dict or _TRANSITION_MAC_FIELD not in sealed:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        )
    observed = sealed.get(_TRANSITION_MAC_FIELD)
    if type(observed) is not str or _SHA256_RE.fullmatch(observed) is None:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        )
    record = dict(sealed)
    del record[_TRANSITION_MAC_FIELD]
    expected = _transition_mac(provider, record)
    if not compare_digest(observed, expected):
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        )
    return record


def _initial_record_under_lock(
    *,
    provider: StagingUploadProvider,
    binding,
    expected: dict[str, object],
) -> None:
    try:
        path = provider._job_lifecycle_path(binding.job_id)
        stored = provider._verify_state_record(
            kind="job_lifecycle",
            record=_decode_record(
                provider._read_file_no_follow(
                    path,
                    max_bytes=_MAX_STATE_RECORD_BYTES,
                    overflow_category="staging_state_corrupt",
                )
            ),
        )
    except MinimumStagingVerticalSliceError:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        ) from None
    if _canonical_record_bytes(stored) != _canonical_record_bytes(expected):
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        )


def _terminal_revision_exists_under_lock(
    provider: StagingUploadProvider,
    *,
    job_id: str,
    run_id: str,
) -> bool:
    try:
        return _transition_record_exists_under_lock(
            provider,
            job_id=job_id,
            run_id=run_id,
            revision=2,
        )
    except ControlledStagingTransitionStateError:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        ) from None


@dataclass(frozen=True, slots=True)
class _QueuedDerived:
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    record: dict[str, object]
    snapshot: object
    ledger: object
    provenance: object
    lifecycle: object
    manifest: object


@dataclass(frozen=True, slots=True)
class ControlledStagingQueuedTransitionResult:
    job_id: str
    source_artifact_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    state: str
    revision: int
    idempotency_record_count: int
    provenance_record_count: int
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
            or type(self.state) is not str
            or self.state != "queued"
            or type(self.revision) is not int
            or self.revision != 1
            or type(self.idempotency_record_count) is not int
            or self.idempotency_record_count != 1
            or type(self.provenance_record_count) is not int
            or self.provenance_record_count != 2
            or type(self.provenance_chain_sha256) is not str
            or _SHA256_RE.fullmatch(self.provenance_chain_sha256) is None
            or type(self.persistence_state) is not str
            or self.persistence_state not in {"written", "replay"}
        ):
            raise ControlledStagingQueuedTransitionError(
                "staging_transition_result_invalid"
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
            "version": CONTROLLED_STAGING_QUEUED_TRANSITION_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "state": self.state,
            "revision": self.revision,
            "idempotencyRecordCount": self.idempotency_record_count,
            "provenanceRecordCount": self.provenance_record_count,
            "provenanceChainSha256": self.provenance_chain_sha256,
            "persistenceState": self.persistence_state,
            "queueAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
        }


def _derive_queued(binding, engine: str):
    initial = _derive_initial_evidence(binding)
    index = ENGINE_NAMES.index(engine)
    context = initial.run_contexts[index]
    try:
        transitioned = apply_durable_transition_idempotently(
            context.ledger,
            context.snapshot,
            "queued",
        )
        provenance_result = append_durable_provenance_record_idempotently(
            context.provenance,
            transitioned.snapshot,
            initial.manifest,
            lifecycle=initial.lifecycle,
        )
    except (DurableIdempotencyError, DurableProvenanceError):
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_contract_invalid"
        ) from None

    record: dict[str, object] = {
        "version": CONTROLLED_STAGING_QUEUED_TRANSITION_VERSION,
        "environment": "staging",
        "job_id": binding.job_id,
        "source_artifact_id": binding.source_artifact_id,
        "engine": engine,
        "run_id": transitioned.snapshot.run_id,
        "dispatch_identity_sha256": transitioned.snapshot.dispatch_identity_sha256,
        "job_state": transitioned.snapshot.as_safe_dict(),
        "idempotency": transitioned.ledger.as_safe_dict(),
        "provenance": provenance_result.chain.as_safe_dict(),
        "boundaries": {
            "queueAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
        },
    }
    return initial, _QueuedDerived(
        engine=engine,
        run_id=transitioned.snapshot.run_id,
        dispatch_identity_sha256=transitioned.snapshot.dispatch_identity_sha256,
        record=record,
        snapshot=transitioned.snapshot,
        ledger=transitioned.ledger,
        provenance=provenance_result.chain,
        lifecycle=initial.lifecycle,
        manifest=initial.manifest,
    )


def _result(
    *,
    binding,
    derived: _QueuedDerived,
    persistence_state: str,
) -> ControlledStagingQueuedTransitionResult:
    return ControlledStagingQueuedTransitionResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        engine=derived.engine,
        run_id=derived.run_id,
        dispatch_identity_sha256=derived.dispatch_identity_sha256,
        state=derived.snapshot.state,
        revision=derived.snapshot.revision,
        idempotency_record_count=len(derived.ledger.records),
        provenance_record_count=len(derived.provenance.records),
        provenance_chain_sha256=derived.provenance.chain_sha256,
        persistence_state=persistence_state,
    )


def queue_controlled_staging_run(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    engine: str,
) -> ControlledStagingQueuedTransitionResult:
    """Persist exactly ``planned(0) -> queued(1)`` for one staging engine run."""

    checked_provider = _require_provider(provider)
    checked_engine = _require_engine(engine)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_input_invalid"
        ) from None
    initial, queued = _derive_queued(binding, checked_engine)
    path = _transition_path(
        checked_provider,
        job_id=binding.job_id,
        run_id=queued.run_id,
    )
    sealed_payload = _canonical_json_bytes(
        _seal_transition(checked_provider, queued.record)
    )
    if len(sealed_payload) > _MAX_STATE_RECORD_BYTES:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_state_invalid"
        )

    try:
        with checked_provider._job_lock(binding.job_id):
            with checked_provider._verified_source_guard(binding) as assert_source_stable:
                _initial_record_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    expected=initial.record,
                )
                if _terminal_revision_exists_under_lock(
                    checked_provider,
                    job_id=binding.job_id,
                    run_id=queued.run_id,
                ):
                    raise ControlledStagingQueuedTransitionError(
                        "staging_transition_superseded"
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
                    stored = _verify_transition(
                        checked_provider,
                        _decode_record(
                            checked_provider._read_file_no_follow(
                                path,
                                max_bytes=_MAX_STATE_RECORD_BYTES,
                                overflow_category="staging_state_corrupt",
                            )
                        ),
                    )
                    if _canonical_json_bytes(stored) != _canonical_json_bytes(
                        queued.record
                    ):
                        raise ControlledStagingQueuedTransitionError(
                            "staging_transition_state_invalid"
                        )
                    if _terminal_revision_exists_under_lock(
                        checked_provider,
                        job_id=binding.job_id,
                        run_id=queued.run_id,
                    ):
                        raise ControlledStagingQueuedTransitionError(
                            "staging_transition_superseded"
                        )
                    assert_source_stable()
                    persistence_state = "replay"
    except ControlledStagingQueuedTransitionError:
        raise
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_transition_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_transition_state_invalid"
        )
        raise ControlledStagingQueuedTransitionError(category) from None

    return _result(
        binding=binding,
        derived=queued,
        persistence_state=persistence_state,
    )


def recover_controlled_staging_queued_run(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    engine: str,
) -> DurableRestartRecoveryDecision:
    """Restore exact queued evidence and evaluate read-only D.5 recovery."""

    checked_provider = _require_provider(provider)
    checked_engine = _require_engine(engine)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_input_invalid"
        ) from None
    initial, queued = _derive_queued(binding, checked_engine)
    path = _transition_path(
        checked_provider,
        job_id=binding.job_id,
        run_id=queued.run_id,
    )

    try:
        with checked_provider._job_lock(binding.job_id):
            with checked_provider._verified_source_guard(binding) as assert_source_stable:
                _initial_record_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    expected=initial.record,
                )
                if _terminal_revision_exists_under_lock(
                    checked_provider,
                    job_id=binding.job_id,
                    run_id=queued.run_id,
                ):
                    raise ControlledStagingQueuedTransitionError(
                        "staging_transition_superseded"
                    )
                try:
                    sealed = _decode_record(
                        checked_provider._read_file_no_follow(
                            path,
                            max_bytes=_MAX_STATE_RECORD_BYTES,
                            overflow_category="staging_state_corrupt",
                        )
                    )
                except MinimumStagingVerticalSliceError as exc:
                    if exc.category == "staging_path_invalid":
                        raise ControlledStagingQueuedTransitionError(
                            "staging_transition_missing"
                        ) from None
                    raise
                stored = _verify_transition(checked_provider, sealed)
                if _canonical_json_bytes(stored) != _canonical_json_bytes(
                    queued.record
                ):
                    raise ControlledStagingQueuedTransitionError(
                        "staging_transition_state_invalid"
                    )
                if _terminal_revision_exists_under_lock(
                    checked_provider,
                    job_id=binding.job_id,
                    run_id=queued.run_id,
                ):
                    raise ControlledStagingQueuedTransitionError(
                        "staging_transition_superseded"
                    )
                assert_source_stable()
    except ControlledStagingQueuedTransitionError:
        raise
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_transition_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_transition_state_invalid"
        )
        raise ControlledStagingQueuedTransitionError(category) from None

    try:
        return evaluate_durable_restart_recovery(
            queued.snapshot,
            queued.ledger,
            queued.manifest,
            lifecycle=queued.lifecycle,
            provenance=queued.provenance,
        )
    except DurableRestartRecoveryError:
        raise ControlledStagingQueuedTransitionError(
            "staging_transition_recovery_invalid"
        ) from None
