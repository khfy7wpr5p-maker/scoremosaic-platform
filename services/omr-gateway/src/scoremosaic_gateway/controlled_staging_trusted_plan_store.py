"""Immutable provider-backed trusted receiver-plan state for controlled staging.

A new plan record may be created only while the job is still at its initial
planned revision and before any controlled-staging transition exists. Once the
record exists, exact read-only replay remains valid after later transitions so a
restart can re-establish trusted receiver-plan evidence without reopening state.

The paired resolver is read-only. An untrusted ``ReceiverPlanLookupHint`` may
select only the canonical job-id record; all other hint fields remain
non-authoritative and are converged by ``trusted_receiver_plan_lookup``.

No HTTP route, credential resolution, request signing, replay reservation, job
state mutation, queue/worker runtime, network dispatch, orchestration runtime, or
engine execution is enabled here.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
from pathlib import Path
import re
from typing import Any

from .controlled_staging_job_lifecycle import (
    ControlledStagingJobLifecycleError,
    _derive_initial_evidence,
    _validated_binding,
)
from .controlled_staging_transition_state import (
    ControlledStagingTransitionStateError,
    _optional_regular_file_exists,
    any_transition_record_exists,
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
    verify_orchestration_plan,
)
from .trusted_receiver_plan_lookup import ReceiverPlanLookupHint


CONTROLLED_STAGING_TRUSTED_PLAN_STORE_VERSION = (
    "scoremosaic-controlled-staging-trusted-plan-store-v1"
)
_PLAN_MAC_FIELD = "trusted_plan_integrity_mac"
_PLAN_MAC_DOMAIN = b"scoremosaic-controlled-staging-trusted-plan-store-v1"
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_PLAN_ID_RE = re.compile(r"plan_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_KEYS = frozenset(
    {
        "version",
        "environment",
        "job_id",
        "source_artifact_id",
        "source_sha256",
        "orchestration_plan_id",
        "orchestration_plan_sha256",
        "canonical_plan_sha256",
        "plan",
    }
)


class ControlledStagingTrustedPlanStoreError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        ) from None


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_input_invalid"
        )
    return value


def _plan_path(provider: StagingUploadProvider, *, job_id: str) -> Path:
    if type(job_id) is not str or _JOB_ID_RE.fullmatch(job_id) is None:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    return provider._root / "state" / "trusted_receiver_plans" / f"{job_id}.json"


def _plan_mac(provider: StagingUploadProvider, record: dict[str, object]) -> str:
    key = getattr(provider, "_state_integrity_key", None)
    if type(key) is not bytes or len(key) != 32:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    if type(record) is not dict or _PLAN_MAC_FIELD in record:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    message = b"\0".join((_PLAN_MAC_DOMAIN, _canonical_json_bytes(record)))
    return hmac_new(key, message, sha256).hexdigest()


def _seal_record(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> dict[str, object]:
    sealed = dict(record)
    sealed[_PLAN_MAC_FIELD] = _plan_mac(provider, record)
    return sealed


def _verify_record_mac(
    provider: StagingUploadProvider,
    sealed: dict[str, object],
) -> dict[str, object]:
    if type(sealed) is not dict or _PLAN_MAC_FIELD not in sealed:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    observed = sealed.get(_PLAN_MAC_FIELD)
    if type(observed) is not str or _SHA256_RE.fullmatch(observed) is None:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    record = dict(sealed)
    del record[_PLAN_MAC_FIELD]
    if not compare_digest(observed, _plan_mac(provider, record)):
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    return record


def _validate_record_shape(record: dict[str, object]) -> dict[str, object]:
    if type(record) is not dict or frozenset(record) != _RECORD_KEYS:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    if (
        record.get("version") != CONTROLLED_STAGING_TRUSTED_PLAN_STORE_VERSION
        or record.get("environment") != "staging"
        or type(record.get("job_id")) is not str
        or _JOB_ID_RE.fullmatch(record["job_id"]) is None
        or type(record.get("source_artifact_id")) is not str
        or _ARTIFACT_ID_RE.fullmatch(record["source_artifact_id"]) is None
        or type(record.get("source_sha256")) is not str
        or _SHA256_RE.fullmatch(record["source_sha256"]) is None
        or type(record.get("orchestration_plan_id")) is not str
        or _PLAN_ID_RE.fullmatch(record["orchestration_plan_id"]) is None
        or type(record.get("orchestration_plan_sha256")) is not str
        or _SHA256_RE.fullmatch(record["orchestration_plan_sha256"]) is None
        or type(record.get("canonical_plan_sha256")) is not str
        or _SHA256_RE.fullmatch(record["canonical_plan_sha256"]) is None
        or type(record.get("plan")) is not dict
    ):
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )

    plan = record["plan"]
    try:
        verify_orchestration_plan(plan)
    except (OrchestrationContractError, TypeError, ValueError, KeyError):
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        ) from None
    canonical_plan = _canonical_json_bytes(plan)
    if (
        plan.get("jobId") != record["job_id"]
        or plan.get("planId") != record["orchestration_plan_id"]
        or plan.get("planSha256") != record["orchestration_plan_sha256"]
        or sha256(canonical_plan).hexdigest() != record["canonical_plan_sha256"]
    ):
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    return record


def _load_verified_record(
    provider: StagingUploadProvider,
    *,
    job_id: str,
) -> dict[str, object]:
    try:
        raw = provider._read_file_no_follow(
            _plan_path(provider, job_id=job_id),
            max_bytes=_MAX_STATE_RECORD_BYTES,
            overflow_category="staging_state_corrupt",
        )
        sealed = _decode_record(raw)
        record = _validate_record_shape(_verify_record_mac(provider, sealed))
        return _decode_record(_canonical_json_bytes(record))
    except ControlledStagingTrustedPlanStoreError:
        raise
    except MinimumStagingVerticalSliceError:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        ) from None


def _derive_record(binding) -> dict[str, object]:
    try:
        plan = build_orchestration_plan(
            binding.job_id,
            source_artifact_ref=binding.source_artifact_ref,
            source_sha256=binding.document_sha256,
            source_size_bytes=binding.source_size_bytes,
            source_media_type=binding.source_media_type,
            requested_engines=ENGINE_NAMES,
        )
        plan_dict = plan.as_dict()
        verify_orchestration_plan(plan_dict)
    except (OrchestrationContractError, TypeError, ValueError, KeyError):
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_contract_invalid"
        ) from None
    if (
        plan.plan_id != binding.orchestration_plan_id
        or plan.plan_sha256 != binding.orchestration_plan_sha256
        or plan.source_artifact.artifact_id != binding.source_artifact_id
        or plan.source_artifact.sha256 != binding.document_sha256
        or plan.source_artifact.artifact_ref != binding.source_artifact_ref
        or plan.source_artifact.size_bytes != binding.source_size_bytes
        or plan.source_artifact.media_type != binding.source_media_type
    ):
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_contract_invalid"
        )
    canonical_plan = _canonical_json_bytes(plan_dict)
    return _validate_record_shape(
        {
            "version": CONTROLLED_STAGING_TRUSTED_PLAN_STORE_VERSION,
            "environment": "staging",
            "job_id": binding.job_id,
            "source_artifact_id": binding.source_artifact_id,
            "source_sha256": binding.document_sha256,
            "orchestration_plan_id": plan.plan_id,
            "orchestration_plan_sha256": plan.plan_sha256,
            "canonical_plan_sha256": sha256(canonical_plan).hexdigest(),
            "plan": plan_dict,
        }
    )


@dataclass(frozen=True, slots=True)
class ControlledStagingTrustedPlanStoreResult:
    job_id: str
    source_artifact_id: str
    orchestration_plan_id: str
    orchestration_plan_sha256: str
    canonical_plan_sha256: str
    persistence_state: str

    def __post_init__(self) -> None:
        if (
            type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.source_artifact_id) is not str
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.orchestration_plan_id) is not str
            or _PLAN_ID_RE.fullmatch(self.orchestration_plan_id) is None
            or type(self.orchestration_plan_sha256) is not str
            or _SHA256_RE.fullmatch(self.orchestration_plan_sha256) is None
            or type(self.canonical_plan_sha256) is not str
            or _SHA256_RE.fullmatch(self.canonical_plan_sha256) is None
            or type(self.persistence_state) is not str
            or self.persistence_state not in {"written", "replay"}
        ):
            raise ControlledStagingTrustedPlanStoreError(
                "staging_trusted_plan_result_invalid"
            )

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    @property
    def credential_resolution_allowed(self) -> bool:
        return False

    @property
    def replay_reservation_allowed(self) -> bool:
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
    def orchestration_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_TRUSTED_PLAN_STORE_VERSION,
            "environment": "staging",
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "orchestrationPlanId": self.orchestration_plan_id,
            "orchestrationPlanSha256": self.orchestration_plan_sha256,
            "canonicalPlanSha256": self.canonical_plan_sha256,
            "persistenceState": self.persistence_state,
            "jobStateMutationAllowed": False,
            "credentialResolutionAllowed": False,
            "replayReservationAllowed": False,
            "queueRuntimeAllowed": False,
            "workerAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
            "engineExecutionAllowed": False,
        }


def persist_controlled_staging_trusted_receiver_plan(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
) -> ControlledStagingTrustedPlanStoreResult:
    """Create once before transitions; exactly replay an existing plan afterward."""

    checked_provider = _require_provider(provider)
    try:
        binding = _validated_binding(minimum_slice, checked_provider)
        initial = _derive_initial_evidence(binding)
        stored_lifecycle = checked_provider.read_job_lifecycle_record(binding=binding)
    except (ControlledStagingJobLifecycleError, MinimumStagingVerticalSliceError):
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_lifecycle_invalid"
        ) from None
    if stored_lifecycle != initial.record:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_lifecycle_invalid"
        )

    record = _derive_record(binding)
    path = _plan_path(checked_provider, job_id=binding.job_id)
    sealed_payload = _canonical_json_bytes(_seal_record(checked_provider, record))
    if len(sealed_payload) > _MAX_STATE_RECORD_BYTES:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        )
    run_ids = tuple(run.run_id for run in initial.run_evidence)

    try:
        with checked_provider._job_lock(binding.job_id):
            with checked_provider._verified_source_guard(
                binding
            ) as assert_source_stable:
                if _optional_regular_file_exists(checked_provider, path):
                    stored = _load_verified_record(
                        checked_provider,
                        job_id=binding.job_id,
                    )
                    if _canonical_json_bytes(stored) != _canonical_json_bytes(record):
                        raise ControlledStagingTrustedPlanStoreError(
                            "staging_trusted_plan_conflict"
                        )
                    assert_source_stable()
                    persistence_state = "replay"
                else:
                    if any_transition_record_exists(
                        checked_provider,
                        job_id=binding.job_id,
                        run_ids=run_ids,
                    ):
                        raise ControlledStagingTrustedPlanStoreError(
                            "staging_trusted_plan_superseded"
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
                        stored = _load_verified_record(
                            checked_provider,
                            job_id=binding.job_id,
                        )
                        if _canonical_json_bytes(stored) != _canonical_json_bytes(record):
                            raise ControlledStagingTrustedPlanStoreError(
                                "staging_trusted_plan_conflict"
                            )
                        assert_source_stable()
                        persistence_state = "replay"
    except ControlledStagingTrustedPlanStoreError:
        raise
    except ControlledStagingTransitionStateError:
        raise ControlledStagingTrustedPlanStoreError(
            "staging_trusted_plan_state_invalid"
        ) from None
    except MinimumStagingVerticalSliceError as exc:
        category = (
            "staging_trusted_plan_source_invalid"
            if exc.category == "staging_source_collision"
            else "staging_trusted_plan_state_invalid"
        )
        raise ControlledStagingTrustedPlanStoreError(category) from None

    return ControlledStagingTrustedPlanStoreResult(
        job_id=binding.job_id,
        source_artifact_id=binding.source_artifact_id,
        orchestration_plan_id=binding.orchestration_plan_id,
        orchestration_plan_sha256=binding.orchestration_plan_sha256,
        canonical_plan_sha256=record["canonical_plan_sha256"],
        persistence_state=persistence_state,
    )


class ControlledStagingTrustedReceiverPlanResolver:
    """Read-only adapter from one untrusted hint to an HMAC-verified plan record."""

    __slots__ = ("_provider",)

    def __init__(self, provider: StagingUploadProvider) -> None:
        self._provider = _require_provider(provider)

    def __repr__(self) -> str:
        return "ControlledStagingTrustedReceiverPlanResolver()"

    @property
    def persistence_allowed(self) -> bool:
        return False

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    @property
    def credential_resolution_allowed(self) -> bool:
        return False

    @property
    def replay_reservation_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def __call__(self, hint: ReceiverPlanLookupHint) -> dict[str, Any]:
        if type(hint) is not ReceiverPlanLookupHint:
            raise ControlledStagingTrustedPlanStoreError(
                "staging_trusted_plan_lookup_unavailable"
            )
        try:
            record = _load_verified_record(self._provider, job_id=hint.job_id)
            plan = record["plan"]
            if type(plan) is not dict:
                raise ControlledStagingTrustedPlanStoreError(
                    "staging_trusted_plan_lookup_unavailable"
                )
            return _decode_record(_canonical_json_bytes(plan))
        except Exception:
            raise ControlledStagingTrustedPlanStoreError(
                "staging_trusted_plan_lookup_unavailable"
            ) from None
