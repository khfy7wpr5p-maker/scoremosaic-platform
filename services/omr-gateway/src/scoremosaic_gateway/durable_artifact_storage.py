"""Gate D.3 immutable artifact storage authority contract foundation.

This module selects no storage provider and performs no read, write, delete,
network, queue, or persistence operation. It derives immutable storage keys
from the existing candidate/artifact lifecycle and records only bounded content
identity metadata for already-sealed artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .artifact_lifecycle import (
    OUTPUT_ARTIFACT_KINDS,
    ArtifactRecord,
    CandidateArtifactLifecycle,
    CandidateRecord,
)
from .orchestration import ENGINE_NAMES


DURABLE_ARTIFACT_STORAGE_CONTRACT_VERSION = "0.1-foundation"

_JOB_ID_PATTERN = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_LIFECYCLE_ID_PATTERN = re.compile(r"^lifecycle_[a-f0-9]{24}$")
_ARTIFACT_ID_PATTERN = re.compile(r"^artifact_[a-f0-9]{24}$")
_CANDIDATE_ID_PATTERN = re.compile(r"^candidate_[a-f0-9]{24}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_SAFE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")
_STORAGE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")
_MAX_ARTIFACT_BYTES = 200 * 1024 * 1024
_MAX_RECORDS = 16
_MAX_MEDIA_TYPE_LENGTH = 127

_POLICIES = {
    "serverDerivedKeys": True,
    "immutableObjects": True,
    "overwriteAllowed": False,
    "exactReplayAllowed": True,
    "crossCandidateWriteAllowed": False,
    "crossEngineWriteAllowed": False,
    "hashRequired": True,
}
_BOUNDARIES = {
    "providerSelected": False,
    "persistenceEnabled": False,
    "storageWritesEnabled": False,
    "queueEnabled": False,
    "networkDispatchEnabled": False,
    "orchestrationEnabled": False,
    "uploadEnabled": False,
    "teacherApproval": False,
    "publication": False,
}


class DurableArtifactStorageError(ValueError):
    """Fail-closed D.3 contract error with one bounded stable category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require_exact_str(value: object, pattern: re.Pattern[str], category: str) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        raise DurableArtifactStorageError(category)
    return value


def _require_optional_exact_str(
    value: object,
    pattern: re.Pattern[str],
    category: str,
) -> str | None:
    if value is None:
        return None
    return _require_exact_str(value, pattern, category)


def _require_safe_ref(value: object) -> str:
    checked = _require_exact_str(value, _SAFE_REF_PATTERN, "binding_invalid")
    if checked.startswith("/") or "\\" in checked or "//" in checked:
        raise DurableArtifactStorageError("binding_invalid")
    if any(part in {"", ".", ".."} for part in checked.split("/")):
        raise DurableArtifactStorageError("binding_invalid")
    return checked


def _require_storage_key(value: object) -> str:
    checked = _require_exact_str(value, _STORAGE_KEY_PATTERN, "binding_invalid")
    if checked.startswith("/") or "\\" in checked or "//" in checked:
        raise DurableArtifactStorageError("binding_invalid")
    if any(part in {"", ".", ".."} for part in checked.split("/")):
        raise DurableArtifactStorageError("binding_invalid")
    return checked


def _require_size(value: object) -> int:
    if isinstance(value, bool) or type(value) is not int:
        raise DurableArtifactStorageError("binding_invalid")
    if not 1 <= value <= _MAX_ARTIFACT_BYTES:
        raise DurableArtifactStorageError("binding_invalid")
    return value


def _require_media_type(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= _MAX_MEDIA_TYPE_LENGTH:
        raise DurableArtifactStorageError("binding_invalid")
    if any(ord(char) < 0x21 or ord(char) > 0x7E for char in value):
        raise DurableArtifactStorageError("binding_invalid")
    return value


@dataclass(frozen=True, slots=True)
class ArtifactStorageBinding:
    storage_key: str
    artifact_id: str
    artifact_ref: str
    kind: str
    candidate_id: str | None
    engine: str | None
    sha256: str
    size_bytes: int
    media_type: str

    def __post_init__(self) -> None:
        _require_storage_key(self.storage_key)
        _require_exact_str(self.artifact_id, _ARTIFACT_ID_PATTERN, "binding_invalid")
        _require_safe_ref(self.artifact_ref)
        if type(self.kind) is not str or self.kind not in {"source", *OUTPUT_ARTIFACT_KINDS}:
            raise DurableArtifactStorageError("binding_invalid")
        _require_exact_str(self.sha256, _SHA256_PATTERN, "binding_invalid")
        _require_size(self.size_bytes)
        _require_media_type(self.media_type)

        if self.kind == "source":
            if self.candidate_id is not None or self.engine is not None:
                raise DurableArtifactStorageError("binding_invalid")
        else:
            _require_optional_exact_str(
                self.candidate_id,
                _CANDIDATE_ID_PATTERN,
                "binding_invalid",
            )
            if self.candidate_id is None:
                raise DurableArtifactStorageError("binding_invalid")
            if type(self.engine) is not str or self.engine not in ENGINE_NAMES:
                raise DurableArtifactStorageError("binding_invalid")

    def _core(self) -> dict[str, Any]:
        return {
            "storageKey": self.storage_key,
            "artifactId": self.artifact_id,
            "artifactRef": self.artifact_ref,
            "kind": self.kind,
            "candidateId": self.candidate_id,
            "engine": self.engine,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "mediaType": self.media_type,
        }

    @property
    def binding_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self._core())).hexdigest()

    def as_safe_dict(self) -> dict[str, Any]:
        payload = self._core()
        payload.update(
            {
                "bindingSha256": self.binding_sha256,
                "immutable": True,
                "overwriteAllowed": False,
            }
        )
        return payload


