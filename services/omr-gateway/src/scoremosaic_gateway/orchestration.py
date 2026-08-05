"""Immutable versioned orchestration contract for future OMR execution."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

ORCHESTRATION_SCHEMA_VERSION = "1.0"
ORCHESTRATION_CONTRACT_TYPE = "scoremosaic-gateway-orchestration-plan"
ENGINE_NAMES = ("audiveris", "homr", "clarity")
ACCEPTED_SOURCE_MEDIA_TYPES = (
    "application/pdf",
    "image/jpeg",
    "image/png",
)
DEFAULT_ENGINE_TIMEOUT_SECONDS = 3600
MIN_ENGINE_TIMEOUT_SECONDS = 30
MAX_ENGINE_TIMEOUT_SECONDS = 7200
DEFAULT_CANCELLATION_GRACE_SECONDS = 30
MAX_CANCELLATION_GRACE_SECONDS = 300
MAX_SOURCE_BYTES = 100 * 1024 * 1024

_JOB_ID_PATTERN = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ARTIFACT_ID_PATTERN = re.compile(r"^artifact_[a-f0-9]{24}$")
_RUN_ID_PATTERN = re.compile(r"^run_[a-f0-9]{24}$")
_CANDIDATE_ID_PATTERN = re.compile(r"^candidate_[a-f0-9]{24}$")
_PLAN_ID_PATTERN = re.compile(r"^plan_[a-f0-9]{24}$")
_SAFE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")

_ENGINE_RUN_TRANSITIONS = {
    "planned": ["queued", "cancelled"],
    "queued": ["dispatching", "cancelled", "timed_out"],
    "dispatching": ["running", "failed", "cancelled", "timed_out"],
    "running": ["completed", "failed", "cancelled", "timed_out"],
    "completed": [],
    "failed": [],
    "cancelled": [],
    "timed_out": [],
}

_BOUNDARIES = {
    "executionEnabled": False,
    "uploadEnabled": False,
    "persistenceEnabled": False,
    "networkDispatchEnabled": False,
    "engineRanking": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherApproval": False,
    "publication": False,
}

_ARTIFACT_POLICY = {
    "sourceImmutable": True,
    "candidateIsolation": True,
    "hashRequired": True,
    "overwriteAllowed": False,
    "crossEngineWriteAllowed": False,
}


class OrchestrationContractError(ValueError):
    """Raised when an orchestration plan violates the versioned contract."""


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


def _validate_artifact_ref(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_REF_PATTERN.fullmatch(value):
        raise OrchestrationContractError("artifact_ref is invalid")
    if value.startswith("/") or "\\" in value or "//" in value:
        raise OrchestrationContractError("artifact_ref must be a normalized relative key")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise OrchestrationContractError("artifact_ref contains an unsafe path segment")
    return value


def _require_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OrchestrationContractError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise OrchestrationContractError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


@dataclass(frozen=True, slots=True)
class SourceArtifactPlan:
    artifact_id: str
    artifact_ref: str
    sha256: str
    size_bytes: int
    media_type: str

    def __post_init__(self) -> None:
        if not _ARTIFACT_ID_PATTERN.fullmatch(self.artifact_id):
            raise OrchestrationContractError("source artifact_id is invalid")
        _validate_artifact_ref(self.artifact_ref)
        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise OrchestrationContractError("source sha256 is invalid")
        _require_int(
            self.size_bytes,
            name="source size_bytes",
            minimum=1,
            maximum=MAX_SOURCE_BYTES,
        )
        if self.media_type not in ACCEPTED_SOURCE_MEDIA_TYPES:
            raise OrchestrationContractError("source media_type is unsupported")

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "artifactRef": self.artifact_ref,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "mediaType": self.media_type,
            "immutable": True,
        }


@dataclass(frozen=True, slots=True)
class ExpectedArtifactPlan:
    artifact_id: str
    kind: str
    artifact_ref: str

    def __post_init__(self) -> None:
        if not _ARTIFACT_ID_PATTERN.fullmatch(self.artifact_id):
            raise OrchestrationContractError("expected artifact_id is invalid")
        if self.kind not in {"musicxml", "diagnostic"}:
            raise OrchestrationContractError("expected artifact kind is invalid")
        _validate_artifact_ref(self.artifact_ref)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "kind": self.kind,
            "artifactRef": self.artifact_ref,
            "immutable": True,
            "sha256Required": True,
        }


@dataclass(frozen=True, slots=True)
class EngineRunPlan:
    run_id: str
    engine: str
    input_artifact_id: str
    candidate_id: str
    candidate_namespace: str
    timeout_seconds: int
    expected_artifacts: tuple[ExpectedArtifactPlan, ...]

    def __post_init__(self) -> None:
        if not _RUN_ID_PATTERN.fullmatch(self.run_id):
            raise OrchestrationContractError("run_id is invalid")
        if self.engine not in ENGINE_NAMES:
            raise OrchestrationContractError("engine is unsupported")
        if not _ARTIFACT_ID_PATTERN.fullmatch(self.input_artifact_id):
            raise OrchestrationContractError("input_artifact_id is invalid")
        if not _CANDIDATE_ID_PATTERN.fullmatch(self.candidate_id):
            raise OrchestrationContractError("candidate_id is invalid")
        _validate_artifact_ref(self.candidate_namespace)
        _require_int(
            self.timeout_seconds,
            name="engine timeout_seconds",
            minimum=MIN_ENGINE_TIMEOUT_SECONDS,
            maximum=MAX_ENGINE_TIMEOUT_SECONDS,
        )
        if tuple(item.kind for item in self.expected_artifacts) != (
            "musicxml",
            "diagnostic",
        ):
            raise OrchestrationContractError(
                "expected artifacts must be ordered as musicxml and diagnostic"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "engine": self.engine,
            "operation": "transcribe",
            "transportProfile": "private-engine-adapter-v1",
            "endpointKey": self.engine,
            "inputArtifactId": self.input_artifact_id,
            "candidateId": self.candidate_id,
            "candidateNamespace": self.candidate_namespace,
            "timeoutSeconds": self.timeout_seconds,
            "attemptLimit": 1,
            "initialState": "planned",
            "expectedArtifacts": [item.as_dict() for item in self.expected_artifacts],
        }


@dataclass(frozen=True, slots=True)
class GatewayOrchestrationPlan:
    job_id: str
    source_artifact: SourceArtifactPlan
    requested_engines: tuple[str, ...]
    engine_runs: tuple[EngineRunPlan, ...]
    cancellation_grace_seconds: int

    def __post_init__(self) -> None:
        if not _JOB_ID_PATTERN.fullmatch(self.job_id):
            raise OrchestrationContractError("job_id is invalid")
        if not self.requested_engines:
            raise OrchestrationContractError("at least one engine is required")
        if self.requested_engines != tuple(
            engine for engine in ENGINE_NAMES if engine in self.requested_engines
        ):
            raise OrchestrationContractError("requested engines are not canonical")
        if len(self.requested_engines) != len(set(self.requested_engines)):
            raise OrchestrationContractError("requested engines must be unique")
        if tuple(run.engine for run in self.engine_runs) != self.requested_engines:
            raise OrchestrationContractError("engine runs must match requested engines")
        if any(
            run.input_artifact_id != self.source_artifact.artifact_id
            for run in self.engine_runs
        ):
            raise OrchestrationContractError("engine run input does not match source")
        namespaces = tuple(run.candidate_namespace for run in self.engine_runs)
        if len(namespaces) != len(set(namespaces)):
            raise OrchestrationContractError("candidate namespaces must be isolated")
        _require_int(
            self.cancellation_grace_seconds,
            name="cancellation_grace_seconds",
            minimum=0,
            maximum=MAX_CANCELLATION_GRACE_SECONDS,
        )

    def _payload_core(self) -> dict[str, Any]:
        total_deadline = (
            max(run.timeout_seconds for run in self.engine_runs)
            + self.cancellation_grace_seconds
        )
        return {
            "schemaVersion": ORCHESTRATION_SCHEMA_VERSION,
            "contractType": ORCHESTRATION_CONTRACT_TYPE,
            "jobId": self.job_id,
            "sourceArtifact": self.source_artifact.as_dict(),
            "requestedEngines": list(self.requested_engines),
            "engineRuns": [run.as_dict() for run in self.engine_runs],
            "lifecyclePolicy": {
                "engineRunStates": list(_ENGINE_RUN_TRANSITIONS),
                "terminalEngineRunStates": [
                    "completed",
                    "failed",
                    "cancelled",
                    "timed_out",
                ],
                "allowedEngineRunTransitions": {
                    state: list(next_states)
                    for state, next_states in _ENGINE_RUN_TRANSITIONS.items()
                },
            },
            "timeoutPolicy": {
                "clock": "monotonic",
                "startsAt": "dispatch",
                "cancellationGraceSeconds": self.cancellation_grace_seconds,
                "totalDeadlineSeconds": total_deadline,
                "timeoutIsTerminal": True,
                "retryAfterTimeout": False,
            },
            "artifactPolicy": dict(_ARTIFACT_POLICY),
            "boundaries": dict(_BOUNDARIES),
        }

    @property
    def plan_id(self) -> str:
        digest = hashlib.sha256(_canonical_json(self._payload_core())).hexdigest()
        return f"plan_{digest[:24]}"

    @property
    def plan_sha256(self) -> str:
        payload = self._payload_core()
        payload["planId"] = self.plan_id
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        payload = self._payload_core()
        payload["planId"] = self.plan_id
        payload["planSha256"] = self.plan_sha256
        return payload

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
        )


def _canonical_engines(requested_engines: Iterable[str]) -> tuple[str, ...]:
    engines = tuple(requested_engines)
    if not engines:
        raise OrchestrationContractError("at least one engine is required")
    if any(not isinstance(engine, str) for engine in engines):
        raise OrchestrationContractError("engine names must be strings")
    if len(engines) != len(set(engines)):
        raise OrchestrationContractError("requested engines must be unique")
    unsupported = sorted(set(engines) - set(ENGINE_NAMES))
    if unsupported:
        raise OrchestrationContractError(
            f"unsupported engines: {', '.join(unsupported)}"
        )
    return tuple(engine for engine in ENGINE_NAMES if engine in engines)


def build_orchestration_plan(
    job_id: str,
    *,
    source_artifact_ref: str,
    source_sha256: str,
    source_size_bytes: int,
    source_media_type: str,
    requested_engines: Iterable[str] = ENGINE_NAMES,
    timeout_seconds_by_engine: Mapping[str, int] | None = None,
    cancellation_grace_seconds: int = DEFAULT_CANCELLATION_GRACE_SECONDS,
) -> GatewayOrchestrationPlan:
    """Build a deterministic plan only; no file, network, queue, or storage action occurs."""

    if not isinstance(job_id, str) or not _JOB_ID_PATTERN.fullmatch(job_id):
        raise OrchestrationContractError("job_id is invalid")
    source_ref = _validate_artifact_ref(source_artifact_ref)
    if not isinstance(source_sha256, str) or not _SHA256_PATTERN.fullmatch(
        source_sha256
    ):
        raise OrchestrationContractError("source_sha256 is invalid")
    size_bytes = _require_int(
        source_size_bytes,
        name="source_size_bytes",
        minimum=1,
        maximum=MAX_SOURCE_BYTES,
    )
    if source_media_type not in ACCEPTED_SOURCE_MEDIA_TYPES:
        raise OrchestrationContractError("source_media_type is unsupported")

    engines = _canonical_engines(requested_engines)
    timeout_values = {} if timeout_seconds_by_engine is None else dict(
        timeout_seconds_by_engine
    )
    unknown_timeout_keys = sorted(set(timeout_values) - set(engines))
    if unknown_timeout_keys:
        raise OrchestrationContractError(
            "timeouts contain unrequested engines: " + ", ".join(unknown_timeout_keys)
        )
    grace_seconds = _require_int(
        cancellation_grace_seconds,
        name="cancellation_grace_seconds",
        minimum=0,
        maximum=MAX_CANCELLATION_GRACE_SECONDS,
    )

    source_artifact_id = _digest_id(
        "artifact",
        ORCHESTRATION_SCHEMA_VERSION,
        job_id,
        source_ref,
        source_sha256,
    )
    source = SourceArtifactPlan(
        artifact_id=source_artifact_id,
        artifact_ref=source_ref,
        sha256=source_sha256,
        size_bytes=size_bytes,
        media_type=source_media_type,
    )

    runs: list[EngineRunPlan] = []
    for engine in engines:
        timeout_seconds = _require_int(
            timeout_values.get(engine, DEFAULT_ENGINE_TIMEOUT_SECONDS),
            name=f"{engine} timeout_seconds",
            minimum=MIN_ENGINE_TIMEOUT_SECONDS,
            maximum=MAX_ENGINE_TIMEOUT_SECONDS,
        )
        run_id = _digest_id(
            "run",
            ORCHESTRATION_SCHEMA_VERSION,
            job_id,
            engine,
            source_sha256,
        )
        candidate_id = _digest_id(
            "candidate",
            ORCHESTRATION_SCHEMA_VERSION,
            job_id,
            engine,
            run_id,
        )
        candidate_namespace = f"candidates/{job_id}/{engine}/{candidate_id}"
        expected_artifacts = tuple(
            ExpectedArtifactPlan(
                artifact_id=_digest_id(
                    "artifact",
                    ORCHESTRATION_SCHEMA_VERSION,
                    candidate_id,
                    kind,
                ),
                kind=kind,
                artifact_ref=f"{candidate_namespace}/{kind}",
            )
            for kind in ("musicxml", "diagnostic")
        )
        runs.append(
            EngineRunPlan(
                run_id=run_id,
                engine=engine,
                input_artifact_id=source.artifact_id,
                candidate_id=candidate_id,
                candidate_namespace=candidate_namespace,
                timeout_seconds=timeout_seconds,
                expected_artifacts=expected_artifacts,
            )
        )

    return GatewayOrchestrationPlan(
        job_id=job_id,
        source_artifact=source,
        requested_engines=engines,
        engine_runs=tuple(runs),
        cancellation_grace_seconds=grace_seconds,
    )


def verify_orchestration_plan(payload: Mapping[str, Any]) -> None:
    """Reject any payload that is not the exact deterministic v1 plan shape."""

    if not isinstance(payload, Mapping):
        raise OrchestrationContractError("orchestration plan must be an object")
    candidate = dict(payload)
    required_keys = {
        "schemaVersion",
        "contractType",
        "planId",
        "planSha256",
        "jobId",
        "sourceArtifact",
        "requestedEngines",
        "engineRuns",
        "lifecyclePolicy",
        "timeoutPolicy",
        "artifactPolicy",
        "boundaries",
    }
    if set(candidate) != required_keys:
        raise OrchestrationContractError("orchestration plan fields are not exact")
    if candidate.get("schemaVersion") != ORCHESTRATION_SCHEMA_VERSION:
        raise OrchestrationContractError("unsupported orchestration schemaVersion")
    if candidate.get("contractType") != ORCHESTRATION_CONTRACT_TYPE:
        raise OrchestrationContractError("unsupported orchestration contractType")
    if not isinstance(candidate.get("planId"), str) or not _PLAN_ID_PATTERN.fullmatch(
        candidate["planId"]
    ):
        raise OrchestrationContractError("planId is invalid")
    if not isinstance(candidate.get("planSha256"), str) or not _SHA256_PATTERN.fullmatch(
        candidate["planSha256"]
    ):
        raise OrchestrationContractError("planSha256 is invalid")

    source = candidate.get("sourceArtifact")
    if not isinstance(source, Mapping):
        raise OrchestrationContractError("sourceArtifact must be an object")
    if set(source) != {
        "artifactId",
        "artifactRef",
        "sha256",
        "sizeBytes",
        "mediaType",
        "immutable",
    }:
        raise OrchestrationContractError("sourceArtifact fields are not exact")

    engines = candidate.get("requestedEngines")
    engine_runs = candidate.get("engineRuns")
    timeout_policy = candidate.get("timeoutPolicy")
    if not isinstance(engines, list) or not all(
        isinstance(engine, str) for engine in engines
    ):
        raise OrchestrationContractError("requestedEngines must be a string array")
    if not isinstance(engine_runs, list):
        raise OrchestrationContractError("engineRuns must be an array")
    if not isinstance(timeout_policy, Mapping):
        raise OrchestrationContractError("timeoutPolicy must be an object")

    timeout_values: dict[str, int] = {}
    for run in engine_runs:
        if not isinstance(run, Mapping):
            raise OrchestrationContractError("engine run must be an object")
        engine = run.get("engine")
        timeout = run.get("timeoutSeconds")
        if not isinstance(engine, str):
            raise OrchestrationContractError("engine run name is invalid")
        timeout_values[engine] = _require_int(
            timeout,
            name=f"{engine} timeoutSeconds",
            minimum=MIN_ENGINE_TIMEOUT_SECONDS,
            maximum=MAX_ENGINE_TIMEOUT_SECONDS,
        )

    grace = _require_int(
        timeout_policy.get("cancellationGraceSeconds"),
        name="timeoutPolicy.cancellationGraceSeconds",
        minimum=0,
        maximum=MAX_CANCELLATION_GRACE_SECONDS,
    )
    expected = build_orchestration_plan(
        candidate.get("jobId"),
        source_artifact_ref=source.get("artifactRef"),
        source_sha256=source.get("sha256"),
        source_size_bytes=source.get("sizeBytes"),
        source_media_type=source.get("mediaType"),
        requested_engines=engines,
        timeout_seconds_by_engine=timeout_values,
        cancellation_grace_seconds=grace,
    ).as_dict()
    if candidate != expected:
        raise OrchestrationContractError(
            "orchestration plan does not match deterministic contract"
        )
