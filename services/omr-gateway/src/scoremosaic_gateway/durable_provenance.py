"""Gate D.4 durable provenance record/hash-chain contract foundation.

This module performs no persistence, storage, queue, network, orchestration,
upload, approval, or publication operation. It binds the already-validated D.1
job/run state snapshot to the already-validated D.3 immutable artifact-storage
manifest and returns bounded immutable provenance evidence only.

The hash chain is deterministic tamper-evidence inside this contract; it is not
a signature, external anchor, or authorization mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .durable_artifact_storage import DurableArtifactStorageManifest
from .durable_job_state import (
    JOB_RUN_STATES,
    DurableJobStateError,
    DurableJobStateSnapshot,
    validate_durable_job_state_transition,
)
from .orchestration import ENGINE_NAMES


DURABLE_PROVENANCE_CONTRACT_VERSION = "0.1-foundation"

_JOB_ID_PATTERN = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_PLAN_ID_PATTERN = re.compile(r"^plan_[a-f0-9]{24}$")
_RUN_ID_PATTERN = re.compile(r"^run_[a-f0-9]{24}$")
_LIFECYCLE_ID_PATTERN = re.compile(r"^lifecycle_[a-f0-9]{24}$")
_ARTIFACT_ID_PATTERN = re.compile(r"^artifact_[a-f0-9]{24}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_MAX_RECORDS = 32
_MAX_STATE_REVISION = 4

_POLICIES = {
    "appendOnly": True,
    "hashChained": True,
    "exactReplayAllowed": True,
    "identityConvergenceRequired": True,
    "storageHistoryMonotonic": True,
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


class DurableProvenanceError(ValueError):
    """Fail-closed D.4 contract error with one bounded stable category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _require_exact_str(
    value: object,
    pattern: re.Pattern[str],
    category: str,
) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise DurableProvenanceError(category)
    return value


def _require_sequence(value: object) -> int:
    if type(value) is not int or not 0 <= value < _MAX_RECORDS:
        raise DurableProvenanceError("record_invalid")
    return value


