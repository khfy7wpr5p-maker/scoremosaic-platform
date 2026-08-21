"""Stage 5-B2 controlled one-shot engine execution core.

Execution is allowed only after Stage 5-B1 converges an engine-owned trusted
plan, durable authenticated dispatch receipt, and immutable source. A durable
engine-local execution claim is published before any workspace or process side
effect. Existing claims always require manual reconciliation and never trigger
an automatic re-execution.

This module grants no HTTP route, network retry, Gateway state mutation, result
persistence, publication, source conversion, or production activation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Callable

from .config import ServiceConfig
from .dispatch_acceptance import EngineDispatchAcceptanceStore
from .engine_execution_capability import (
    EngineExecutionCapabilityError,
    EngineExecutionEligibility,
    evaluate_engine_execution_eligibility,
)
from .receiver_authority import ENGINE_NAME, EngineReceiverAuthority
from .runtime import RuntimeExecutionError, TranscriptionResult, transcribe_file
from .source_delivery import EngineSourceStore, SourceDeliveryReceiverError

CONTROLLED_ENGINE_EXECUTION_VERSION = "scoremosaic-controlled-engine-execution-v1"
ENGINE_EXECUTION_CLAIM_VERSION = "scoremosaic-engine-execution-claim-v1"
MAX_EXECUTION_CLAIM_BYTES = 32 * 1024
MAX_EXECUTION_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_EXECUTION_OUTPUTS = 16
_CLAIM_MAC_DOMAIN = b"scoremosaic-engine-execution-claim-v1"
_CLAIM_MAC_FIELD = "integrityMac"
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_CANDIDATE_ID_RE = re.compile(r"candidate_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_NAMESPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,499}\Z")


class ControlledEngineExecutionError(RuntimeError):
    """Stable fail-closed Stage 5-B2 failure category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise ControlledEngineExecutionError("engine_execution_claim_state_invalid") from None


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
        result[key] = value
    return result


def _decode_canonical(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_EXECUTION_CLAIM_BYTES:
        raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
    try:
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except ControlledEngineExecutionError:
        raise
    except Exception:
        raise ControlledEngineExecutionError("engine_execution_claim_state_invalid") from None
    if type(value) is not dict or _canonical_json(value) != raw:
        raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
    return value


def _claim_key(eligibility: EngineExecutionEligibility) -> str:
    material = "\x1f".join(
        (
            ENGINE_EXECUTION_CLAIM_VERSION,
            eligibility.engine,
            eligibility.job_id,
            eligibility.run_id,
            eligibility.dispatch_identity_sha256,
            eligibility.source_artifact_id,
            eligibility.source_sha256,
            eligibility.source_media_type,
            eligibility.candidate_id,
            eligibility.candidate_namespace,
            str(eligibility.timeout_seconds),
        )
    ).encode("utf-8")
    return sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class EngineExecutionClaim:
    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    source_artifact_id: str
    source_sha256: str
    source_media_type: str
    candidate_id: str
    candidate_namespace: str
    timeout_seconds: int
    claim_key: str
    persistence_state: str

    def __post_init__(self) -> None:
        if (
            self.engine != ENGINE_NAME
            or type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.run_id) is not str
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or type(self.dispatch_identity_sha256) is not str
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or type(self.source_artifact_id) is not str
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.source_sha256) is not str
            or _SHA256_RE.fullmatch(self.source_sha256) is None
            or type(self.source_media_type) is not str
            or type(self.candidate_id) is not str
            or _CANDIDATE_ID_RE.fullmatch(self.candidate_id) is None
            or type(self.candidate_namespace) is not str
            or _SAFE_NAMESPACE_RE.fullmatch(self.candidate_namespace) is None
            or type(self.timeout_seconds) is not int
            or not 30 <= self.timeout_seconds <= 7200
            or type(self.claim_key) is not str
            or _SHA256_RE.fullmatch(self.claim_key) is None
            or self.persistence_state not in {"written", "loaded"}
        ):
            raise ControlledEngineExecutionError("engine_execution_claim_result_invalid")

    @property
    def automatic_retry_allowed(self) -> bool:
        return False

    @property
    def restart_reexecution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": ENGINE_EXECUTION_CLAIM_VERSION,
            "environment": "staging",
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "sourceMediaType": self.source_media_type,
            "candidateId": self.candidate_id,
            "candidateNamespace": self.candidate_namespace,
            "timeoutSeconds": self.timeout_seconds,
            "claimKey": self.claim_key,
            "persistenceState": self.persistence_state,
            "automaticRetryAllowed": False,
            "restartReexecutionAllowed": False,
        }


