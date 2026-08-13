"""Gate E.4C immutable source/job binding foundation.

This module consumes only exact Gate E.4B Safe Intake finalization evidence. It
creates no storage write and accepts no raw document bytes. Instead it derives one
server-owned deterministic job identity and source reference, then reuses the
existing orchestration, candidate/artifact lifecycle, and Gate D.3 immutable
storage-authority contracts to prove that the exact accepted source hash/size/media
identity maps to one immutable source artifact and storage key.

No HTTP route, provider, database, object-store write, queue, engine execution,
network dispatch, or orchestration runtime is activated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .artifact_lifecycle import ArtifactLifecycleError, build_artifact_lifecycle
from .durable_artifact_storage import (
    DurableArtifactStorageError,
    build_durable_artifact_storage_manifest,
)
from .external_auth import ALLOWED_ENVIRONMENTS
from .orchestration import (
    ENGINE_NAMES,
    MAX_SOURCE_BYTES,
    OrchestrationContractError,
    build_orchestration_plan,
)
from .safe_intake import SAFE_INTAKE_MEDIA_TYPES, SAFE_INTAKE_POLICY_VERSION
from .safe_upload_finalization import (
    SafeUploadFinalizationDecision,
    SafeUploadFinalizationError,
    verify_safe_upload_finalization_decision,
)
from .safe_upload_session import SAFE_UPLOAD_SESSION_OPERATION_ID


SAFE_SOURCE_JOB_BINDING_CONTRACT_VERSION = "scoremosaic-safe-source-job-binding-v1"

_PRINCIPAL_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SESSION_ID_RE = re.compile(r"upload_[0-9a-f]{40}\Z")
_FINALIZATION_ID_RE = re.compile(r"final_[0-9a-f]{40}\Z")
_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_PLAN_ID_RE = re.compile(r"plan_[0-9a-f]{24}\Z")
_LIFECYCLE_ID_RE = re.compile(r"lifecycle_[0-9a-f]{24}\Z")
_DECISION_CONSTRUCTION_SEAL = object()


class SafeSourceJobBindingError(ValueError):
    """Stable fail-closed E.4C failure category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _is_exact_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _finalization_snapshot(value: SafeUploadFinalizationDecision) -> tuple[object, ...]:
    return (
        value.version,
        value.environment,
        value.principal_id,
        value.operation_id,
        value.session_id,
        value.admission_binding_id,
        value.state,
        value.replayed,
        value.finalization_id,
        value.document_sha256,
        value.intake_policy_version,
        value.observed_bytes,
        value.format_id,
        value.media_type,
        value.page_count,
        value.image_width,
        value.image_height,
        value.image_pixel_count,
        value.finalized_at_epoch_s,
    )


def _derive_job_id(finalization: SafeUploadFinalizationDecision) -> str:
    digest = sha256(
        b"\0".join(
            (
                SAFE_SOURCE_JOB_BINDING_CONTRACT_VERSION.encode("ascii"),
                finalization.environment.encode("ascii"),
                finalization.principal_id.encode("ascii"),
                finalization.operation_id.encode("ascii"),
                finalization.session_id.encode("ascii"),
                finalization.finalization_id.encode("ascii"),
                finalization.document_sha256.encode("ascii"),
            )
        )
    ).hexdigest()
    return "job_" + digest[:32]


