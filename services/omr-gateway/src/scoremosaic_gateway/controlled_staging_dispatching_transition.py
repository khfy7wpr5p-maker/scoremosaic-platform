"""Atomic controlled-staging ``queued(1) -> dispatching(2)`` transition.

Revision 2 is the single durable arbitration slot shared with pre-dispatch
terminal cancellation. Publication is serialized by the existing job lock and
performed with the provider's create-once primitive, so exactly one competing
revision-2 outcome can become authoritative. Once dispatching is durable,
restart/recovery is deliberately reconciliation-only: no automatic retry,
network resend, execution resume, or state mutation authority is granted.

This module does not resolve credentials, sign requests, send network traffic,
execute engines, write result artifacts, or mutate source bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import re

from .config import EngineEndpoint
from .controlled_staging_dispatch_intent import (
    ControlledStagingDispatchIntentError,
    _canonical_json_bytes as _intent_canonical_json_bytes,
    _derive_intent,
    _load_and_verify_intent_under_lock,
)
from .controlled_staging_job_lifecycle import (
    ControlledStagingJobLifecycleError,
    _validated_binding,
)
from .controlled_staging_queued_transition import (
    ControlledStagingQueuedTransitionError,
    _derive_queued,
)
from .controlled_staging_terminal_cancellation import _verify_queued_under_lock
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


CONTROLLED_STAGING_DISPATCHING_TRANSITION_VERSION = (
    "scoremosaic-controlled-staging-dispatching-transition-v1"
)
_DISPATCHING_MAC_FIELD = "dispatching_integrity_mac"
_DISPATCHING_MAC_DOMAIN = b"scoremosaic-controlled-staging-dispatching-transition-v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")


class ControlledStagingDispatchingTransitionError(ValueError):
    """Stable fail-closed category for revision-2 dispatch arbitration."""

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
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        ) from None


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_input_invalid"
        )
    return value


def _require_endpoint(value: object) -> EngineEndpoint:
    if (
        type(value) is not EngineEndpoint
        or type(value.name) is not str
        or value.name not in ENGINE_NAMES
        or type(value.base_url) is not str
    ):
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_endpoint_invalid"
        )
    return value


def _dispatching_mac(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> str:
    key = getattr(provider, "_state_integrity_key", None)
    if type(key) is not bytes or len(key) != 32:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        )
    if type(record) is not dict or _DISPATCHING_MAC_FIELD in record:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        )
    message = b"\0".join((_DISPATCHING_MAC_DOMAIN, _canonical_json_bytes(record)))
    return hmac_new(key, message, sha256).hexdigest()


def _seal_dispatching(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> dict[str, object]:
    sealed = dict(record)
    sealed[_DISPATCHING_MAC_FIELD] = _dispatching_mac(provider, record)
    return sealed


def _verify_dispatching(
    provider: StagingUploadProvider,
    sealed: dict[str, object],
) -> dict[str, object]:
    if type(sealed) is not dict or _DISPATCHING_MAC_FIELD not in sealed:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_revision_conflict"
        )
    observed = sealed.get(_DISPATCHING_MAC_FIELD)
    if type(observed) is not str or _SHA256_RE.fullmatch(observed) is None:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        )
    record = dict(sealed)
    del record[_DISPATCHING_MAC_FIELD]
    if not compare_digest(observed, _dispatching_mac(provider, record)):
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        )
    return record


@dataclass(frozen=True, slots=True)
class _DispatchingDerived:
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    dispatch_intent_sha256: str
    record: dict[str, object]
    snapshot: object
    ledger: object
    provenance: object
    lifecycle: object
    manifest: object
    recovery: DurableRestartRecoveryDecision


@dataclass(frozen=True, slots=True)
class ControlledStagingDispatchingTransitionResult:
    job_id: str
    source_artifact_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    dispatch_intent_sha256: str
    state: str
    revision: int
    idempotency_record_count: int
    provenance_record_count: int
    provenance_chain_sha256: str
    recovery_disposition: str
    reconciliation_required: bool
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
            or type(self.dispatch_intent_sha256) is not str
            or _SHA256_RE.fullmatch(self.dispatch_intent_sha256) is None
            or self.state != "dispatching"
            or self.revision != 2
            or self.idempotency_record_count != 2
            or self.provenance_record_count != 3
            or type(self.provenance_chain_sha256) is not str
            or _SHA256_RE.fullmatch(self.provenance_chain_sha256) is None
            or self.recovery_disposition != "reconciliation_required"
            or self.reconciliation_required is not True
            or self.persistence_state not in {"written", "replay"}
        ):
            raise ControlledStagingDispatchingTransitionError(
                "staging_dispatching_result_invalid"
            )

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
    def automatic_retry_allowed(self) -> bool:
        return False

    @property
    def automatic_execution_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    @property
    def further_state_mutation_allowed(self) -> bool:
        return False

    @property
    def source_mutation_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_DISPATCHING_TRANSITION_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "dispatchIntentSha256": self.dispatch_intent_sha256,
            "state": self.state,
            "revision": self.revision,
            "idempotencyRecordCount": self.idempotency_record_count,
            "provenanceRecordCount": self.provenance_record_count,
            "provenanceChainSha256": self.provenance_chain_sha256,
            "recoveryDisposition": self.recovery_disposition,
            "reconciliationRequired": self.reconciliation_required,
            "persistenceState": self.persistence_state,
            "credentialResolutionAllowed": False,
            "requestSigningAllowed": False,
            "networkDispatchAllowed": False,
            "automaticRetryAllowed": False,
            "automaticExecutionAllowed": False,
            "engineExecutionAllowed": False,
            "furtherStateMutationAllowed": False,
            "sourceMutationAllowed": False,
        }


def _derive_dispatching(binding, endpoint: EngineEndpoint):
    try:
        initial, queued = _derive_queued(binding, endpoint.name)
        _, intent_queued, intent = _derive_intent(binding, endpoint)
        transitioned = apply_durable_transition_idempotently(
            queued.ledger,
            queued.snapshot,
            "dispatching",
        )
        provenance_result = append_durable_provenance_record_idempotently(
            queued.provenance,
            transitioned.snapshot,
            queued.manifest,
            lifecycle=queued.lifecycle,
        )
        recovery = evaluate_durable_restart_recovery(
            transitioned.snapshot,
            transitioned.ledger,
            queued.manifest,
            lifecycle=queued.lifecycle,
            provenance=provenance_result.chain,
        )
    except (
        ControlledStagingQueuedTransitionError,
        ControlledStagingDispatchIntentError,
        DurableIdempotencyError,
        DurableProvenanceError,
        DurableRestartRecoveryError,
    ):
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_contract_invalid"
        ) from None

    intent_sha256 = sha256(_intent_canonical_json_bytes(intent.record)).hexdigest()
    if (
        intent_queued.run_id != queued.run_id
        or intent.engine != queued.engine
        or intent.run_id != queued.run_id
        or intent.dispatch_identity_sha256 != queued.dispatch_identity_sha256
        or transitioned.snapshot.state != "dispatching"
        or transitioned.snapshot.revision != 2
        or recovery.state != "dispatching"
        or recovery.revision != 2
        or recovery.disposition != "reconciliation_required"
        or recovery.terminal
        or not recovery.reconciliation_required
        or recovery.automatic_execution_allowed
        or recovery.retry_allowed
        or recovery.network_dispatch_allowed
        or recovery.state_mutation_allowed
    ):
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_contract_invalid"
        )

    record: dict[str, object] = {
        "version": CONTROLLED_STAGING_DISPATCHING_TRANSITION_VERSION,
        "environment": "staging",
        "job_id": binding.job_id,
        "source_artifact_id": binding.source_artifact_id,
        "engine": endpoint.name,
        "run_id": transitioned.snapshot.run_id,
        "dispatch_identity_sha256": transitioned.snapshot.dispatch_identity_sha256,
        "dispatch_intent_sha256": intent_sha256,
        "job_state": transitioned.snapshot.as_safe_dict(),
        "idempotency": transitioned.ledger.as_safe_dict(),
        "provenance": provenance_result.chain.as_safe_dict(),
        "recovery": recovery.as_safe_dict(),
        "boundaries": {
            "credentialResolutionAllowed": False,
            "requestSigningAllowed": False,
            "networkDispatchAllowed": False,
            "automaticRetryAllowed": False,
            "automaticExecutionAllowed": False,
            "engineExecutionAllowed": False,
            "furtherStateMutationAllowed": False,
            "sourceMutationAllowed": False,
        },
    }
    return initial, queued, intent, _DispatchingDerived(
        engine=endpoint.name,
        run_id=transitioned.snapshot.run_id,
        dispatch_identity_sha256=transitioned.snapshot.dispatch_identity_sha256,
        dispatch_intent_sha256=intent_sha256,
        record=record,
        snapshot=transitioned.snapshot,
        ledger=transitioned.ledger,
        provenance=provenance_result.chain,
        lifecycle=queued.lifecycle,
        manifest=queued.manifest,
        recovery=recovery,
    )


def _load_and_verify_dispatching_under_lock(
    *,
    provider: StagingUploadProvider,
    binding,
    derived: _DispatchingDerived,
) -> None:
    path = transition_record_path(
        provider,
        job_id=binding.job_id,
        run_id=derived.run_id,
        revision=2,
    )
    try:
        if not _transition_record_exists_under_lock(
            provider,
            job_id=binding.job_id,
            run_id=derived.run_id,
            revision=2,
        ):
            raise ControlledStagingDispatchingTransitionError(
                "staging_dispatching_missing"
            )
        sealed = _decode_record(
            provider._read_file_no_follow(
                path,
                max_bytes=_MAX_STATE_RECORD_BYTES,
                overflow_category="staging_state_corrupt",
            )
        )
        stored = _verify_dispatching(provider, sealed)
    except ControlledStagingDispatchingTransitionError:
        raise
    except (
        ControlledStagingTransitionStateError,
        MinimumStagingVerticalSliceError,
    ):
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        ) from None

    if _canonical_json_bytes(stored) != _canonical_json_bytes(derived.record):
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        )


def _result(
    *,
    binding,
    derived: _DispatchingDerived,
    persistence_state: str,
) -> ControlledStagingDispatchingTransitionResult:
    return ControlledStagingDispatchingTransitionResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        engine=derived.engine,
        run_id=derived.run_id,
        dispatch_identity_sha256=derived.dispatch_identity_sha256,
        dispatch_intent_sha256=derived.dispatch_intent_sha256,
        state=derived.snapshot.state,
        revision=derived.snapshot.revision,
        idempotency_record_count=len(derived.ledger.records),
        provenance_record_count=len(derived.provenance.records),
        provenance_chain_sha256=derived.provenance.chain_sha256,
        recovery_disposition=derived.recovery.disposition,
        reconciliation_required=derived.recovery.reconciliation_required,
        persistence_state=persistence_state,
    )


def transition_controlled_staging_queued_to_dispatching(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
) -> ControlledStagingDispatchingTransitionResult:
    """Atomically claim the shared revision-2 slot as ``dispatching``.

    The durable state is published before any future transport attempt. A crash
    after publication is therefore treated conservatively as an ambiguous
    in-flight operation that requires reconciliation and cannot auto-retry.
    """

    checked_provider = _require_provider(provider)
    checked_endpoint = _require_endpoint(endpoint)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_input_invalid"
        ) from None

    initial, queued, intent, dispatching = _derive_dispatching(binding, checked_endpoint)
    path = transition_record_path(
        checked_provider,
        job_id=binding.job_id,
        run_id=dispatching.run_id,
        revision=2,
    )
    sealed_payload = _canonical_json_bytes(
        _seal_dispatching(checked_provider, dispatching.record)
    )
    if len(sealed_payload) > _MAX_STATE_RECORD_BYTES:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
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
                _load_and_verify_intent_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    derived=intent,
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
                    _load_and_verify_dispatching_under_lock(
                        provider=checked_provider,
                        binding=binding,
                        derived=dispatching,
                    )
                    assert_source_stable()
                    persistence_state = "replay"
    except ControlledStagingDispatchingTransitionError:
        raise
    except ControlledStagingDispatchIntentError:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_intent_invalid"
        ) from None
    except ControlledStagingTransitionStateError:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        ) from None
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_dispatching_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_dispatching_state_invalid"
        )
        raise ControlledStagingDispatchingTransitionError(category) from None

    return _result(
        binding=binding,
        derived=dispatching,
        persistence_state=persistence_state,
    )


def recover_controlled_staging_dispatching_run(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
) -> DurableRestartRecoveryDecision:
    """Restore exact dispatching evidence and return reconciliation-only D.5."""

    checked_provider = _require_provider(provider)
    checked_endpoint = _require_endpoint(endpoint)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_input_invalid"
        ) from None

    initial, queued, intent, dispatching = _derive_dispatching(binding, checked_endpoint)
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
                _load_and_verify_intent_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    derived=intent,
                )
                _load_and_verify_dispatching_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    derived=dispatching,
                )
                assert_source_stable()
    except ControlledStagingDispatchingTransitionError:
        raise
    except ControlledStagingDispatchIntentError:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_intent_invalid"
        ) from None
    except ControlledStagingTransitionStateError:
        raise ControlledStagingDispatchingTransitionError(
            "staging_dispatching_state_invalid"
        ) from None
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_dispatching_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_dispatching_state_invalid"
        )
        raise ControlledStagingDispatchingTransitionError(category) from None

    return dispatching.recovery