def _require_state_revision(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_STATE_REVISION:
        raise DurableProvenanceError("record_invalid")
    return value


def _require_snapshot(value: object) -> DurableJobStateSnapshot:
    if type(value) is not DurableJobStateSnapshot:
        raise DurableProvenanceError("snapshot_invalid")
    return value


def _require_manifest(value: object) -> DurableArtifactStorageManifest:
    if type(value) is not DurableArtifactStorageManifest:
        raise DurableProvenanceError("manifest_invalid")
    return value


def _require_identity_convergence(
    snapshot: DurableJobStateSnapshot,
    manifest: DurableArtifactStorageManifest,
) -> None:
    if manifest.job_id != snapshot.job_id:
        raise DurableProvenanceError("identity_mismatch")
    source = manifest.records[0]
    if (
        source.kind != "source"
        or source.artifact_id != snapshot.source_artifact_id
        or source.sha256 != snapshot.source_sha256
    ):
        raise DurableProvenanceError("identity_mismatch")


@dataclass(frozen=True, slots=True)
class DurableProvenanceRecord:
    version: str
    sequence: int
    previous_record_sha256: str | None
    dispatch_identity_sha256: str
    plan_id: str
    plan_sha256: str
    job_id: str
    source_artifact_id: str
    source_sha256: str
    run_id: str
    engine: str
    state: str
    state_revision: int
    lifecycle_id: str
    storage_manifest_sha256: str
    storage_binding_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != DURABLE_PROVENANCE_CONTRACT_VERSION
        ):
            raise DurableProvenanceError("record_invalid")
        sequence = _require_sequence(self.sequence)
        if sequence == 0:
            if self.previous_record_sha256 is not None:
                raise DurableProvenanceError("record_invalid")
        else:
            _require_exact_str(
                self.previous_record_sha256,
                _SHA256_PATTERN,
                "record_invalid",
            )
        _require_exact_str(
            self.dispatch_identity_sha256,
            _SHA256_PATTERN,
            "record_invalid",
        )
        _require_exact_str(self.plan_id, _PLAN_ID_PATTERN, "record_invalid")
        _require_exact_str(self.plan_sha256, _SHA256_PATTERN, "record_invalid")
        _require_exact_str(self.job_id, _JOB_ID_PATTERN, "record_invalid")
        _require_exact_str(
            self.source_artifact_id,
            _ARTIFACT_ID_PATTERN,
            "record_invalid",
        )
        _require_exact_str(self.source_sha256, _SHA256_PATTERN, "record_invalid")
        _require_exact_str(self.run_id, _RUN_ID_PATTERN, "record_invalid")
        if type(self.engine) is not str or self.engine not in ENGINE_NAMES:
            raise DurableProvenanceError("record_invalid")
        if type(self.state) is not str or self.state not in JOB_RUN_STATES:
            raise DurableProvenanceError("record_invalid")
        _require_state_revision(self.state_revision)
        _require_exact_str(
            self.lifecycle_id,
            _LIFECYCLE_ID_PATTERN,
            "record_invalid",
        )
        _require_exact_str(
            self.storage_manifest_sha256,
            _SHA256_PATTERN,
            "record_invalid",
        )
        if (
            type(self.storage_binding_sha256s) is not tuple
            or not 1 <= len(self.storage_binding_sha256s) <= 16
        ):
            raise DurableProvenanceError("record_invalid")
        if len(set(self.storage_binding_sha256s)) != len(
            self.storage_binding_sha256s
        ):
            raise DurableProvenanceError("record_invalid")
        for binding_sha256 in self.storage_binding_sha256s:
            _require_exact_str(
                binding_sha256,
                _SHA256_PATTERN,
                "record_invalid",
            )

    def _core(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "sequence": self.sequence,
            "previousRecordSha256": self.previous_record_sha256,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "runId": self.run_id,
            "engine": self.engine,
            "state": self.state,
            "stateRevision": self.state_revision,
            "lifecycleId": self.lifecycle_id,
            "storageManifestSha256": self.storage_manifest_sha256,
            "storageBindingSha256s": list(self.storage_binding_sha256s),
        }

    @property
    def record_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self._core())).hexdigest()

    def as_safe_dict(self) -> dict[str, Any]:
        payload = self._core()
        payload["recordSha256"] = self.record_sha256
        return payload


def _same_run_identity(
    left: DurableProvenanceRecord,
    right: DurableProvenanceRecord,
) -> bool:
    return (
        left.dispatch_identity_sha256 == right.dispatch_identity_sha256
        and left.plan_id == right.plan_id
        and left.plan_sha256 == right.plan_sha256
        and left.job_id == right.job_id
        and left.source_artifact_id == right.source_artifact_id
        and left.source_sha256 == right.source_sha256
        and left.run_id == right.run_id
        and left.engine == right.engine
        and left.lifecycle_id == right.lifecycle_id
    )


def _validate_record_history(
    previous: DurableProvenanceRecord,
    current: DurableProvenanceRecord,
) -> None:
    if not _same_run_identity(previous, current):
        raise DurableProvenanceError("chain_invalid")
    if current.sequence != previous.sequence + 1:
        raise DurableProvenanceError("chain_invalid")
    if current.previous_record_sha256 != previous.record_sha256:
        raise DurableProvenanceError("chain_invalid")

    previous_bindings = set(previous.storage_binding_sha256s)
    current_bindings = set(current.storage_binding_sha256s)
    if not previous_bindings.issubset(current_bindings):
        raise DurableProvenanceError("chain_invalid")

    if current.state_revision == previous.state_revision:
        if current.state != previous.state:
            raise DurableProvenanceError("chain_invalid")
        if current.storage_manifest_sha256 == previous.storage_manifest_sha256:
            raise DurableProvenanceError("chain_invalid")
        if len(current_bindings) <= len(previous_bindings):
            raise DurableProvenanceError("chain_invalid")
        return

    if current.state_revision != previous.state_revision + 1:
        raise DurableProvenanceError("chain_invalid")
    try:
        validate_durable_job_state_transition(
            previous.state,
            previous.state_revision,
            current.state,
        )
    except DurableJobStateError:
        raise DurableProvenanceError("chain_invalid") from None