class EngineExecutionClaimStore:
    """Create-once HMAC-sealed execution claim store."""

    __slots__ = ("_root", "_integrity_key")

    def __init__(self, *, root: str | Path, integrity_key: bytes) -> None:
        try:
            checked = Path(root)
        except TypeError:
            raise ControlledEngineExecutionError("engine_execution_claim_config_invalid") from None
        if (
            not checked.is_absolute()
            or checked == Path("/")
            or type(integrity_key) is not bytes
            or len(integrity_key) != 32
        ):
            raise ControlledEngineExecutionError("engine_execution_claim_config_invalid")
        self._root = checked
        self._integrity_key = bytes(integrity_key)
        self._ensure_dir(self._root)
        self._ensure_dir(self._root / "execution-claims")

    def __repr__(self) -> str:
        return (
            f"EngineExecutionClaimStore(engine={ENGINE_NAME!r}, root={str(self._root)!r}, "
            "integrity_key=<redacted>)"
        )

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            observed = path.lstat()
        except OSError:
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid") from None
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")

    @staticmethod
    def _read_flags() -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        return flags

    def _path(self, eligibility: EngineExecutionEligibility) -> Path:
        if type(eligibility) is not EngineExecutionEligibility:
            raise ControlledEngineExecutionError("engine_execution_claim_input_invalid")
        return (
            self._root
            / "execution-claims"
            / f"{eligibility.job_id}.{eligibility.run_id}.json"
        )

    def _record(self, eligibility: EngineExecutionEligibility) -> dict[str, Any]:
        key = _claim_key(eligibility)
        return {
            "version": ENGINE_EXECUTION_CLAIM_VERSION,
            "environment": "staging",
            "engine": eligibility.engine,
            "jobId": eligibility.job_id,
            "runId": eligibility.run_id,
            "dispatchIdentitySha256": eligibility.dispatch_identity_sha256,
            "sourceArtifactId": eligibility.source_artifact_id,
            "sourceSha256": eligibility.source_sha256,
            "sourceMediaType": eligibility.source_media_type,
            "candidateId": eligibility.candidate_id,
            "candidateNamespace": eligibility.candidate_namespace,
            "timeoutSeconds": eligibility.timeout_seconds,
            "claimKey": key,
        }

    def _mac(self, record: dict[str, Any]) -> str:
        if type(record) is not dict or _CLAIM_MAC_FIELD in record:
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
        return hmac_new(
            self._integrity_key,
            b"\0".join(
                (
                    _CLAIM_MAC_DOMAIN,
                    ENGINE_NAME.encode("ascii"),
                    _canonical_json(record),
                )
            ),
            sha256,
        ).hexdigest()

    def _seal(self, record: dict[str, Any]) -> bytes:
        sealed = dict(record)
        sealed[_CLAIM_MAC_FIELD] = self._mac(record)
        payload = _canonical_json(sealed)
        if len(payload) > MAX_EXECUTION_CLAIM_BYTES:
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
        return payload

    def _read(self, path: Path) -> dict[str, Any]:
        fd: int | None = None
        try:
            fd = os.open(path, self._read_flags())
            observed = os.fstat(fd)
            if (
                not stat.S_ISREG(observed.st_mode)
                or not 1 <= observed.st_size <= MAX_EXECUTION_CLAIM_BYTES
            ):
                raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(
                    fd,
                    min(4096, MAX_EXECUTION_CLAIM_BYTES + 1 - total),
                )
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_EXECUTION_CLAIM_BYTES:
                    raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
                chunks.append(chunk)
            raw = b"".join(chunks)
        except ControlledEngineExecutionError:
            raise
        except OSError:
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid") from None
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    raise ControlledEngineExecutionError("engine_execution_claim_state_invalid") from None
        sealed = _decode_canonical(raw)
        if _CLAIM_MAC_FIELD not in sealed:
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
        observed_mac = sealed.pop(_CLAIM_MAC_FIELD)
        if (
            type(observed_mac) is not str
            or _SHA256_RE.fullmatch(observed_mac) is None
            or not compare_digest(observed_mac, self._mac(sealed))
        ):
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
        return sealed

    def _to_claim(self, record: dict[str, Any], *, state: str) -> EngineExecutionClaim:
        expected = {
            "version",
            "environment",
            "engine",
            "jobId",
            "runId",
            "dispatchIdentitySha256",
            "sourceArtifactId",
            "sourceSha256",
            "sourceMediaType",
            "candidateId",
            "candidateNamespace",
            "timeoutSeconds",
            "claimKey",
        }
        if (
            set(record) != expected
            or record.get("version") != ENGINE_EXECUTION_CLAIM_VERSION
            or record.get("environment") != "staging"
            or record.get("engine") != ENGINE_NAME
        ):
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid")
        return EngineExecutionClaim(
            engine=record.get("engine"),
            job_id=record.get("jobId"),
            run_id=record.get("runId"),
            dispatch_identity_sha256=record.get("dispatchIdentitySha256"),
            source_artifact_id=record.get("sourceArtifactId"),
            source_sha256=record.get("sourceSha256"),
            source_media_type=record.get("sourceMediaType"),
            candidate_id=record.get("candidateId"),
            candidate_namespace=record.get("candidateNamespace"),
            timeout_seconds=record.get("timeoutSeconds"),
            claim_key=record.get("claimKey"),
            persistence_state=state,
        )

    def reserve(self, eligibility: EngineExecutionEligibility) -> EngineExecutionClaim:
        """Publish once; every pre-existing exact claim requires reconciliation."""

        if type(eligibility) is not EngineExecutionEligibility:
            raise ControlledEngineExecutionError("engine_execution_claim_input_invalid")
        record = self._record(eligibility)
        payload = self._seal(record)
        path = self._path(eligibility)
        temp = path.parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        fd: int | None = None
        created = False
        try:
            fd = os.open(temp, flags, 0o600)
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise OSError("execution_claim_write_failed")
                offset += written
            os.fchmod(fd, 0o400)
            os.fsync(fd)
            os.close(fd)
            fd = None
            try:
                os.link(temp, path, follow_symlinks=False)
                created = True
            except FileExistsError:
                created = False
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except ControlledEngineExecutionError:
            raise
        except OSError:
            raise ControlledEngineExecutionError("engine_execution_claim_state_invalid") from None
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

        stored_record = self._read(path)
        stored = self._to_claim(
            stored_record,
            state="written" if created else "loaded",
        )
        expected = self._to_claim(record, state="written")
        if (
            stored.engine != expected.engine
            or stored.job_id != expected.job_id
            or stored.run_id != expected.run_id
            or not compare_digest(
                stored.dispatch_identity_sha256,
                expected.dispatch_identity_sha256,
            )
            or stored.source_artifact_id != expected.source_artifact_id
            or not compare_digest(stored.source_sha256, expected.source_sha256)
            or stored.source_media_type != expected.source_media_type
            or stored.candidate_id != expected.candidate_id
            or stored.candidate_namespace != expected.candidate_namespace
            or stored.timeout_seconds != expected.timeout_seconds
            or not compare_digest(stored.claim_key, expected.claim_key)
        ):
            raise ControlledEngineExecutionError("engine_execution_claim_conflict")
        if not created:
            raise ControlledEngineExecutionError("engine_execution_reconciliation_required")
        return stored


