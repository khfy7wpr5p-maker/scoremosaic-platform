"""Engine-owned durable receiver authority foundation.

The authority stores only receiver-owned trusted orchestration-plan evidence and
one-way replay reservations.  State is create-once, HMAC sealed with an
engine-local integrity key, path-derived from validated identifiers, and read
without following symlinks.

This module intentionally grants no HTTP, credential provisioning, network
transport, retry, job mutation, orchestration, or engine-execution authority.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import errno
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any

_PACKAGE_TO_ENGINE = {
    "scoremosaic_audiveris": "audiveris",
    "scoremosaic_homr": "homr",
    "scoremosaic_clarity": "clarity",
}
ENGINE_NAME = _PACKAGE_TO_ENGINE.get(__package__)
if ENGINE_NAME is None:
    raise RuntimeError("receiver authority imported outside an engine package")
ENGINE_RECEIVER_AUTHORITY_VERSION = "scoremosaic-engine-receiver-authority-v1"
ENGINE_NAMES = ("audiveris", "homr", "clarity")
MAX_CANONICAL_PLAN_BYTES = 64 * 1024
MAX_STATE_RECORD_BYTES = 128 * 1024
MAX_REPLAY_LIFETIME_SECONDS = 2 * 60 * 60

_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_PLAN_ID_RE = re.compile(r"plan_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_CANDIDATE_ID_RE = re.compile(r"candidate_[0-9a-f]{24}\Z")
_SAFE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,499}\Z")
_ACCEPTED_MEDIA_TYPES = {"application/pdf", "image/jpeg", "image/png"}
_MIN_ENGINE_TIMEOUT_SECONDS = 30
_MAX_ENGINE_TIMEOUT_SECONDS = 7200
_MAX_SOURCE_BYTES = 100 * 1024 * 1024
_MAX_CANCELLATION_GRACE_SECONDS = 300
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
_ARTIFACT_POLICY = {
    "sourceImmutable": True,
    "candidateIsolation": True,
    "hashRequired": True,
    "overwriteAllowed": False,
    "crossEngineWriteAllowed": False,
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
_PLAN_MAC_DOMAIN = b"scoremosaic-engine-receiver-authority-plan-v1"
_REPLAY_MAC_DOMAIN = b"scoremosaic-engine-receiver-authority-replay-v1"
_MAC_FIELD = "integrity_mac"


class EngineReceiverAuthorityError(ValueError):
    """Stable fail-closed receiver-authority error category."""

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
        raise EngineReceiverAuthorityError("receiver_authority_state_invalid") from None


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise EngineReceiverAuthorityError("receiver_authority_json_invalid")
        result[key] = value
    return result


def _decode_canonical_json(raw: bytes, *, max_bytes: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= max_bytes:
        raise EngineReceiverAuthorityError("receiver_authority_json_invalid")
    try:
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except EngineReceiverAuthorityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError):
        raise EngineReceiverAuthorityError("receiver_authority_json_invalid") from None
    if type(value) is not dict or _canonical_json_bytes(value) != raw:
        raise EngineReceiverAuthorityError("receiver_authority_json_invalid")
    return value


def _require_sha256(value: object, *, category: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise EngineReceiverAuthorityError(category)
    return value


def _require_job_id(value: object, *, category: str) -> str:
    if type(value) is not str or _JOB_ID_RE.fullmatch(value) is None:
        raise EngineReceiverAuthorityError(category)
    return value


def _require_generation(value: object) -> str:
    if type(value) is not str or _GENERATION_RE.fullmatch(value) is None:
        raise EngineReceiverAuthorityError("receiver_authority_replay_input_invalid")
    return value


def _digest_id(prefix: str, *parts: str) -> str:
    digest = sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _valid_artifact_ref(value: object) -> bool:
    if type(value) is not str or _SAFE_REF_RE.fullmatch(value) is None:
        return False
    if value.startswith("/") or "\\" in value or "//" in value:
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _validate_trusted_plan(canonical_plan_bytes: bytes, *, expected_job_id: str) -> dict[str, Any]:
    """Verify exact deterministic Gateway orchestration-plan v1 semantics."""

    plan = _decode_canonical_json(canonical_plan_bytes, max_bytes=MAX_CANONICAL_PLAN_BYTES)
    required_keys = {
        "schemaVersion", "contractType", "planId", "planSha256", "jobId",
        "sourceArtifact", "requestedEngines", "engineRuns", "lifecyclePolicy",
        "timeoutPolicy", "artifactPolicy", "boundaries",
    }
    if (
        set(plan) != required_keys
        or plan.get("schemaVersion") != "1.0"
        or plan.get("contractType") != "scoremosaic-gateway-orchestration-plan"
        or plan.get("jobId") != expected_job_id
        or _JOB_ID_RE.fullmatch(expected_job_id) is None
    ):
        raise EngineReceiverAuthorityError("receiver_authority_plan_invalid")

    source = plan.get("sourceArtifact")
    requested = plan.get("requestedEngines")
    runs = plan.get("engineRuns")
    timeout_policy = plan.get("timeoutPolicy")
    if (
        type(source) is not dict
        or set(source) != {"artifactId", "artifactRef", "sha256", "sizeBytes", "mediaType", "immutable"}
        or not _valid_artifact_ref(source.get("artifactRef"))
        or type(source.get("sha256")) is not str
        or _SHA256_RE.fullmatch(source["sha256"]) is None
        or type(source.get("sizeBytes")) is not int
        or type(source.get("sizeBytes")) is bool
        or not 1 <= source["sizeBytes"] <= _MAX_SOURCE_BYTES
        or source.get("mediaType") not in _ACCEPTED_MEDIA_TYPES
        or source.get("immutable") is not True
        or type(requested) is not list
        or not requested
        or any(type(engine) is not str for engine in requested)
        or requested != [engine for engine in ENGINE_NAMES if engine in requested]
        or len(requested) != len(set(requested))
        or ENGINE_NAME not in requested
        or type(runs) is not list
        or len(runs) != len(requested)
        or type(timeout_policy) is not dict
    ):
        raise EngineReceiverAuthorityError("receiver_authority_plan_invalid")

    timeout_values: dict[str, int] = {}
    for expected_engine, run in zip(requested, runs, strict=True):
        if type(run) is not dict or run.get("engine") != expected_engine:
            raise EngineReceiverAuthorityError("receiver_authority_plan_invalid")
        timeout = run.get("timeoutSeconds")
        if (
            type(timeout) is not int
            or type(timeout) is bool
            or not _MIN_ENGINE_TIMEOUT_SECONDS <= timeout <= _MAX_ENGINE_TIMEOUT_SECONDS
        ):
            raise EngineReceiverAuthorityError("receiver_authority_plan_invalid")
        timeout_values[expected_engine] = timeout

    grace = timeout_policy.get("cancellationGraceSeconds")
    if (
        type(grace) is not int
        or type(grace) is bool
        or not 0 <= grace <= _MAX_CANCELLATION_GRACE_SECONDS
    ):
        raise EngineReceiverAuthorityError("receiver_authority_plan_invalid")

    source_artifact_id = _digest_id(
        "artifact", "1.0", expected_job_id, source["artifactRef"], source["sha256"]
    )
    expected_source = {
        "artifactId": source_artifact_id,
        "artifactRef": source["artifactRef"],
        "sha256": source["sha256"],
        "sizeBytes": source["sizeBytes"],
        "mediaType": source["mediaType"],
        "immutable": True,
    }
    expected_runs: list[dict[str, Any]] = []
    for engine in requested:
        run_id = _digest_id("run", "1.0", expected_job_id, engine, source["sha256"])
        candidate_id = _digest_id("candidate", "1.0", expected_job_id, engine, run_id)
        namespace = f"candidates/{expected_job_id}/{engine}/{candidate_id}"
        artifacts = []
        for kind in ("musicxml", "diagnostic"):
            artifacts.append({
                "artifactId": _digest_id("artifact", "1.0", candidate_id, kind),
                "kind": kind,
                "artifactRef": f"{namespace}/{kind}",
                "immutable": True,
                "sha256Required": True,
            })
        expected_runs.append({
            "runId": run_id,
            "engine": engine,
            "operation": "transcribe",
            "transportProfile": "private-engine-adapter-v1",
            "endpointKey": engine,
            "inputArtifactId": source_artifact_id,
            "candidateId": candidate_id,
            "candidateNamespace": namespace,
            "timeoutSeconds": timeout_values[engine],
            "attemptLimit": 1,
            "initialState": "planned",
            "expectedArtifacts": artifacts,
        })

    core = {
        "schemaVersion": "1.0",
        "contractType": "scoremosaic-gateway-orchestration-plan",
        "jobId": expected_job_id,
        "sourceArtifact": expected_source,
        "requestedEngines": list(requested),
        "engineRuns": expected_runs,
        "lifecyclePolicy": {
            "engineRunStates": list(_ENGINE_RUN_TRANSITIONS),
            "terminalEngineRunStates": ["completed", "failed", "cancelled", "timed_out"],
            "allowedEngineRunTransitions": {
                state: list(next_states) for state, next_states in _ENGINE_RUN_TRANSITIONS.items()
            },
        },
        "timeoutPolicy": {
            "clock": "monotonic",
            "startsAt": "dispatch",
            "cancellationGraceSeconds": grace,
            "totalDeadlineSeconds": max(timeout_values.values()) + grace,
            "timeoutIsTerminal": True,
            "retryAfterTimeout": False,
        },
        "artifactPolicy": dict(_ARTIFACT_POLICY),
        "boundaries": dict(_BOUNDARIES),
    }
    with_id = dict(core)
    with_id["planId"] = "plan_" + sha256(_canonical_json_bytes(core)).hexdigest()[:24]
    expected = dict(with_id)
    expected["planSha256"] = sha256(_canonical_json_bytes(with_id)).hexdigest()
    if plan != expected:
        raise EngineReceiverAuthorityError("receiver_authority_plan_invalid")
    return plan


@dataclass(frozen=True, slots=True)
class EngineReceiverTrustedPlan:
    job_id: str
    engine: str
    run_id: str
    orchestration_plan_id: str
    orchestration_plan_sha256: str
    canonical_plan_sha256: str
    canonical_plan_bytes: bytes = field(repr=False)
    persistence_state: str = "loaded"

    def __post_init__(self) -> None:
        if (
            _JOB_ID_RE.fullmatch(self.job_id) is None
            or self.engine != ENGINE_NAME
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or _PLAN_ID_RE.fullmatch(self.orchestration_plan_id) is None
            or _SHA256_RE.fullmatch(self.orchestration_plan_sha256) is None
            or _SHA256_RE.fullmatch(self.canonical_plan_sha256) is None
            or type(self.canonical_plan_bytes) is not bytes
            or not 1 <= len(self.canonical_plan_bytes) <= MAX_CANONICAL_PLAN_BYTES
            or self.persistence_state not in {"written", "replay", "loaded"}
        ):
            raise EngineReceiverAuthorityError("receiver_authority_result_invalid")

    @property
    def credential_export_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": ENGINE_RECEIVER_AUTHORITY_VERSION,
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "orchestrationPlanId": self.orchestration_plan_id,
            "orchestrationPlanSha256": self.orchestration_plan_sha256,
            "canonicalPlanSha256": self.canonical_plan_sha256,
            "canonicalPlanBytes": len(self.canonical_plan_bytes),
            "persistenceState": self.persistence_state,
            "credentialExportAllowed": False,
            "networkDispatchAllowed": False,
            "retryAllowed": False,
            "jobStateMutationAllowed": False,
            "engineExecutionAllowed": False,
        }


@dataclass(frozen=True, slots=True)
class EngineReceiverReplayReservation:
    engine: str
    replay_key: str
    credential_generation_id: str
    request_timestamp: int
    replay_expires_at: int
    persistence_state: str = "written"

    def __post_init__(self) -> None:
        if (
            self.engine != ENGINE_NAME
            or _SHA256_RE.fullmatch(self.replay_key) is None
            or _GENERATION_RE.fullmatch(self.credential_generation_id) is None
            or type(self.request_timestamp) is not int
            or self.request_timestamp < 0
            or type(self.replay_expires_at) is not int
            or not self.request_timestamp <= self.replay_expires_at <= self.request_timestamp + MAX_REPLAY_LIFETIME_SECONDS
            or self.persistence_state != "written"
        ):
            raise EngineReceiverAuthorityError("receiver_authority_result_invalid")

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": ENGINE_RECEIVER_AUTHORITY_VERSION,
            "engine": self.engine,
            "replayKey": self.replay_key,
            "credentialGenerationId": self.credential_generation_id,
            "requestTimestamp": self.request_timestamp,
            "replayExpiresAt": self.replay_expires_at,
            "persistenceState": self.persistence_state,
            "retryAllowed": False,
            "networkDispatchAllowed": False,
            "engineExecutionAllowed": False,
        }


class EngineReceiverAuthority:
    """Create-once engine-local durable trusted-plan and replay state."""

    __slots__ = ("_root", "_integrity_key")

    def __init__(self, *, root: str | Path, integrity_key: bytes) -> None:
        try:
            checked_root = Path(root)
        except TypeError:
            raise EngineReceiverAuthorityError("receiver_authority_config_invalid") from None
        if not checked_root.is_absolute() or type(integrity_key) is not bytes or len(integrity_key) != 32:
            raise EngineReceiverAuthorityError("receiver_authority_config_invalid")
        self._root = checked_root
        self._integrity_key = bytes(integrity_key)
        self._ensure_directory(self._root)
        self._ensure_directory(self._root / "trusted-plans")
        self._ensure_directory(self._root / "replay-reservations")

    def __repr__(self) -> str:
        return f"EngineReceiverAuthority(engine={ENGINE_NAME!r}, root={str(self._root)!r}, integrity_key=<redacted>)"

    @property
    def engine(self) -> str:
        return ENGINE_NAME

    @property
    def credential_export_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def _ensure_directory(self, path: Path) -> None:
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            observed = path.lstat()
        except OSError:
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid") from None
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")

    def _plan_path(self, job_id: str) -> Path:
        checked = _require_job_id(job_id, category="receiver_authority_plan_input_invalid")
        return self._root / "trusted-plans" / f"{checked}.json"

    def _replay_path(self, replay_key: str) -> Path:
        checked = _require_sha256(replay_key, category="receiver_authority_replay_input_invalid")
        return self._root / "replay-reservations" / f"{checked}.json"

    def _record_mac(self, domain: bytes, record: dict[str, Any]) -> str:
        if type(record) is not dict or _MAC_FIELD in record:
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        message = b"\\0".join((domain, ENGINE_NAME.encode("ascii"), _canonical_json_bytes(record)))
        return hmac_new(self._integrity_key, message, sha256).hexdigest()

    def _seal(self, domain: bytes, record: dict[str, Any]) -> bytes:
        sealed = dict(record)
        sealed[_MAC_FIELD] = self._record_mac(domain, record)
        payload = _canonical_json_bytes(sealed)
        if len(payload) > MAX_STATE_RECORD_BYTES:
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        return payload

    def _verify_sealed(self, domain: bytes, raw: bytes) -> dict[str, Any]:
        sealed = _decode_canonical_json(raw, max_bytes=MAX_STATE_RECORD_BYTES)
        observed = sealed.get(_MAC_FIELD)
        if type(observed) is not str or _SHA256_RE.fullmatch(observed) is None:
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        record = dict(sealed)
        del record[_MAC_FIELD]
        if not compare_digest(observed, self._record_mac(domain, record)):
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        return record

    def _assert_regular_existing(self, path: Path) -> None:
        try:
            observed = path.lstat()
        except OSError:
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid") from None
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")

    def _atomic_create(self, path: Path, payload: bytes) -> bool:
        """Publish one complete immutable record without exposing partial bytes."""

        temp_path = path.parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd: int | None = None
        try:
            fd = os.open(temp_path, flags, 0o600)
            with os.fdopen(fd, "wb", closefd=True) as handle:
                fd = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, 0o400, follow_symlinks=False)
            try:
                os.link(temp_path, path, follow_symlinks=False)
                created = True
            except FileExistsError:
                self._assert_regular_existing(path)
                created = False
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            return created
        except EngineReceiverAuthorityError:
            raise
        except OSError as exc:
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid") from None
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _read_no_follow(self, path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except OSError:
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid") from None
        try:
            observed = os.fstat(fd)
            if not stat.S_ISREG(observed.st_mode) or observed.st_size > MAX_STATE_RECORD_BYTES:
                raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, min(65536, MAX_STATE_RECORD_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_STATE_RECORD_BYTES:
                    raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
            return b"".join(chunks)
        finally:
            os.close(fd)

    def _trusted_plan_from_record(self, record: dict[str, Any], *, persistence_state: str) -> EngineReceiverTrustedPlan:
        expected_keys = {
            "version", "engine", "job_id", "run_id", "orchestration_plan_id",
            "orchestration_plan_sha256", "canonical_plan_sha256", "canonical_plan_b64",
        }
        if set(record) != expected_keys or record.get("version") != ENGINE_RECEIVER_AUTHORITY_VERSION or record.get("engine") != ENGINE_NAME:
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        job_id = _require_job_id(record.get("job_id"), category="receiver_authority_state_invalid")
        run_id = record.get("run_id")
        plan_id = record.get("orchestration_plan_id")
        plan_sha = record.get("orchestration_plan_sha256")
        canonical_sha = record.get("canonical_plan_sha256")
        encoded = record.get("canonical_plan_b64")
        if (
            type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None
            or type(plan_id) is not str or _PLAN_ID_RE.fullmatch(plan_id) is None
            or type(plan_sha) is not str or _SHA256_RE.fullmatch(plan_sha) is None
            or type(canonical_sha) is not str or _SHA256_RE.fullmatch(canonical_sha) is None
            or type(encoded) is not str
        ):
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        try:
            canonical = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError):
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid") from None
        plan = _validate_trusted_plan(canonical, expected_job_id=job_id)
        engine_runs = plan["engineRuns"]
        matching_run = next(run for run in engine_runs if run["engine"] == ENGINE_NAME)
        if (
            matching_run["runId"] != run_id
            or plan["planId"] != plan_id
            or plan["planSha256"] != plan_sha
            or sha256(canonical).hexdigest() != canonical_sha
        ):
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        return EngineReceiverTrustedPlan(
            job_id=job_id,
            engine=ENGINE_NAME,
            run_id=run_id,
            orchestration_plan_id=plan_id,
            orchestration_plan_sha256=plan_sha,
            canonical_plan_sha256=canonical_sha,
            canonical_plan_bytes=canonical,
            persistence_state=persistence_state,
        )

    def register_trusted_plan(self, *, job_id: str, canonical_plan_bytes: bytes) -> EngineReceiverTrustedPlan:
        checked_job = _require_job_id(job_id, category="receiver_authority_plan_input_invalid")
        if type(canonical_plan_bytes) is not bytes:
            raise EngineReceiverAuthorityError("receiver_authority_plan_input_invalid")
        plan = _validate_trusted_plan(canonical_plan_bytes, expected_job_id=checked_job)
        run = next(run for run in plan["engineRuns"] if run["engine"] == ENGINE_NAME)
        record = {
            "version": ENGINE_RECEIVER_AUTHORITY_VERSION,
            "engine": ENGINE_NAME,
            "job_id": checked_job,
            "run_id": run["runId"],
            "orchestration_plan_id": plan["planId"],
            "orchestration_plan_sha256": plan["planSha256"],
            "canonical_plan_sha256": sha256(canonical_plan_bytes).hexdigest(),
            "canonical_plan_b64": base64.b64encode(canonical_plan_bytes).decode("ascii"),
        }
        path = self._plan_path(checked_job)
        payload = self._seal(_PLAN_MAC_DOMAIN, record)
        if self._atomic_create(path, payload):
            return self._trusted_plan_from_record(record, persistence_state="written")
        stored = self._trusted_plan_from_record(
            self._verify_sealed(_PLAN_MAC_DOMAIN, self._read_no_follow(path)),
            persistence_state="replay",
        )
        if not compare_digest(stored.canonical_plan_sha256, record["canonical_plan_sha256"]):
            raise EngineReceiverAuthorityError("receiver_authority_plan_conflict")
        return stored

    def load_trusted_plan(self, *, job_id: str) -> EngineReceiverTrustedPlan:
        path = self._plan_path(job_id)
        try:
            raw = self._read_no_follow(path)
        except EngineReceiverAuthorityError:
            raise EngineReceiverAuthorityError("receiver_authority_plan_not_found_or_invalid") from None
        try:
            record = self._verify_sealed(_PLAN_MAC_DOMAIN, raw)
            return self._trusted_plan_from_record(record, persistence_state="loaded")
        except EngineReceiverAuthorityError:
            raise EngineReceiverAuthorityError("receiver_authority_plan_not_found_or_invalid") from None

    def _replay_from_record(self, record: dict[str, Any]) -> EngineReceiverReplayReservation:
        expected_keys = {
            "version", "engine", "replay_key", "credential_generation_id",
            "request_timestamp", "replay_expires_at",
        }
        if (
            set(record) != expected_keys
            or record.get("version") != ENGINE_RECEIVER_AUTHORITY_VERSION
            or record.get("engine") != ENGINE_NAME
        ):
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        replay_key = _require_sha256(
            record.get("replay_key"), category="receiver_authority_state_invalid"
        )
        generation = record.get("credential_generation_id")
        request_timestamp = record.get("request_timestamp")
        replay_expires_at = record.get("replay_expires_at")
        if (
            type(generation) is not str
            or _GENERATION_RE.fullmatch(generation) is None
            or type(request_timestamp) is not int
            or request_timestamp < 0
            or type(replay_expires_at) is not int
            or not request_timestamp <= replay_expires_at <= request_timestamp + MAX_REPLAY_LIFETIME_SECONDS
        ):
            raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
        return EngineReceiverReplayReservation(
            engine=ENGINE_NAME,
            replay_key=replay_key,
            credential_generation_id=generation,
            request_timestamp=request_timestamp,
            replay_expires_at=replay_expires_at,
        )

    def reserve_replay(
        self,
        *,
        replay_key: str,
        credential_generation_id: str,
        request_timestamp: int,
        replay_expires_at: int,
    ) -> EngineReceiverReplayReservation:
        checked_key = _require_sha256(replay_key, category="receiver_authority_replay_input_invalid")
        checked_generation = _require_generation(credential_generation_id)
        if (
            type(request_timestamp) is not int
            or request_timestamp < 0
            or type(replay_expires_at) is not int
            or not request_timestamp <= replay_expires_at <= request_timestamp + MAX_REPLAY_LIFETIME_SECONDS
        ):
            raise EngineReceiverAuthorityError("receiver_authority_replay_input_invalid")
        record = {
            "version": ENGINE_RECEIVER_AUTHORITY_VERSION,
            "engine": ENGINE_NAME,
            "replay_key": checked_key,
            "credential_generation_id": checked_generation,
            "request_timestamp": request_timestamp,
            "replay_expires_at": replay_expires_at,
        }
        path = self._replay_path(checked_key)
        if not self._atomic_create(path, self._seal(_REPLAY_MAC_DOMAIN, record)):
            existing = self._replay_from_record(
                self._verify_sealed(_REPLAY_MAC_DOMAIN, self._read_no_follow(path))
            )
            if not compare_digest(existing.replay_key, checked_key):
                raise EngineReceiverAuthorityError("receiver_authority_state_invalid")
            raise EngineReceiverAuthorityError("receiver_authority_replay_detected")
        return EngineReceiverReplayReservation(
            engine=ENGINE_NAME,
            replay_key=checked_key,
            credential_generation_id=checked_generation,
            request_timestamp=request_timestamp,
            replay_expires_at=replay_expires_at,
        )