@dataclass(frozen=True, slots=True)
class DurableArtifactStorageManifest:
    version: str
    lifecycle_id: str
    job_id: str
    records: tuple[ArtifactStorageBinding, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != DURABLE_ARTIFACT_STORAGE_CONTRACT_VERSION:
            raise DurableArtifactStorageError("manifest_invalid")
        _require_exact_str(self.lifecycle_id, _LIFECYCLE_ID_PATTERN, "manifest_invalid")
        _require_exact_str(self.job_id, _JOB_ID_PATTERN, "manifest_invalid")
        if type(self.records) is not tuple or not 1 <= len(self.records) <= _MAX_RECORDS:
            raise DurableArtifactStorageError("manifest_invalid")
        if any(type(record) is not ArtifactStorageBinding for record in self.records):
            raise DurableArtifactStorageError("manifest_invalid")
        if len({record.storage_key for record in self.records}) != len(self.records):
            raise DurableArtifactStorageError("manifest_invalid")
        if len({record.artifact_id for record in self.records}) != len(self.records):
            raise DurableArtifactStorageError("manifest_invalid")
        sources = [record for record in self.records if record.kind == "source"]
        if len(sources) != 1:
            raise DurableArtifactStorageError("manifest_invalid")

    def _core(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "lifecycleId": self.lifecycle_id,
            "jobId": self.job_id,
            "records": [record.as_safe_dict() for record in self.records],
            "policies": dict(_POLICIES),
            "boundaries": dict(_BOUNDARIES),
        }

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self._core())).hexdigest()

    def as_safe_dict(self) -> dict[str, Any]:
        payload = self._core()
        payload["manifestSha256"] = self.manifest_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ArtifactStorageBindResult:
    manifest: DurableArtifactStorageManifest
    replayed: bool

    def __post_init__(self) -> None:
        if type(self.manifest) is not DurableArtifactStorageManifest:
            raise DurableArtifactStorageError("result_invalid")
        if type(self.replayed) is not bool:
            raise DurableArtifactStorageError("result_invalid")


def _require_lifecycle(value: object) -> CandidateArtifactLifecycle:
    if type(value) is not CandidateArtifactLifecycle:
        raise DurableArtifactStorageError("lifecycle_invalid")
    return value


def _expected_storage_key(
    lifecycle: CandidateArtifactLifecycle,
    artifact: ArtifactRecord,
    candidate: CandidateRecord | None,
) -> str:
    if candidate is None:
        return (
            f"immutable/jobs/{lifecycle.job_id}/source/"
            f"{artifact.artifact_id}"
        )
    return (
        f"immutable/jobs/{lifecycle.job_id}/candidates/"
        f"{candidate.candidate_id}/{artifact.artifact_id}"
    )


def _find_artifact(
    lifecycle: CandidateArtifactLifecycle,
    artifact_id: str,
) -> tuple[ArtifactRecord, CandidateRecord | None]:
    if lifecycle.source_artifact.artifact_id == artifact_id:
        return lifecycle.source_artifact, None
    for candidate in lifecycle.candidates:
        for artifact in candidate.artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact, candidate
    raise DurableArtifactStorageError("artifact_unknown")


def _binding_from_artifact(
    lifecycle: CandidateArtifactLifecycle,
    artifact: ArtifactRecord,
    candidate: CandidateRecord | None,
) -> ArtifactStorageBinding:
    if artifact.state != "sealed":
        raise DurableArtifactStorageError("artifact_not_sealed")
    if (
        type(artifact.sha256) is not str
        or type(artifact.size_bytes) is not int
        or isinstance(artifact.size_bytes, bool)
        or type(artifact.media_type) is not str
    ):
        raise DurableArtifactStorageError("artifact_not_sealed")
    return ArtifactStorageBinding(
        storage_key=_expected_storage_key(lifecycle, artifact, candidate),
        artifact_id=artifact.artifact_id,
        artifact_ref=artifact.artifact_ref,
        kind=artifact.kind,
        candidate_id=None if candidate is None else candidate.candidate_id,
        engine=None if candidate is None else candidate.engine,
        sha256=artifact.sha256,
        size_bytes=artifact.size_bytes,
        media_type=artifact.media_type,
    )