@dataclass(frozen=True, slots=True, repr=False)
class EngineExecutionArtifactHandoff:
    path: Path = field(repr=False)
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, Path)
            or type(self.size_bytes) is not int
            or not 1 <= self.size_bytes <= MAX_EXECUTION_OUTPUT_BYTES
            or type(self.sha256) is not str
            or _SHA256_RE.fullmatch(self.sha256) is None
        ):
            raise ControlledEngineExecutionError("engine_execution_artifact_invalid")

    def __repr__(self) -> str:
        return (
            "EngineExecutionArtifactHandoff("
            f"size_bytes={self.size_bytes!r}, sha256={self.sha256!r}, path=<redacted>)"
        )

    def as_safe_dict(self) -> dict[str, object]:
        return {"sizeBytes": self.size_bytes, "sha256": self.sha256}


@dataclass(frozen=True, slots=True, repr=False)
class ControlledEngineExecutionResult:
    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    source_artifact_id: str
    source_sha256: str
    source_media_type: str
    candidate_id: str
    claim_key: str
    artifacts: tuple[EngineExecutionArtifactHandoff, ...] = field(repr=False)
    execution_attempt_count: int = 1

    def __post_init__(self) -> None:
        if (
            self.engine != ENGINE_NAME
            or type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.run_id) is not str
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or type(self.dispatch_identity_sha256) is not str
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or type(self.source_artifact_id) is not str
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.source_sha256) is not str
            or _SHA256_RE.fullmatch(self.source_sha256) is None
            or type(self.source_media_type) is not str
            or type(self.candidate_id) is not str
            or _CANDIDATE_ID_RE.fullmatch(self.candidate_id) is None
            or type(self.claim_key) is not str
            or _SHA256_RE.fullmatch(self.claim_key) is None
            or type(self.artifacts) is not tuple
            or not 1 <= len(self.artifacts) <= MAX_EXECUTION_OUTPUTS
            or any(type(item) is not EngineExecutionArtifactHandoff for item in self.artifacts)
            or self.execution_attempt_count != 1
        ):
            raise ControlledEngineExecutionError("engine_execution_result_invalid")

    def __repr__(self) -> str:
        return (
            "ControlledEngineExecutionResult("
            f"engine={self.engine!r}, job_id={self.job_id!r}, run_id={self.run_id!r}, "
            f"source_sha256={self.source_sha256!r}, candidate_id={self.candidate_id!r}, "
            f"claim_key={self.claim_key!r}, artifacts=<redacted>)"
        )

    @property
    def engine_execution_performed(self) -> bool:
        return True

    @property
    def automatic_retry_allowed(self) -> bool:
        return False

    @property
    def restart_reexecution_allowed(self) -> bool:
        return False

    @property
    def result_return_allowed(self) -> bool:
        return False

    @property
    def result_persistence_allowed(self) -> bool:
        return False

    @property
    def gateway_state_mutation_allowed(self) -> bool:
        return False

    @property
    def reconciliation_required_on_restart(self) -> bool:
        return True

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_ENGINE_EXECUTION_VERSION,
            "environment": "staging",
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "sourceMediaType": self.source_media_type,
            "candidateId": self.candidate_id,
            "claimKey": self.claim_key,
            "outputCount": len(self.artifacts),
            "outputs": [item.as_safe_dict() for item in self.artifacts],
            "executionAttemptCount": 1,
            "engineExecutionPerformed": True,
            "automaticRetryAllowed": False,
            "restartReexecutionAllowed": False,
            "resultReturnAllowed": False,
            "resultPersistenceAllowed": False,
            "gatewayStateMutationAllowed": False,
            "reconciliationRequiredOnRestart": True,
        }