@dataclass(frozen=True, slots=True)
class DurableProvenanceChain:
    version: str
    records: tuple[DurableProvenanceRecord, ...]

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != DURABLE_PROVENANCE_CONTRACT_VERSION
        ):
            raise DurableProvenanceError("chain_invalid")
        if type(self.records) is not tuple or not 1 <= len(self.records) <= _MAX_RECORDS:
            raise DurableProvenanceError("chain_invalid")
        if any(type(record) is not DurableProvenanceRecord for record in self.records):
            raise DurableProvenanceError("chain_invalid")

        first = self.records[0]
        if (
            first.sequence != 0
            or first.previous_record_sha256 is not None
            or first.state != "planned"
            or first.state_revision != 0
        ):
            raise DurableProvenanceError("chain_invalid")
        for previous, current in zip(self.records, self.records[1:]):
            _validate_record_history(previous, current)

    @property
    def chain_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json(
                {
                    "version": self.version,
                    "recordSha256s": [
                        record.record_sha256 for record in self.records
                    ],
                }
            )
        ).hexdigest()

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "records": [record.as_safe_dict() for record in self.records],
            "chainSha256": self.chain_sha256,
            "policies": dict(_POLICIES),
            "boundaries": dict(_BOUNDARIES),
        }


@dataclass(frozen=True, slots=True)
class DurableProvenanceAppendResult:
    chain: DurableProvenanceChain
    replayed: bool

    def __post_init__(self) -> None:
        if type(self.chain) is not DurableProvenanceChain:
            raise DurableProvenanceError("result_invalid")
        if type(self.replayed) is not bool:
            raise DurableProvenanceError("result_invalid")


def _record_from_evidence(
    snapshot: DurableJobStateSnapshot,
    manifest: DurableArtifactStorageManifest,
    *,
    sequence: int,
    previous_record_sha256: str | None,
) -> DurableProvenanceRecord:
    return DurableProvenanceRecord(
        version=DURABLE_PROVENANCE_CONTRACT_VERSION,
        sequence=sequence,
        previous_record_sha256=previous_record_sha256,
        dispatch_identity_sha256=snapshot.dispatch_identity_sha256,
        plan_id=snapshot.plan_id,
        plan_sha256=snapshot.plan_sha256,
        job_id=snapshot.job_id,
        source_artifact_id=snapshot.source_artifact_id,
        source_sha256=snapshot.source_sha256,
        run_id=snapshot.run_id,
        engine=snapshot.engine,
        state=snapshot.state,
        state_revision=snapshot.revision,
        lifecycle_id=manifest.lifecycle_id,
        storage_manifest_sha256=manifest.manifest_sha256,
        storage_binding_sha256s=tuple(
            record.binding_sha256 for record in manifest.records
        ),
    )


def _record_matches_evidence(
    record: DurableProvenanceRecord,
    snapshot: DurableJobStateSnapshot,
    manifest: DurableArtifactStorageManifest,
) -> bool:
    candidate = _record_from_evidence(
        snapshot,
        manifest,
        sequence=record.sequence,
        previous_record_sha256=record.previous_record_sha256,
    )
    return candidate == record


def build_durable_provenance_chain(
    snapshot: DurableJobStateSnapshot,
    manifest: DurableArtifactStorageManifest,
) -> DurableProvenanceChain:
    """Create the initial bounded provenance record without performing I/O."""

    checked_snapshot = _require_snapshot(snapshot)
    checked_manifest = _require_manifest(manifest)
    _require_identity_convergence(checked_snapshot, checked_manifest)
    if checked_snapshot.state != "planned" or checked_snapshot.revision != 0:
        raise DurableProvenanceError("state_history_invalid")

    record = _record_from_evidence(
        checked_snapshot,
        checked_manifest,
        sequence=0,
        previous_record_sha256=None,
    )
    chain = DurableProvenanceChain(
        version=DURABLE_PROVENANCE_CONTRACT_VERSION,
        records=(record,),
    )
    verify_durable_provenance_chain(chain, checked_snapshot, checked_manifest)
    return chain