def _canonical_artifact_order(
    lifecycle: CandidateArtifactLifecycle,
) -> dict[str, int]:
    artifact_ids = [lifecycle.source_artifact.artifact_id]
    artifact_ids.extend(
        artifact.artifact_id
        for candidate in lifecycle.candidates
        for artifact in candidate.artifacts
    )
    return {artifact_id: index for index, artifact_id in enumerate(artifact_ids)}


def build_durable_artifact_storage_manifest(
    lifecycle: CandidateArtifactLifecycle,
) -> DurableArtifactStorageManifest:
    """Create source-only immutable storage authority without touching storage."""

    checked = _require_lifecycle(lifecycle)
    source_binding = _binding_from_artifact(
        checked,
        checked.source_artifact,
        None,
    )
    manifest = DurableArtifactStorageManifest(
        version=DURABLE_ARTIFACT_STORAGE_CONTRACT_VERSION,
        lifecycle_id=checked.lifecycle_id,
        job_id=checked.job_id,
        records=(source_binding,),
    )
    verify_durable_artifact_storage_manifest(manifest, checked)
    return manifest


def verify_durable_artifact_storage_manifest(
    manifest: DurableArtifactStorageManifest,
    lifecycle: CandidateArtifactLifecycle,
) -> None:
    """Verify restored bounded storage authority against the exact lifecycle."""

    if type(manifest) is not DurableArtifactStorageManifest:
        raise DurableArtifactStorageError("manifest_invalid")
    checked = _require_lifecycle(lifecycle)
    if manifest.lifecycle_id != checked.lifecycle_id or manifest.job_id != checked.job_id:
        raise DurableArtifactStorageError("identity_mismatch")

    order = _canonical_artifact_order(checked)
    record_order: list[int] = []
    source_seen = False
    for record in manifest.records:
        try:
            artifact, candidate = _find_artifact(checked, record.artifact_id)
        except DurableArtifactStorageError as exc:
            if exc.category == "artifact_unknown":
                raise DurableArtifactStorageError("identity_mismatch") from None
            raise

        if artifact.state != "sealed":
            raise DurableArtifactStorageError("identity_mismatch")
        expected = _binding_from_artifact(checked, artifact, candidate)

        if record.storage_key != expected.storage_key:
            raise DurableArtifactStorageError("storage_key_mismatch")
        if (
            record.artifact_id != expected.artifact_id
            or record.artifact_ref != expected.artifact_ref
            or record.kind != expected.kind
            or record.candidate_id != expected.candidate_id
            or record.engine != expected.engine
        ):
            raise DurableArtifactStorageError("identity_mismatch")
        if (
            record.sha256 != expected.sha256
            or record.size_bytes != expected.size_bytes
            or record.media_type != expected.media_type
        ):
            raise DurableArtifactStorageError("storage_conflict")

        if record.kind == "source":
            if source_seen:
                raise DurableArtifactStorageError("manifest_invalid")
            source_seen = True
        record_order.append(order[record.artifact_id])

    if not source_seen or manifest.records[0].kind != "source":
        raise DurableArtifactStorageError("manifest_invalid")
    if record_order != sorted(record_order):
        raise DurableArtifactStorageError("manifest_invalid")


def bind_sealed_artifact_idempotently(
    manifest: DurableArtifactStorageManifest,
    lifecycle: CandidateArtifactLifecycle,
    artifact_id: str,
) -> ArtifactStorageBindResult:
    """Record immutable authority for one sealed artifact; never write bytes."""

    if type(artifact_id) is not str or not _ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
        raise DurableArtifactStorageError("artifact_id_invalid")
    checked = _require_lifecycle(lifecycle)
    verify_durable_artifact_storage_manifest(manifest, checked)

    artifact, candidate = _find_artifact(checked, artifact_id)
    target = _binding_from_artifact(checked, artifact, candidate)

    for record in manifest.records:
        if record.artifact_id == target.artifact_id or record.storage_key == target.storage_key:
            if record == target:
                return ArtifactStorageBindResult(manifest=manifest, replayed=True)
            if record.storage_key == target.storage_key:
                raise DurableArtifactStorageError("storage_conflict")
            raise DurableArtifactStorageError("identity_mismatch")

    order = _canonical_artifact_order(checked)
    records = tuple(
        sorted(
            manifest.records + (target,),
            key=lambda item: order[item.artifact_id],
        )
    )
    updated = DurableArtifactStorageManifest(
        version=manifest.version,
        lifecycle_id=manifest.lifecycle_id,
        job_id=manifest.job_id,
        records=records,
    )
    verify_durable_artifact_storage_manifest(updated, checked)
    return ArtifactStorageBindResult(manifest=updated, replayed=False)