Transcriber = Callable[[Path, Path, ServiceConfig], TranscriptionResult]


def _ensure_execution_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        observed = path.lstat()
    except OSError:
        raise ControlledEngineExecutionError("engine_execution_workspace_invalid") from None
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise ControlledEngineExecutionError("engine_execution_workspace_invalid")


def _stage_source(
    *,
    config: ServiceConfig,
    eligibility: EngineExecutionEligibility,
    source_bytes: bytes,
) -> tuple[Path, Path]:
    root = config.workspace_root
    if not root.is_absolute() or root == Path("/"):
        raise ControlledEngineExecutionError("engine_execution_workspace_invalid")
    _ensure_execution_directory(root)
    executions = root / "stage5-executions"
    _ensure_execution_directory(executions)
    run_dir = executions / f"{eligibility.job_id}.{eligibility.run_id}"
    try:
        run_dir.mkdir(mode=0o700)
        observed = run_dir.lstat()
    except FileExistsError:
        raise ControlledEngineExecutionError("engine_execution_workspace_conflict") from None
    except OSError:
        raise ControlledEngineExecutionError("engine_execution_workspace_invalid") from None
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise ControlledEngineExecutionError("engine_execution_workspace_invalid")

    input_path = run_dir / f"source{eligibility.runtime_input_suffix}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd: int | None = None
    try:
        fd = os.open(input_path, flags, 0o400)
        view = memoryview(source_bytes)
        offset = 0
        while offset < len(view):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise OSError("engine_execution_source_write_failed")
            offset += written
        os.fchmod(fd, 0o400)
        os.fsync(fd)
        observed_file = os.fstat(fd)
        if not stat.S_ISREG(observed_file.st_mode) or observed_file.st_size != len(source_bytes):
            raise ControlledEngineExecutionError("engine_execution_source_stage_invalid")
    except ControlledEngineExecutionError:
        raise
    except OSError:
        raise ControlledEngineExecutionError("engine_execution_source_stage_invalid") from None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                raise ControlledEngineExecutionError("engine_execution_source_stage_invalid") from None
    dir_fd = None
    try:
        dir_fd = os.open(run_dir, os.O_RDONLY)
        os.fsync(dir_fd)
    except OSError:
        raise ControlledEngineExecutionError("engine_execution_source_stage_invalid") from None
    finally:
        if dir_fd is not None:
            os.close(dir_fd)
    if sha256(source_bytes).hexdigest() != eligibility.source_sha256:
        raise ControlledEngineExecutionError("engine_execution_source_stage_invalid")
    return run_dir, input_path