@dataclass(frozen=True, slots=True, repr=False, init=False)
class SafeSourceJobBindingDecision:
    """Bounded E.4C evidence; it is not a storage write or execution capability."""

    version: str
    environment: str
    principal_id: str
    operation_id: str
    session_id: str
    finalization_id: str
    document_sha256: str
    intake_policy_version: str
    format_id: str
    source_size_bytes: int
    source_media_type: str
    job_id: str
    source_artifact_id: str
    source_artifact_ref: str
    source_storage_key: str
    source_binding_sha256: str
    orchestration_plan_id: str
    orchestration_plan_sha256: str
    lifecycle_id: str
    lifecycle_sha256: str
    storage_manifest_sha256: str

    def __init__(
        self,
        *,
        version: str,
        environment: str,
        principal_id: str,
        operation_id: str,
        session_id: str,
        finalization_id: str,
        document_sha256: str,
        intake_policy_version: str,
        format_id: str,
        source_size_bytes: int,
        source_media_type: str,
        job_id: str,
        source_artifact_id: str,
        source_artifact_ref: str,
        source_storage_key: str,
        source_binding_sha256: str,
        orchestration_plan_id: str,
        orchestration_plan_sha256: str,
        lifecycle_id: str,
        lifecycle_sha256: str,
        storage_manifest_sha256: str,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _DECISION_CONSTRUCTION_SEAL:
            raise SafeSourceJobBindingError("source_binding_construction_forbidden")
        for field, value in (
            ("version", version),
            ("environment", environment),
            ("principal_id", principal_id),
            ("operation_id", operation_id),
            ("session_id", session_id),
            ("finalization_id", finalization_id),
            ("document_sha256", document_sha256),
            ("intake_policy_version", intake_policy_version),
            ("format_id", format_id),
            ("source_size_bytes", source_size_bytes),
            ("source_media_type", source_media_type),
            ("job_id", job_id),
            ("source_artifact_id", source_artifact_id),
            ("source_artifact_ref", source_artifact_ref),
            ("source_storage_key", source_storage_key),
            ("source_binding_sha256", source_binding_sha256),
            ("orchestration_plan_id", orchestration_plan_id),
            ("orchestration_plan_sha256", orchestration_plan_sha256),
            ("lifecycle_id", lifecycle_id),
            ("lifecycle_sha256", lifecycle_sha256),
            ("storage_manifest_sha256", storage_manifest_sha256),
        ):
            object.__setattr__(self, field, value)
        self.__post_init__()

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != SAFE_SOURCE_JOB_BINDING_CONTRACT_VERSION:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.environment) is not str or self.environment not in ALLOWED_ENVIRONMENTS:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.principal_id) is not str or _PRINCIPAL_ID_RE.fullmatch(self.principal_id) is None:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.operation_id) is not str or self.operation_id != SAFE_UPLOAD_SESSION_OPERATION_ID:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.session_id) is not str or _SESSION_ID_RE.fullmatch(self.session_id) is None:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.finalization_id) is not str or _FINALIZATION_ID_RE.fullmatch(self.finalization_id) is None:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if not _is_exact_sha256(self.document_sha256):
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.intake_policy_version) is not str or self.intake_policy_version != SAFE_INTAKE_POLICY_VERSION:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.format_id) is not str or self.format_id not in {"pdf", "jpeg", "png"}:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.source_size_bytes) is not int or not 1 <= self.source_size_bytes <= MAX_SOURCE_BYTES:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.source_media_type) is not str or self.source_media_type not in SAFE_INTAKE_MEDIA_TYPES:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.job_id) is not str or _JOB_ID_RE.fullmatch(self.job_id) is None:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.source_artifact_id) is not str or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if self.source_artifact_ref != f"sources/{self.job_id}/original":
            raise SafeSourceJobBindingError("source_binding_invalid")
        if self.source_storage_key != f"immutable/jobs/{self.job_id}/source/{self.source_artifact_id}":
            raise SafeSourceJobBindingError("source_binding_invalid")
        if not _is_exact_sha256(self.source_binding_sha256):
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.orchestration_plan_id) is not str or _PLAN_ID_RE.fullmatch(self.orchestration_plan_id) is None:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if not _is_exact_sha256(self.orchestration_plan_sha256):
            raise SafeSourceJobBindingError("source_binding_invalid")
        if type(self.lifecycle_id) is not str or _LIFECYCLE_ID_RE.fullmatch(self.lifecycle_id) is None:
            raise SafeSourceJobBindingError("source_binding_invalid")
        if not _is_exact_sha256(self.lifecycle_sha256) or not _is_exact_sha256(self.storage_manifest_sha256):
            raise SafeSourceJobBindingError("source_binding_invalid")

    def __repr__(self) -> str:
        return (
            "SafeSourceJobBindingDecision("
            f"version={self.version!r}, environment={self.environment!r}, "
            f"principal_id={self.principal_id!r}, operation_id={self.operation_id!r}, "
            f"job_id={self.job_id!r}, source_artifact_id={self.source_artifact_id!r})"
        )

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "environment": self.environment,
            "principalId": self.principal_id,
            "operationId": self.operation_id,
            "sessionId": self.session_id,
            "finalizationId": self.finalization_id,
            "documentSha256": self.document_sha256,
            "safeIntakePolicyVersion": self.intake_policy_version,
            "formatId": self.format_id,
            "sourceSizeBytes": self.source_size_bytes,
            "sourceMediaType": self.source_media_type,
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "sourceArtifactRef": self.source_artifact_ref,
            "sourceStorageKey": self.source_storage_key,
            "sourceBindingSha256": self.source_binding_sha256,
            "orchestrationPlanId": self.orchestration_plan_id,
            "orchestrationPlanSha256": self.orchestration_plan_sha256,
            "lifecycleId": self.lifecycle_id,
            "lifecycleSha256": self.lifecycle_sha256,
            "storageManifestSha256": self.storage_manifest_sha256,
            "immutableSourceBound": True,
            "uploadAllowed": False,
            "storageWriteAllowed": False,
            "persistenceEnabled": False,
            "jobExecutionAllowed": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


