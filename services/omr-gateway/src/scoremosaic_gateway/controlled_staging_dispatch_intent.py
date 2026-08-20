"""Atomic non-executable dispatch intent for one controlled staging run.

This bounded slice persists the exact non-secret identity and private target for
one provider-backed ``queued`` revision-1 engine run. The D.1 job state remains
``queued``: no ``dispatching`` transition is written because no dispatch attempt
has occurred.

The intent stores no credential material, resolver key, timestamp, nonce,
signature, request body, or transport authority. It starts no queue or worker,
sends no network request, executes no engine, and grants no retry or state
mutation authority. A terminal revision-2 record always supersedes the intent.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
from pathlib import Path
import re

from .config import EngineEndpoint
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
from .dispatch_identity import (
    MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES,
    DispatchIdentityError,
    build_dispatch_identity,
    dispatch_identity_payload,
)
from .dispatch_target import (
    DISPATCH_METHOD,
    DISPATCH_PATH,
    DispatchTargetError,
    build_engine_dispatch_target,
)
from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError,
    MinimumStagingVerticalSliceResult,
    StagingUploadProvider,
    _MAX_STATE_RECORD_BYTES,
    _decode_record,
)
from .orchestration import (
    ENGINE_NAMES,
    OrchestrationContractError,
    build_orchestration_plan,
)
from .service_auth import ServiceAuthError, build_engine_auth_binding


CONTROLLED_STAGING_DISPATCH_INTENT_VERSION = (
    "scoremosaic-controlled-staging-dispatch-intent-v1"
)
_INTENT_MAC_FIELD = "dispatch_intent_integrity_mac"
_INTENT_MAC_DOMAIN = b"scoremosaic-controlled-staging-dispatch-intent-v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")


class ControlledStagingDispatchIntentError(ValueError):
    """Stable fail-closed category for the non-executable dispatch intent."""

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
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        ) from None


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_input_invalid"
        )
    return value


def _require_endpoint(value: object) -> EngineEndpoint:
    if (
        type(value) is not EngineEndpoint
        or type(value.name) is not str
        or value.name not in ENGINE_NAMES
        or type(value.base_url) is not str
    ):
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_endpoint_invalid"
        )
    return value


def _intent_path(
    provider: StagingUploadProvider,
    *,
    job_id: str,
    run_id: str,
) -> Path:
    if type(job_id) is not str or _JOB_ID_RE.fullmatch(job_id) is None:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )
    if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )
    return (
        provider._root
        / "state"
        / "dispatch_intents"
        / job_id
        / f"{run_id}.json"
    )


def _intent_mac(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> str:
    key = getattr(provider, "_state_integrity_key", None)
    if type(key) is not bytes or len(key) != 32:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )
    if type(record) is not dict or _INTENT_MAC_FIELD in record:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )
    message = b"\0".join((_INTENT_MAC_DOMAIN, _canonical_json_bytes(record)))
    return hmac_new(key, message, sha256).hexdigest()


def _seal_intent(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> dict[str, object]:
    sealed = dict(record)
    sealed[_INTENT_MAC_FIELD] = _intent_mac(provider, record)
    return sealed


def _verify_intent(
    provider: StagingUploadProvider,
    sealed: dict[str, object],
) -> dict[str, object]:
    if type(sealed) is not dict or _INTENT_MAC_FIELD not in sealed:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )
    observed = sealed.get(_INTENT_MAC_FIELD)
    if type(observed) is not str or _SHA256_RE.fullmatch(observed) is None:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )
    record = dict(sealed)
    del record[_INTENT_MAC_FIELD]
    expected = _intent_mac(provider, record)
    if not compare_digest(observed, expected):
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )
    return record


@dataclass(frozen=True, slots=True)
class _DispatchIntentDerived:
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    identity_payload_sha256: str
    identity_payload_bytes: int
    caller_identity: str
    audience_identity: str
    target_origin: str
    target_method: str
    target_path: str
    record: dict[str, object]


@dataclass(frozen=True, slots=True)
class ControlledStagingDispatchIntentResult:
    job_id: str
    source_artifact_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    identity_payload_sha256: str
    identity_payload_bytes: int
    state: str
    revision: int
    caller_identity: str
    audience_identity: str
    target_origin: str
    target_method: str
    target_path: str
    intent_sha256: str
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
            or type(self.identity_payload_sha256) is not str
            or _SHA256_RE.fullmatch(self.identity_payload_sha256) is None
            or type(self.identity_payload_bytes) is not int
            or not 1
            <= self.identity_payload_bytes
            <= MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
            or type(self.state) is not str
            or self.state != "queued"
            or type(self.revision) is not int
            or self.revision != 1
            or type(self.caller_identity) is not str
            or not self.caller_identity
            or type(self.audience_identity) is not str
            or not self.audience_identity
            or type(self.target_origin) is not str
            or not self.target_origin
            or type(self.target_method) is not str
            or self.target_method != DISPATCH_METHOD
            or type(self.target_path) is not str
            or self.target_path != DISPATCH_PATH
            or type(self.intent_sha256) is not str
            or _SHA256_RE.fullmatch(self.intent_sha256) is None
            or type(self.persistence_state) is not str
            or self.persistence_state not in {"written", "replay"}
        ):
            raise ControlledStagingDispatchIntentError(
                "staging_dispatch_intent_result_invalid"
            )

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    @property
    def credential_resolution_allowed(self) -> bool:
        return False

    @property
    def request_signing_allowed(self) -> bool:
        return False

    @property
    def nonce_allocation_allowed(self) -> bool:
        return False

    @property
    def timestamp_allocation_allowed(self) -> bool:
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
            "version": CONTROLLED_STAGING_DISPATCH_INTENT_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "identityPayloadSha256": self.identity_payload_sha256,
            "identityPayloadBytes": self.identity_payload_bytes,
            "state": self.state,
            "revision": self.revision,
            "callerIdentity": self.caller_identity,
            "audienceIdentity": self.audience_identity,
            "targetOrigin": self.target_origin,
            "targetMethod": self.target_method,
            "targetPath": self.target_path,
            "intentSha256": self.intent_sha256,
            "persistenceState": self.persistence_state,
            "jobStateMutationAllowed": False,
            "credentialResolutionAllowed": False,
            "requestSigningAllowed": False,
            "nonceAllocationAllowed": False,
            "timestampAllocationAllowed": False,
            "queueRuntimeAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "dispatchAttemptAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
        }


def _derive_intent(binding, endpoint: EngineEndpoint):
    try:
        initial, queued = _derive_queued(binding, endpoint.name)
        plan = build_orchestration_plan(
            binding.job_id,
            source_artifact_ref=binding.source_artifact_ref,
            source_sha256=binding.document_sha256,
            source_size_bytes=binding.source_size_bytes,
            source_media_type=binding.source_media_type,
            requested_engines=ENGINE_NAMES,
        )
        identity = build_dispatch_identity(plan.as_dict(), endpoint.name)
        identity_payload = dispatch_identity_payload(identity)
        auth_binding = build_engine_auth_binding(endpoint, "staging")
        target = build_engine_dispatch_target(auth_binding, endpoint)
    except (
        ControlledStagingQueuedTransitionError,
        OrchestrationContractError,
        DispatchIdentityError,
        ServiceAuthError,
        DispatchTargetError,
    ):
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_contract_invalid"
        ) from None

    if (
        plan.plan_id != binding.orchestration_plan_id
        or plan.plan_sha256 != binding.orchestration_plan_sha256
        or plan.source_artifact.artifact_id != binding.source_artifact_id
        or identity.job_id != binding.job_id
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
        or queued.snapshot.state != "queued"
        or queued.snapshot.revision != 1
        or target.environment != "staging"
        or target.engine != endpoint.name
        or target.method != DISPATCH_METHOD
        or target.path != DISPATCH_PATH
        or auth_binding.engine != endpoint.name
        or auth_binding.environment != "staging"
    ):
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_contract_invalid"
        )

    identity_payload_sha256 = sha256(identity_payload).hexdigest()
    record: dict[str, object] = {
        "version": CONTROLLED_STAGING_DISPATCH_INTENT_VERSION,
        "environment": "staging",
        "job_id": binding.job_id,
        "source_artifact_id": binding.source_artifact_id,
        "source_sha256": binding.document_sha256,
        "engine": endpoint.name,
        "run_id": identity.run_id,
        "dispatch_identity_sha256": identity.identity_sha256,
        "identity_payload_sha256": identity_payload_sha256,
        "identity_payload_bytes": len(identity_payload),
        "job_state": {
            "state": queued.snapshot.state,
            "revision": queued.snapshot.revision,
        },
        "service_identity": {
            "bindingVersion": auth_binding.version,
            "callerIdentity": auth_binding.caller_identity,
            "audienceIdentity": auth_binding.audience_identity,
        },
        "target": {
            "origin": target.origin,
            "method": target.method,
            "path": target.path,
        },
        "boundaries": {
            "jobStateMutationAllowed": False,
            "credentialResolutionAllowed": False,
            "requestSigningAllowed": False,
            "nonceAllocationAllowed": False,
            "timestampAllocationAllowed": False,
            "queueRuntimeAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "dispatchAttemptAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
        },
    }
    return initial, queued, _DispatchIntentDerived(
        engine=endpoint.name,
        run_id=identity.run_id,
        dispatch_identity_sha256=identity.identity_sha256,
        identity_payload_sha256=identity_payload_sha256,
        identity_payload_bytes=len(identity_payload),
        caller_identity=auth_binding.caller_identity,
        audience_identity=auth_binding.audience_identity,
        target_origin=target.origin,
        target_method=target.method,
        target_path=target.path,
        record=record,
    )


def _verify_queued_and_not_terminal_under_lock(
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
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        ) from None

    try:
        if _transition_record_exists_under_lock(
            provider,
            job_id=binding.job_id,
            run_id=queued.run_id,
            revision=2,
        ):
            raise ControlledStagingDispatchIntentError(
                "staging_dispatch_intent_superseded"
            )
        if not _transition_record_exists_under_lock(
            provider,
            job_id=binding.job_id,
            run_id=queued.run_id,
            revision=1,
        ):
            raise ControlledStagingDispatchIntentError(
                "staging_dispatch_intent_queued_missing"
            )
        queued_path = transition_record_path(
            provider,
            job_id=binding.job_id,
            run_id=queued.run_id,
            revision=1,
        )
        stored = _verify_queued_transition(
            provider,
            _decode_record(
                provider._read_file_no_follow(
                    queued_path,
                    max_bytes=_MAX_STATE_RECORD_BYTES,
                    overflow_category="staging_state_corrupt",
                )
            ),
        )
    except ControlledStagingDispatchIntentError:
        raise
    except (
        ControlledStagingQueuedTransitionError,
        ControlledStagingTransitionStateError,
        MinimumStagingVerticalSliceError,
    ):
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        ) from None

    if _queued_canonical_json_bytes(stored) != _queued_canonical_json_bytes(
        queued.record
    ):
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )


def _load_and_verify_intent_under_lock(
    *,
    provider: StagingUploadProvider,
    binding,
    derived: _DispatchIntentDerived,
) -> None:
    path = _intent_path(
        provider,
        job_id=binding.job_id,
        run_id=derived.run_id,
    )
    try:
        stored = _verify_intent(
            provider,
            _decode_record(
                provider._read_file_no_follow(
                    path,
                    max_bytes=_MAX_STATE_RECORD_BYTES,
                    overflow_category="staging_state_corrupt",
                )
            ),
        )
    except ControlledStagingDispatchIntentError:
        raise
    except MinimumStagingVerticalSliceError as exc:
        if exc.category == "staging_path_invalid":
            raise ControlledStagingDispatchIntentError(
                "staging_dispatch_intent_missing"
            ) from None
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        ) from None

    if _canonical_json_bytes(stored) != _canonical_json_bytes(derived.record):
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )


def _result(
    *,
    binding,
    derived: _DispatchIntentDerived,
    persistence_state: str,
) -> ControlledStagingDispatchIntentResult:
    return ControlledStagingDispatchIntentResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        engine=derived.engine,
        run_id=derived.run_id,
        dispatch_identity_sha256=derived.dispatch_identity_sha256,
        identity_payload_sha256=derived.identity_payload_sha256,
        identity_payload_bytes=derived.identity_payload_bytes,
        state="queued",
        revision=1,
        caller_identity=derived.caller_identity,
        audience_identity=derived.audience_identity,
        target_origin=derived.target_origin,
        target_method=derived.target_method,
        target_path=derived.target_path,
        intent_sha256=sha256(_canonical_json_bytes(derived.record)).hexdigest(),
        persistence_state=persistence_state,
    )


def persist_controlled_staging_dispatch_intent(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
) -> ControlledStagingDispatchIntentResult:
    """Persist one exact non-executable dispatch intent while state stays queued."""

    checked_provider = _require_provider(provider)
    checked_endpoint = _require_endpoint(endpoint)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_input_invalid"
        ) from None

    initial, queued, derived = _derive_intent(binding, checked_endpoint)
    path = _intent_path(
        checked_provider,
        job_id=binding.job_id,
        run_id=derived.run_id,
    )
    sealed_payload = _canonical_json_bytes(
        _seal_intent(checked_provider, derived.record)
    )
    if len(sealed_payload) > _MAX_STATE_RECORD_BYTES:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_state_invalid"
        )

    try:
        with checked_provider._job_lock(binding.job_id):
            with checked_provider._verified_source_guard(
                binding
            ) as assert_source_stable:
                _verify_queued_and_not_terminal_under_lock(
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
                    _load_and_verify_intent_under_lock(
                        provider=checked_provider,
                        binding=binding,
                        derived=derived,
                    )
                    assert_source_stable()
                    persistence_state = "replay"
    except ControlledStagingDispatchIntentError:
        raise
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_dispatch_intent_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_dispatch_intent_state_invalid"
        )
        raise ControlledStagingDispatchIntentError(category) from None

    return _result(
        binding=binding,
        derived=derived,
        persistence_state=persistence_state,
    )


def recover_controlled_staging_dispatch_intent(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
) -> ControlledStagingDispatchIntentResult:
    """Read exact intent evidence only while the run remains queued revision 1."""

    checked_provider = _require_provider(provider)
    checked_endpoint = _require_endpoint(endpoint)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
    except ControlledStagingJobLifecycleError:
        raise ControlledStagingDispatchIntentError(
            "staging_dispatch_intent_input_invalid"
        ) from None

    initial, queued, derived = _derive_intent(binding, checked_endpoint)

    try:
        with checked_provider._job_lock(binding.job_id):
            with checked_provider._verified_source_guard(
                binding
            ) as assert_source_stable:
                _verify_queued_and_not_terminal_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    initial=initial,
                    queued=queued,
                )
                _load_and_verify_intent_under_lock(
                    provider=checked_provider,
                    binding=binding,
                    derived=derived,
                )
                assert_source_stable()
    except ControlledStagingDispatchIntentError:
        raise
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_dispatch_intent_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_dispatch_intent_state_invalid"
        )
        raise ControlledStagingDispatchIntentError(category) from None

    return _result(
        binding=binding,
        derived=derived,
        persistence_state="replay",
    )