def _read_output_handoff(path: Path, run_dir: Path) -> EngineExecutionArtifactHandoff:
    if not isinstance(path, Path) or path.is_symlink():
        raise ControlledEngineExecutionError("engine_execution_output_invalid")
    try:
        resolved_run = run_dir.resolve(strict=True)
        resolved = path.resolve(strict=True)
    except OSError:
        raise ControlledEngineExecutionError("engine_execution_output_invalid") from None
    if not resolved.is_relative_to(resolved_run):
        raise ControlledEngineExecutionError("engine_execution_output_invalid")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd: int | None = None
    digest = sha256()
    total = 0
    try:
        fd = os.open(resolved, flags)
        observed = os.fstat(fd)
        if not stat.S_ISREG(observed.st_mode) or not 1 <= observed.st_size <= MAX_EXECUTION_OUTPUT_BYTES:
            raise ControlledEngineExecutionError("engine_execution_output_invalid")
        while True:
            chunk = os.read(fd, min(65536, MAX_EXECUTION_OUTPUT_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_EXECUTION_OUTPUT_BYTES:
                raise ControlledEngineExecutionError("engine_execution_output_invalid")
            digest.update(chunk)
    except ControlledEngineExecutionError:
        raise
    except OSError:
        raise ControlledEngineExecutionError("engine_execution_output_invalid") from None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                raise ControlledEngineExecutionError("engine_execution_output_invalid") from None
    return EngineExecutionArtifactHandoff(
        path=resolved,
        size_bytes=total,
        sha256=digest.hexdigest(),
    )


def execute_controlled_engine_once(
    *,
    authority: EngineReceiverAuthority,
    dispatch_acceptance_store: EngineDispatchAcceptanceStore,
    source_store: EngineSourceStore,
    claim_store: EngineExecutionClaimStore,
    config: ServiceConfig,
    job_id: str,
    run_id: str,
    dispatch_identity_sha256: str,
    transcriber: Transcriber = transcribe_file,
) -> ControlledEngineExecutionResult:
    """Execute exactly one engine attempt after all durable prerequisites converge."""

    if (
        type(claim_store) is not EngineExecutionClaimStore
        or type(config) is not ServiceConfig
        or not callable(transcriber)
    ):
        raise ControlledEngineExecutionError("engine_execution_input_invalid")
    try:
        eligibility = evaluate_engine_execution_eligibility(
            authority=authority,
            dispatch_acceptance_store=dispatch_acceptance_store,
            source_store=source_store,
            job_id=job_id,
            run_id=run_id,
            dispatch_identity_sha256=dispatch_identity_sha256,
        )
    except EngineExecutionCapabilityError as exc:
        if exc.category == "engine_execution_media_type_unsupported":
            raise ControlledEngineExecutionError("engine_execution_media_type_unsupported") from None
        raise ControlledEngineExecutionError("engine_execution_prerequisite_invalid") from None

    if (
        type(config.request_timeout_seconds) is not int
        or config.request_timeout_seconds < 1
        or config.request_timeout_seconds > eligibility.timeout_seconds
    ):
        raise ControlledEngineExecutionError("engine_execution_timeout_policy_invalid")

    try:
        stored = source_store.load(job_id=job_id, run_id=run_id)
    except SourceDeliveryReceiverError:
        raise ControlledEngineExecutionError("engine_execution_source_unavailable") from None
    if (
        stored.engine != eligibility.engine
        or stored.job_id != eligibility.job_id
        or stored.run_id != eligibility.run_id
        or stored.dispatch_identity_sha256 != eligibility.dispatch_identity_sha256
        or stored.source_artifact_id != eligibility.source_artifact_id
        or stored.source_sha256 != eligibility.source_sha256
        or stored.source_media_type != eligibility.source_media_type
        or len(stored.source_bytes) != eligibility.source_size_bytes
        or not compare_digest(sha256(stored.source_bytes).hexdigest(), eligibility.source_sha256)
    ):
        raise ControlledEngineExecutionError("engine_execution_source_mismatch")

    claim = claim_store.reserve(eligibility)
    run_dir, input_path = _stage_source(
        config=config,
        eligibility=eligibility,
        source_bytes=stored.source_bytes,
    )

    try:
        runtime_result = transcriber(input_path, run_dir, config)
    except RuntimeExecutionError:
        raise ControlledEngineExecutionError("engine_execution_runtime_failed") from None
    except Exception:
        raise ControlledEngineExecutionError("engine_execution_runtime_failed") from None
    if type(runtime_result) is not TranscriptionResult or runtime_result.return_code != 0:
        raise ControlledEngineExecutionError("engine_execution_runtime_result_invalid")
    paths = runtime_result.musicxml_artifacts
    if (
        type(paths) is not tuple
        or not 1 <= len(paths) <= MAX_EXECUTION_OUTPUTS
    ):
        raise ControlledEngineExecutionError("engine_execution_runtime_result_invalid")
    artifacts = tuple(_read_output_handoff(path, run_dir) for path in paths)

    return ControlledEngineExecutionResult(
        engine=eligibility.engine,
        job_id=eligibility.job_id,
        run_id=eligibility.run_id,
        dispatch_identity_sha256=eligibility.dispatch_identity_sha256,
        source_artifact_id=eligibility.source_artifact_id,
        source_sha256=eligibility.source_sha256,
        source_media_type=eligibility.source_media_type,
        candidate_id=eligibility.candidate_id,
        claim_key=claim.claim_key,
        artifacts=artifacts,
    )