def bind_finalized_source_to_job(
    finalization: SafeUploadFinalizationDecision,
) -> SafeSourceJobBindingDecision:
    """Bind exact E.4B evidence to existing immutable job/source contracts only."""

    if type(finalization) is not SafeUploadFinalizationDecision:
        raise SafeSourceJobBindingError("source_finalization_invalid")
    try:
        verify_safe_upload_finalization_decision(finalization)
    except SafeUploadFinalizationError:
        raise SafeSourceJobBindingError("source_finalization_invalid") from None

    initial = _finalization_snapshot(finalization)
    job_id = _derive_job_id(finalization)
    source_ref = f"sources/{job_id}/original"

    try:
        plan = build_orchestration_plan(
            job_id,
            source_artifact_ref=source_ref,
            source_sha256=finalization.document_sha256,
            source_size_bytes=finalization.observed_bytes,
            source_media_type=finalization.media_type,
            requested_engines=ENGINE_NAMES,
        )
        lifecycle = build_artifact_lifecycle(plan.as_dict())
        manifest = build_durable_artifact_storage_manifest(lifecycle)
    except (OrchestrationContractError, ArtifactLifecycleError, DurableArtifactStorageError):
        raise SafeSourceJobBindingError("source_binding_invalid") from None

    if _finalization_snapshot(finalization) != initial:
        raise SafeSourceJobBindingError("source_finalization_mutated")
    if len(manifest.records) != 1 or manifest.records[0].kind != "source":
        raise SafeSourceJobBindingError("source_binding_invalid")

    source = manifest.records[0]
    if (
        source.sha256 != finalization.document_sha256
        or source.size_bytes != finalization.observed_bytes
        or source.media_type != finalization.media_type
        or source.candidate_id is not None
        or source.engine is not None
    ):
        raise SafeSourceJobBindingError("source_binding_invalid")

    decision = SafeSourceJobBindingDecision(
        version=SAFE_SOURCE_JOB_BINDING_CONTRACT_VERSION,
        environment=finalization.environment,
        principal_id=finalization.principal_id,
        operation_id=finalization.operation_id,
        session_id=finalization.session_id,
        finalization_id=finalization.finalization_id,
        document_sha256=finalization.document_sha256,
        intake_policy_version=finalization.intake_policy_version,
        format_id=finalization.format_id,
        source_size_bytes=finalization.observed_bytes,
        source_media_type=finalization.media_type,
        job_id=job_id,
        source_artifact_id=source.artifact_id,
        source_artifact_ref=source.artifact_ref,
        source_storage_key=source.storage_key,
        source_binding_sha256=source.binding_sha256,
        orchestration_plan_id=plan.plan_id,
        orchestration_plan_sha256=plan.plan_sha256,
        lifecycle_id=lifecycle.lifecycle_id,
        lifecycle_sha256=lifecycle.lifecycle_sha256,
        storage_manifest_sha256=manifest.manifest_sha256,
        _construction_seal=_DECISION_CONSTRUCTION_SEAL,
    )
    return decision
