"""Append-only candidate and artifact lifecycle contract for future OMR execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re
from typing import Any, Mapping

from .orchestration import (
    ENGINE_NAMES,
    OrchestrationContractError,
    verify_orchestration_plan,
)

LIFECYCLE_SCHEMA_VERSION = "1.0"
LIFECYCLE_CONTRACT_TYPE = "scoremosaic-gateway-candidate-artifact-lifecycle"
CANDIDATE_STATES = (
    "reserved",
    "collecting",
    "sealed",
    "failed",
    "cancelled",
    "timed_out",
)
ARTIFACT_STATES = (
    "reserved",
    "writing",
    "sealed",
    "rejected",
    "abandoned",
)
OUTPUT_ARTIFACT_KINDS = (
    "raw_engine_result",
    "musicxml",
    "diagnostic",
)
TERMINAL_CANDIDATE_STATES = (
    "sealed",
    "failed",
    "cancelled",
    "timed_out",
)
TERMINAL_ARTIFACT_STATES = (
    "sealed",
    "rejected",
    "abandoned",
)

_CANDIDATE_TRANSITIONS = {
    "reserved": ("collecting", "failed", "cancelled", "timed_out"),
    "collecting": ("sealed", "failed", "cancelled", "timed_out"),
    "sealed": (),
    "failed": (),
    "cancelled": (),
    "timed_out": (),
}
_ARTIFACT_TRANSITIONS = {
    "reserved": ("writing", "rejected", "abandoned"),
    "writing": ("sealed", "rejected", "abandoned"),
    "sealed": (),
    "rejected": (),
    "abandoned": (),
}
_OUTPUT_MEDIA_TYPES = {
    "raw_engine_result": "application/octet-stream",
    "musicxml": "application/vnd.recordare.musicxml+xml",
    "diagnostic": "application/json",
}
_REASON_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_JOB_ID_PATTERN = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ARTIFACT_ID_PATTERN = re.compile(r"^artifact_[a-f0-9]{24}$")
_RUN_ID_PATTERN = re.compile(r"^run_[a-f0-9]{24}$")
_CANDIDATE_ID_PATTERN = re.compile(r"^candidate_[a-f0-9]{24}$")
_PLAN_ID_PATTERN = re.compile(r"^plan_[a-f0-9]{24}$")
_SAFE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")
_ZERO_SHA256 = "0" * 64
_MAX_ARTIFACT_BYTES = 200 * 1024 * 1024

_POLICIES = {
    "appendOnlyEvents": True,
    "sourceImmutable": True,
    "rawEngineResultPreserved": True,
    "hashRequiredBeforeSeal": True,
    "overwriteAllowed": False,
    "crossEngineWriteAllowed": False,
    "terminalStateReopenAllowed": False,
    "candidateSealRequiresAllArtifactsSealed": True,
}
_BOUNDARIES = {
    "executionEnabled": False,
    "uploadEnabled": False,
    "networkDispatchEnabled": False,
    "queueEnabled": False,
    "persistenceEnabled": False,
    "storageWritesEnabled": False,
    "runtimeMutationEnabled": False,
    "engineRanking": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherApproval": False,
    "publication": False,
}


class ArtifactLifecycleError(ValueError):
    """Raised when a candidate or artifact lifecycle violates the contract."""


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _validate_ref(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_REF_PATTERN.fullmatch(value):
        raise ArtifactLifecycleError("artifact_ref is invalid")
    if value.startswith("/") or "\\" in value or "//" in value:
        raise ArtifactLifecycleError("artifact_ref must be a normalized relative key")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ArtifactLifecycleError("artifact_ref contains an unsafe path segment")
    return value


def _validate_reason(value: str | None, *, required: bool) -> str | None:
    if required:
        if not isinstance(value, str) or not _REASON_PATTERN.fullmatch(value):
            raise ArtifactLifecycleError("a normalized reason_code is required")
        return value
    if value is not None:
        raise ArtifactLifecycleError("reason_code is not allowed for this transition")
    return None


def _require_size(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArtifactLifecycleError("size_bytes must be an integer")
    if not 1 <= value <= _MAX_ARTIFACT_BYTES:
        raise ArtifactLifecycleError(
            f"size_bytes must be between 1 and {_MAX_ARTIFACT_BYTES}"
        )
    return value


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    kind: str
    artifact_ref: str
    state: str
    candidate_id: str | None
    engine: str | None
    sha256: str | None = None
    size_bytes: int | None = None
    media_type: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not _ARTIFACT_ID_PATTERN.fullmatch(self.artifact_id):
            raise ArtifactLifecycleError("artifact_id is invalid")
        _validate_ref(self.artifact_ref)
        if self.kind not in {"source", *OUTPUT_ARTIFACT_KINDS}:
            raise ArtifactLifecycleError("artifact kind is invalid")
        if self.state not in ARTIFACT_STATES:
            raise ArtifactLifecycleError("artifact state is invalid")

        if self.kind == "source":
            if self.candidate_id is not None or self.engine is not None:
                raise ArtifactLifecycleError("source artifact cannot belong to a candidate")
            if self.state != "sealed":
                raise ArtifactLifecycleError("source artifact must remain sealed")
        else:
            if (
                not isinstance(self.candidate_id, str)
                or not _CANDIDATE_ID_PATTERN.fullmatch(self.candidate_id)
            ):
                raise ArtifactLifecycleError("output artifact candidate_id is invalid")
            if self.engine not in ENGINE_NAMES:
                raise ArtifactLifecycleError("output artifact engine is invalid")

        if self.state == "sealed":
            if not isinstance(self.sha256, str) or not _SHA256_PATTERN.fullmatch(
                self.sha256
            ):
                raise ArtifactLifecycleError("sealed artifact sha256 is invalid")
            _require_size(self.size_bytes)
            if not isinstance(self.media_type, str) or not self.media_type:
                raise ArtifactLifecycleError("sealed artifact media_type is required")
            if self.kind in _OUTPUT_MEDIA_TYPES:
                expected_media_type = _OUTPUT_MEDIA_TYPES[self.kind]
                if self.media_type != expected_media_type:
                    raise ArtifactLifecycleError(
                        f"{self.kind} media_type must be {expected_media_type}"
                    )
            _validate_reason(self.reason_code, required=False)
        else:
            if any(
                value is not None
                for value in (self.sha256, self.size_bytes, self.media_type)
            ):
                raise ArtifactLifecycleError(
                    "unsealed artifact cannot contain content metadata"
                )
            _validate_reason(
                self.reason_code,
                required=self.state in {"rejected", "abandoned"},
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "kind": self.kind,
            "artifactRef": self.artifact_ref,
            "candidateId": self.candidate_id,
            "engine": self.engine,
            "state": self.state,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "mediaType": self.media_type,
            "reasonCode": self.reason_code,
            "immutable": True,
            "overwriteAllowed": False,
        }


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    candidate_id: str
    run_id: str
    engine: str
    candidate_namespace: str
    state: str
    artifacts: tuple[ArtifactRecord, ...]
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not _CANDIDATE_ID_PATTERN.fullmatch(self.candidate_id):
            raise ArtifactLifecycleError("candidate_id is invalid")
        if not _RUN_ID_PATTERN.fullmatch(self.run_id):
            raise ArtifactLifecycleError("run_id is invalid")
        if self.engine not in ENGINE_NAMES:
            raise ArtifactLifecycleError("candidate engine is invalid")
        _validate_ref(self.candidate_namespace)
        if self.state not in CANDIDATE_STATES:
            raise ArtifactLifecycleError("candidate state is invalid")
        if tuple(item.kind for item in self.artifacts) != OUTPUT_ARTIFACT_KINDS:
            raise ArtifactLifecycleError(
                "candidate artifacts must be raw_engine_result, musicxml, diagnostic"
            )
        if len({item.artifact_id for item in self.artifacts}) != len(self.artifacts):
            raise ArtifactLifecycleError("candidate artifact IDs must be unique")
        for artifact in self.artifacts:
            if artifact.candidate_id != self.candidate_id:
                raise ArtifactLifecycleError("artifact candidate relationship is invalid")
            if artifact.engine != self.engine:
                raise ArtifactLifecycleError("artifact engine relationship is invalid")
            if not artifact.artifact_ref.startswith(
                self.candidate_namespace + "/"
            ):
                raise ArtifactLifecycleError(
                    "artifact_ref escapes the candidate namespace"
                )

        if self.state == "sealed":
            if any(item.state != "sealed" for item in self.artifacts):
                raise ArtifactLifecycleError(
                    "sealed candidate requires every artifact to be sealed"
                )
            _validate_reason(self.reason_code, required=False)
        elif self.state in {"failed", "cancelled", "timed_out"}:
            if any(
                item.state not in TERMINAL_ARTIFACT_STATES
                for item in self.artifacts
            ):
                raise ArtifactLifecycleError(
                    "terminal candidate requires terminal artifact states"
                )
            _validate_reason(self.reason_code, required=True)
        else:
            _validate_reason(self.reason_code, required=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidate_id,
            "runId": self.run_id,
            "engine": self.engine,
            "candidateNamespace": self.candidate_namespace,
            "state": self.state,
            "reasonCode": self.reason_code,
            "terminal": self.state in TERMINAL_CANDIDATE_STATES,
            "artifacts": [item.as_dict() for item in self.artifacts],
        }


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    sequence: int
    event_type: str
    target_id: str
    from_state: str
    to_state: str
    previous_event_sha256: str
    reason_code: str | None = None
    content_sha256: str | None = None
    size_bytes: int | None = None
    media_type: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ArtifactLifecycleError("event sequence must be an integer")
        if self.sequence < 1:
            raise ArtifactLifecycleError("event sequence must be positive")
        if self.event_type not in {
            "candidate_state_changed",
            "artifact_state_changed",
        }:
            raise ArtifactLifecycleError("event_type is invalid")
        if self.event_type == "candidate_state_changed":
            if not _CANDIDATE_ID_PATTERN.fullmatch(self.target_id):
                raise ArtifactLifecycleError("candidate event target is invalid")
            if self.from_state not in CANDIDATE_STATES:
                raise ArtifactLifecycleError("candidate from_state is invalid")
            if self.to_state not in CANDIDATE_STATES:
                raise ArtifactLifecycleError("candidate to_state is invalid")
        else:
            if not _ARTIFACT_ID_PATTERN.fullmatch(self.target_id):
                raise ArtifactLifecycleError("artifact event target is invalid")
            if self.from_state not in ARTIFACT_STATES:
                raise ArtifactLifecycleError("artifact from_state is invalid")
            if self.to_state not in ARTIFACT_STATES:
                raise ArtifactLifecycleError("artifact to_state is invalid")
        if not _SHA256_PATTERN.fullmatch(self.previous_event_sha256):
            raise ArtifactLifecycleError("previous_event_sha256 is invalid")

        content_values = (self.content_sha256, self.size_bytes, self.media_type)
        if self.to_state == "sealed" and self.event_type == "artifact_state_changed":
            if not isinstance(self.content_sha256, str) or not _SHA256_PATTERN.fullmatch(
                self.content_sha256
            ):
                raise ArtifactLifecycleError("sealed event content sha256 is invalid")
            _require_size(self.size_bytes)
            if not isinstance(self.media_type, str) or not self.media_type:
                raise ArtifactLifecycleError("sealed event media_type is required")
        elif any(value is not None for value in content_values):
            raise ArtifactLifecycleError(
                "content metadata is only allowed for artifact sealing"
            )

    def _core(self) -> dict[str, Any]:
        content = None
        if self.content_sha256 is not None:
            content = {
                "sha256": self.content_sha256,
                "sizeBytes": self.size_bytes,
                "mediaType": self.media_type,
            }
        return {
            "sequence": self.sequence,
            "eventType": self.event_type,
            "targetId": self.target_id,
            "fromState": self.from_state,
            "toState": self.to_state,
            "reasonCode": self.reason_code,
            "content": content,
            "previousEventSha256": self.previous_event_sha256,
        }

    @property
    def event_id(self) -> str:
        digest = hashlib.sha256(_canonical_json(self._core())).hexdigest()
        return f"event_{digest[:24]}"

    @property
    def event_sha256(self) -> str:
        payload = self._core()
        payload["eventId"] = self.event_id
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        payload = self._core()
        payload["eventId"] = self.event_id
        payload["eventSha256"] = self.event_sha256
        return payload


@dataclass(frozen=True, slots=True)
class CandidateArtifactLifecycle:
    plan_id: str
    plan_sha256: str
    job_id: str
    source_artifact: ArtifactRecord
    candidates: tuple[CandidateRecord, ...]
    events: tuple[LifecycleEvent, ...] = ()

    def __post_init__(self) -> None:
        if not _PLAN_ID_PATTERN.fullmatch(self.plan_id):
            raise ArtifactLifecycleError("plan_id is invalid")
        if not _SHA256_PATTERN.fullmatch(self.plan_sha256):
            raise ArtifactLifecycleError("plan_sha256 is invalid")
        if not _JOB_ID_PATTERN.fullmatch(self.job_id):
            raise ArtifactLifecycleError("job_id is invalid")
        if self.source_artifact.kind != "source":
            raise ArtifactLifecycleError("source_artifact kind is invalid")
        engines = tuple(item.engine for item in self.candidates)
        if engines != tuple(engine for engine in ENGINE_NAMES if engine in engines):
            raise ArtifactLifecycleError("candidate order is not canonical")
        if len(engines) != len(set(engines)):
            raise ArtifactLifecycleError("candidate engines must be unique")
        candidate_ids = [item.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ArtifactLifecycleError("candidate IDs must be unique")
        artifact_ids = [self.source_artifact.artifact_id]
        artifact_ids.extend(
            artifact.artifact_id
            for candidate in self.candidates
            for artifact in candidate.artifacts
        )
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ArtifactLifecycleError("artifact IDs must be globally unique")
        expected_sequence = 1
        previous_sha = _ZERO_SHA256
        for event in self.events:
            if event.sequence != expected_sequence:
                raise ArtifactLifecycleError("event sequence is not contiguous")
            if event.previous_event_sha256 != previous_sha:
                raise ArtifactLifecycleError("event hash chain is broken")
            previous_sha = event.event_sha256
            expected_sequence += 1

    @property
    def lifecycle_id(self) -> str:
        return _digest_id(
            "lifecycle",
            LIFECYCLE_SCHEMA_VERSION,
            self.plan_id,
            self.plan_sha256,
        )

    def _payload_core(self) -> dict[str, Any]:
        return {
            "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
            "contractType": LIFECYCLE_CONTRACT_TYPE,
            "planRef": {
                "planId": self.plan_id,
                "planSha256": self.plan_sha256,
                "jobId": self.job_id,
            },
            "sequence": len(self.events),
            "sourceArtifact": self.source_artifact.as_dict(),
            "candidates": [item.as_dict() for item in self.candidates],
            "events": [item.as_dict() for item in self.events],
            "policies": dict(_POLICIES),
            "boundaries": dict(_BOUNDARIES),
        }

    @property
    def lifecycle_sha256(self) -> str:
        payload = self._payload_core()
        payload["lifecycleId"] = self.lifecycle_id
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        payload = self._payload_core()
        payload["lifecycleId"] = self.lifecycle_id
        payload["lifecycleSha256"] = self.lifecycle_sha256
        return payload

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
        )


def _build_initial_lifecycle(
    orchestration_plan: Mapping[str, Any],
) -> CandidateArtifactLifecycle:
    try:
        verify_orchestration_plan(orchestration_plan)
    except (OrchestrationContractError, TypeError, ValueError) as exc:
        raise ArtifactLifecycleError("orchestration plan verification failed") from exc

    source = orchestration_plan["sourceArtifact"]
    source_record = ArtifactRecord(
        artifact_id=source["artifactId"],
        kind="source",
        artifact_ref=source["artifactRef"],
        state="sealed",
        candidate_id=None,
        engine=None,
        sha256=source["sha256"],
        size_bytes=source["sizeBytes"],
        media_type=source["mediaType"],
    )

    candidates: list[CandidateRecord] = []
    for run in orchestration_plan["engineRuns"]:
        expected_by_kind = {
            item["kind"]: item for item in run["expectedArtifacts"]
        }
        raw_artifact = ArtifactRecord(
            artifact_id=_digest_id(
                "artifact",
                LIFECYCLE_SCHEMA_VERSION,
                run["candidateId"],
                "raw_engine_result",
            ),
            kind="raw_engine_result",
            artifact_ref=f'{run["candidateNamespace"]}/raw-engine-result',
            state="reserved",
            candidate_id=run["candidateId"],
            engine=run["engine"],
        )
        musicxml_plan = expected_by_kind["musicxml"]
        diagnostic_plan = expected_by_kind["diagnostic"]
        candidates.append(
            CandidateRecord(
                candidate_id=run["candidateId"],
                run_id=run["runId"],
                engine=run["engine"],
                candidate_namespace=run["candidateNamespace"],
                state="reserved",
                artifacts=(
                    raw_artifact,
                    ArtifactRecord(
                        artifact_id=musicxml_plan["artifactId"],
                        kind="musicxml",
                        artifact_ref=musicxml_plan["artifactRef"],
                        state="reserved",
                        candidate_id=run["candidateId"],
                        engine=run["engine"],
                    ),
                    ArtifactRecord(
                        artifact_id=diagnostic_plan["artifactId"],
                        kind="diagnostic",
                        artifact_ref=diagnostic_plan["artifactRef"],
                        state="reserved",
                        candidate_id=run["candidateId"],
                        engine=run["engine"],
                    ),
                ),
            )
        )

    return CandidateArtifactLifecycle(
        plan_id=orchestration_plan["planId"],
        plan_sha256=orchestration_plan["planSha256"],
        job_id=orchestration_plan["jobId"],
        source_artifact=source_record,
        candidates=tuple(candidates),
    )


def build_artifact_lifecycle(
    orchestration_plan: Mapping[str, Any],
) -> CandidateArtifactLifecycle:
    """Build an immutable in-memory lifecycle without reading or writing bytes."""

    if not isinstance(orchestration_plan, Mapping):
        raise ArtifactLifecycleError("orchestration_plan must be a mapping")
    return _build_initial_lifecycle(orchestration_plan)


def _next_previous_sha(lifecycle: CandidateArtifactLifecycle) -> str:
    return (
        lifecycle.events[-1].event_sha256
        if lifecycle.events
        else _ZERO_SHA256
    )


def transition_artifact(
    lifecycle: CandidateArtifactLifecycle,
    artifact_id: str,
    to_state: str,
    *,
    sha256: str | None = None,
    size_bytes: int | None = None,
    media_type: str | None = None,
    reason_code: str | None = None,
) -> CandidateArtifactLifecycle:
    """Return a new lifecycle with one validated append-only artifact event."""

    if not isinstance(lifecycle, CandidateArtifactLifecycle):
        raise ArtifactLifecycleError("lifecycle must be a CandidateArtifactLifecycle")
    if lifecycle.source_artifact.artifact_id == artifact_id:
        raise ArtifactLifecycleError("source artifact transitions are forbidden")
    if to_state not in ARTIFACT_STATES:
        raise ArtifactLifecycleError("artifact to_state is invalid")

    candidate_index = -1
    artifact_index = -1
    current: ArtifactRecord | None = None
    owner: CandidateRecord | None = None
    for index, candidate in enumerate(lifecycle.candidates):
        for output_index, artifact in enumerate(candidate.artifacts):
            if artifact.artifact_id == artifact_id:
                candidate_index = index
                artifact_index = output_index
                current = artifact
                owner = candidate
                break
        if current is not None:
            break
    if current is None or owner is None:
        raise ArtifactLifecycleError("artifact_id is unknown")
    if to_state not in _ARTIFACT_TRANSITIONS[current.state]:
        raise ArtifactLifecycleError(
            f"artifact transition {current.state}->{to_state} is not allowed"
        )
    if to_state in {"writing", "sealed"} and owner.state != "collecting":
        raise ArtifactLifecycleError(
            "artifact writing and sealing require a collecting candidate"
        )

    if to_state == "sealed":
        if not isinstance(sha256, str) or not _SHA256_PATTERN.fullmatch(sha256):
            raise ArtifactLifecycleError("sealed artifact sha256 is invalid")
        checked_size = _require_size(size_bytes)
        expected_media_type = _OUTPUT_MEDIA_TYPES[current.kind]
        if media_type != expected_media_type:
            raise ArtifactLifecycleError(
                f"{current.kind} media_type must be {expected_media_type}"
            )
        checked_reason = _validate_reason(reason_code, required=False)
    elif to_state in {"rejected", "abandoned"}:
        if any(value is not None for value in (sha256, size_bytes, media_type)):
            raise ArtifactLifecycleError(
                "rejected or abandoned artifacts cannot contain content metadata"
            )
        checked_size = None
        checked_reason = _validate_reason(reason_code, required=True)
    else:
        if any(value is not None for value in (sha256, size_bytes, media_type)):
            raise ArtifactLifecycleError(
                "writing artifact cannot contain final content metadata"
            )
        checked_size = None
        checked_reason = _validate_reason(reason_code, required=False)

    updated_artifact = replace(
        current,
        state=to_state,
        sha256=sha256 if to_state == "sealed" else None,
        size_bytes=checked_size if to_state == "sealed" else None,
        media_type=media_type if to_state == "sealed" else None,
        reason_code=checked_reason,
    )
    updated_artifacts = list(owner.artifacts)
    updated_artifacts[artifact_index] = updated_artifact
    updated_candidate = replace(owner, artifacts=tuple(updated_artifacts))
    updated_candidates = list(lifecycle.candidates)
    updated_candidates[candidate_index] = updated_candidate

    event = LifecycleEvent(
        sequence=len(lifecycle.events) + 1,
        event_type="artifact_state_changed",
        target_id=artifact_id,
        from_state=current.state,
        to_state=to_state,
        previous_event_sha256=_next_previous_sha(lifecycle),
        reason_code=checked_reason,
        content_sha256=sha256 if to_state == "sealed" else None,
        size_bytes=checked_size if to_state == "sealed" else None,
        media_type=media_type if to_state == "sealed" else None,
    )
    return CandidateArtifactLifecycle(
        plan_id=lifecycle.plan_id,
        plan_sha256=lifecycle.plan_sha256,
        job_id=lifecycle.job_id,
        source_artifact=lifecycle.source_artifact,
        candidates=tuple(updated_candidates),
        events=lifecycle.events + (event,),
    )


def transition_candidate(
    lifecycle: CandidateArtifactLifecycle,
    candidate_id: str,
    to_state: str,
    *,
    reason_code: str | None = None,
) -> CandidateArtifactLifecycle:
    """Return a new lifecycle with one validated append-only candidate event."""

    if not isinstance(lifecycle, CandidateArtifactLifecycle):
        raise ArtifactLifecycleError("lifecycle must be a CandidateArtifactLifecycle")
    if to_state not in CANDIDATE_STATES:
        raise ArtifactLifecycleError("candidate to_state is invalid")

    candidate_index = -1
    current: CandidateRecord | None = None
    for index, candidate in enumerate(lifecycle.candidates):
        if candidate.candidate_id == candidate_id:
            candidate_index = index
            current = candidate
            break
    if current is None:
        raise ArtifactLifecycleError("candidate_id is unknown")
    if to_state not in _CANDIDATE_TRANSITIONS[current.state]:
        raise ArtifactLifecycleError(
            f"candidate transition {current.state}->{to_state} is not allowed"
        )

    if to_state == "sealed":
        if any(item.state != "sealed" for item in current.artifacts):
            raise ArtifactLifecycleError(
                "candidate cannot be sealed before all artifacts are sealed"
            )
        checked_reason = _validate_reason(reason_code, required=False)
    elif to_state in {"failed", "cancelled", "timed_out"}:
        if any(
            item.state not in TERMINAL_ARTIFACT_STATES
            for item in current.artifacts
        ):
            raise ArtifactLifecycleError(
                "terminal candidate requires all artifacts to be terminal"
            )
        checked_reason = _validate_reason(reason_code, required=True)
    else:
        checked_reason = _validate_reason(reason_code, required=False)

    updated_candidate = replace(
        current,
        state=to_state,
        reason_code=checked_reason,
    )
    updated_candidates = list(lifecycle.candidates)
    updated_candidates[candidate_index] = updated_candidate
    event = LifecycleEvent(
        sequence=len(lifecycle.events) + 1,
        event_type="candidate_state_changed",
        target_id=candidate_id,
        from_state=current.state,
        to_state=to_state,
        previous_event_sha256=_next_previous_sha(lifecycle),
        reason_code=checked_reason,
    )
    return CandidateArtifactLifecycle(
        plan_id=lifecycle.plan_id,
        plan_sha256=lifecycle.plan_sha256,
        job_id=lifecycle.job_id,
        source_artifact=lifecycle.source_artifact,
        candidates=tuple(updated_candidates),
        events=lifecycle.events + (event,),
    )


def verify_artifact_lifecycle(
    payload: Mapping[str, Any],
    orchestration_plan: Mapping[str, Any],
) -> None:
    """Replay the append-only event ledger and verify the exact final snapshot."""

    if not isinstance(payload, Mapping):
        raise ArtifactLifecycleError("payload must be a mapping")
    if not isinstance(orchestration_plan, Mapping):
        raise ArtifactLifecycleError("orchestration_plan must be a mapping")

    try:
        events = payload["events"]
        if not isinstance(events, list):
            raise ArtifactLifecycleError("events must be a list")
        replay = build_artifact_lifecycle(orchestration_plan)
        for event_payload in events:
            if not isinstance(event_payload, Mapping):
                raise ArtifactLifecycleError("event must be a mapping")
            event_type = event_payload["eventType"]
            target_id = event_payload["targetId"]
            to_state = event_payload["toState"]
            reason_code = event_payload["reasonCode"]
            content = event_payload["content"]

            if event_type == "candidate_state_changed":
                if content is not None:
                    raise ArtifactLifecycleError(
                        "candidate event cannot contain artifact content"
                    )
                replay = transition_candidate(
                    replay,
                    target_id,
                    to_state,
                    reason_code=reason_code,
                )
            elif event_type == "artifact_state_changed":
                if content is None:
                    replay = transition_artifact(
                        replay,
                        target_id,
                        to_state,
                        reason_code=reason_code,
                    )
                else:
                    if not isinstance(content, Mapping):
                        raise ArtifactLifecycleError(
                            "artifact event content must be a mapping"
                        )
                    replay = transition_artifact(
                        replay,
                        target_id,
                        to_state,
                        sha256=content["sha256"],
                        size_bytes=content["sizeBytes"],
                        media_type=content["mediaType"],
                        reason_code=reason_code,
                    )
            else:
                raise ArtifactLifecycleError("event_type is invalid")

            if replay.events[-1].as_dict() != dict(event_payload):
                raise ArtifactLifecycleError("event integrity verification failed")

        if replay.as_dict() != dict(payload):
            raise ArtifactLifecycleError("lifecycle snapshot verification failed")
    except ArtifactLifecycleError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ArtifactLifecycleError("lifecycle payload structure is invalid") from exc