def append_durable_provenance_record_idempotently(
    chain: DurableProvenanceChain,
    snapshot: DurableJobStateSnapshot,
    manifest: DurableArtifactStorageManifest,
) -> DurableProvenanceAppendResult:
    """Append one provenance record or return exact replay; never persist it."""

    if type(chain) is not DurableProvenanceChain:
        raise DurableProvenanceError("chain_invalid")
    checked_snapshot = _require_snapshot(snapshot)
    checked_manifest = _require_manifest(manifest)
    _require_identity_convergence(checked_snapshot, checked_manifest)

    latest = chain.records[-1]
    if _record_matches_evidence(latest, checked_snapshot, checked_manifest):
        return DurableProvenanceAppendResult(chain=chain, replayed=True)

    if (
        latest.dispatch_identity_sha256 != checked_snapshot.dispatch_identity_sha256
        or latest.plan_id != checked_snapshot.plan_id
        or latest.plan_sha256 != checked_snapshot.plan_sha256
        or latest.job_id != checked_snapshot.job_id
        or latest.source_artifact_id != checked_snapshot.source_artifact_id
        or latest.source_sha256 != checked_snapshot.source_sha256
        or latest.run_id != checked_snapshot.run_id
        or latest.engine != checked_snapshot.engine
        or latest.lifecycle_id != checked_manifest.lifecycle_id
    ):
        raise DurableProvenanceError("identity_mismatch")

    if checked_snapshot.revision < latest.state_revision:
        raise DurableProvenanceError("state_history_invalid")
    if checked_snapshot.revision == latest.state_revision:
        if checked_snapshot.state != latest.state:
            raise DurableProvenanceError("state_history_invalid")
    elif checked_snapshot.revision == latest.state_revision + 1:
        try:
            validate_durable_job_state_transition(
                latest.state,
                latest.state_revision,
                checked_snapshot.state,
            )
        except DurableJobStateError:
            raise DurableProvenanceError("state_history_invalid") from None
    else:
        raise DurableProvenanceError("state_history_invalid")

    current_bindings = {
        record.binding_sha256 for record in checked_manifest.records
    }
    if not set(latest.storage_binding_sha256s).issubset(current_bindings):
        raise DurableProvenanceError("storage_history_invalid")
    if checked_snapshot.revision == latest.state_revision and len(
        current_bindings
    ) <= len(latest.storage_binding_sha256s):
        raise DurableProvenanceError("storage_history_invalid")

    record = _record_from_evidence(
        checked_snapshot,
        checked_manifest,
        sequence=len(chain.records),
        previous_record_sha256=latest.record_sha256,
    )
    try:
        updated = DurableProvenanceChain(
            version=chain.version,
            records=chain.records + (record,),
        )
    except DurableProvenanceError as exc:
        if exc.category == "chain_invalid":
            raise DurableProvenanceError("provenance_invalid") from None
        raise
    verify_durable_provenance_chain(updated, checked_snapshot, checked_manifest)
    return DurableProvenanceAppendResult(chain=updated, replayed=False)


def verify_durable_provenance_chain(
    chain: DurableProvenanceChain,
    snapshot: DurableJobStateSnapshot,
    manifest: DurableArtifactStorageManifest,
) -> None:
    """Verify the latest record against exact D.1 and D.3 evidence."""

    if type(chain) is not DurableProvenanceChain:
        raise DurableProvenanceError("chain_invalid")
    checked_snapshot = _require_snapshot(snapshot)
    checked_manifest = _require_manifest(manifest)
    _require_identity_convergence(checked_snapshot, checked_manifest)

    latest = chain.records[-1]
    if not _record_matches_evidence(latest, checked_snapshot, checked_manifest):
        raise DurableProvenanceError("provenance_mismatch")
