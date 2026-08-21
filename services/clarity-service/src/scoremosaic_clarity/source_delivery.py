"""Engine-owned authenticated source intake for Stage 5-A1.

This boundary accepts one exact immutable source body only after it converges with
an engine-owned trusted orchestration plan and a purpose-separated staging
credential.  It persists source bytes create-once in an engine-local store.
It grants no HTTP route, engine execution, retry, result persistence, Gateway
state mutation, or production activation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import errno
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
from typing import Any, Callable, Sequence

from .receiver_authority import (
    ENGINE_NAME,
    EngineReceiverAuthority,
    EngineReceiverAuthorityError,
)

SOURCE_DELIVERY_VERSION = "scoremosaic-source-delivery-v1"
SOURCE_DELIVERY_ALGORITHM = "hmac-sha256"
SOURCE_DELIVERY_METHOD = "POST"
SOURCE_DELIVERY_PATH = "/internal/source"
SOURCE_DELIVERY_ENVIRONMENT = "staging"
SOURCE_DELIVERY_MAX_AGE_SECONDS = 60
SOURCE_DELIVERY_MAX_FUTURE_SKEW_SECONDS = 30
SOURCE_DELIVERY_MAX_BYTES = 100 * 1024 * 1024
SOURCE_DELIVERY_MAX_ROTATION_GRACE_SECONDS = 300
SOURCE_STORE_VERSION = "scoremosaic-engine-source-store-v1"
_SOURCE_SIGNATURE_DOMAIN = b"scoremosaic-source-delivery-signature-v1"
_SOURCE_STORE_MAC_DOMAIN = b"scoremosaic-engine-source-store-metadata-v1"

CALLER_SERVICE_IDENTITY = "scoremosaic-omr-gateway"
_ENGINE_CONFIG = {
    "audiveris": (
        "scoremosaic-audiveris-foundation",
        "http://audiveris-foundation:8082",
    ),
    "homr": (
        "scoremosaic-homr-foundation",
        "http://homr-foundation:8080",
    ),
    "clarity": (
        "scoremosaic-clarity-foundation",
        "http://clarity-foundation:8081",
    ),
}
if ENGINE_NAME not in _ENGINE_CONFIG:
    raise RuntimeError("source delivery imported outside an engine package")
AUDIENCE_IDENTITY, ENGINE_ORIGIN = _ENGINE_CONFIG[ENGINE_NAME]

SOURCE_DELIVERY_HEADER_NAMES = (
    "x-scoremosaic-source-generation",
    "x-scoremosaic-source-timestamp",
    "x-scoremosaic-source-nonce",
    "x-scoremosaic-source-job",
    "x-scoremosaic-source-run",
    "x-scoremosaic-source-dispatch-sha256",
    "x-scoremosaic-source-artifact",
    "x-scoremosaic-source-bytes",
    "x-scoremosaic-source-sha256",
    "x-scoremosaic-source-media-type",
    "x-scoremosaic-source-signature",
)

_GENERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_ALLOWED_MEDIA_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})
_MIN_CREDENTIAL_BYTES = 32
_MAX_CREDENTIAL_BYTES = 512


class SourceDeliveryReceiverError(ValueError):
    """Stable fail-closed engine source-delivery category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class SourceDeliveryRotation:
    current_generation_id: str
    current_activated_at: int
    previous_generation_id: str | None = None
    previous_valid_until: int | None = None

    def __post_init__(self) -> None:
        if (
            type(self.current_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.current_generation_id) is None
            or type(self.current_activated_at) is not int
            or self.current_activated_at < 0
        ):
            raise SourceDeliveryReceiverError("source_delivery_rotation_invalid")
        if self.previous_generation_id is None:
            if self.previous_valid_until is not None:
                raise SourceDeliveryReceiverError("source_delivery_rotation_invalid")
            return
        if (
            type(self.previous_generation_id) is not str
            or _GENERATION_RE.fullmatch(self.previous_generation_id) is None
            or self.previous_generation_id == self.current_generation_id
            or type(self.previous_valid_until) is not int
            or self.previous_valid_until <= self.current_activated_at
            or self.previous_valid_until - self.current_activated_at
            > SOURCE_DELIVERY_MAX_ROTATION_GRACE_SECONDS
        ):
            raise SourceDeliveryReceiverError("source_delivery_rotation_invalid")


@dataclass(frozen=True, slots=True, repr=False)
class EngineStoredSource:
    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    source_artifact_id: str
    source_size_bytes: int
    source_sha256: str
    source_media_type: str
    persistence_state: str
    source_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.engine != ENGINE_NAME
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.source_size_bytes) is not int
            or not 1 <= self.source_size_bytes <= SOURCE_DELIVERY_MAX_BYTES
            or _SHA256_RE.fullmatch(self.source_sha256) is None
            or self.source_media_type not in _ALLOWED_MEDIA_TYPES
            or self.persistence_state not in {"written", "replay", "loaded"}
            or type(self.source_bytes) is not bytes
            or len(self.source_bytes) != self.source_size_bytes
            or not compare_digest(sha256(self.source_bytes).hexdigest(), self.source_sha256)
        ):
            raise SourceDeliveryReceiverError("source_store_result_invalid")

    def __repr__(self) -> str:
        return (
            "EngineStoredSource("
            f"engine={self.engine!r}, job_id={self.job_id!r}, run_id={self.run_id!r}, "
            f"source_size_bytes={self.source_size_bytes!r}, source_sha256={self.source_sha256!r}, "
            f"persistence_state={self.persistence_state!r}, source_bytes=<redacted>)"
        )

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def gateway_state_mutation_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": SOURCE_STORE_VERSION,
            "environment": SOURCE_DELIVERY_ENVIRONMENT,
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSizeBytes": self.source_size_bytes,
            "sourceSha256": self.source_sha256,
            "sourceMediaType": self.source_media_type,
            "persistenceState": self.persistence_state,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
            "gatewayStateMutationAllowed": False,
        }


class EngineSourceStore:
    """Create-once engine-local source store with HMAC-sealed metadata."""

    __slots__ = ("_root", "_integrity_key")

    def __init__(self, *, root: str | Path, integrity_key: bytes) -> None:
        try:
            checked = Path(root)
        except TypeError:
            raise SourceDeliveryReceiverError("source_store_config_invalid") from None
        if not checked.is_absolute() or type(integrity_key) is not bytes or len(integrity_key) != 32:
            raise SourceDeliveryReceiverError("source_store_config_invalid")
        self._root = checked
        self._integrity_key = bytes(integrity_key)
        self._ensure_dir(self._root)
        self._ensure_dir(self._root / "sources")

    def __repr__(self) -> str:
        return (
            f"EngineSourceStore(engine={ENGINE_NAME!r}, root={str(self._root)!r}, "
            "integrity_key=<redacted>)"
        )

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            observed = path.lstat()
        except OSError:
            raise SourceDeliveryReceiverError("source_store_state_invalid") from None
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise SourceDeliveryReceiverError("source_store_state_invalid")

    def _job_dir(self, job_id: str, run_id: str) -> Path:
        if (
            type(job_id) is not str
            or _JOB_ID_RE.fullmatch(job_id) is None
            or type(run_id) is not str
            or _RUN_ID_RE.fullmatch(run_id) is None
        ):
            raise SourceDeliveryReceiverError("source_store_input_invalid")
        return self._root / "sources" / f"{job_id}.{run_id}"

    def _metadata_mac(self, record: dict[str, Any]) -> str:
        payload = json.dumps(
            record,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        return hmac_new(
            self._integrity_key,
            b"\0".join((_SOURCE_STORE_MAC_DOMAIN, ENGINE_NAME.encode("ascii"), payload)),
            sha256,
        ).hexdigest()

    def _metadata_bytes(self, record: dict[str, Any]) -> bytes:
        sealed = dict(record)
        sealed["integrityMac"] = self._metadata_mac(record)
        return json.dumps(
            sealed,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

    @staticmethod
    def _directory_flags() -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        return flags

    @staticmethod
    def _file_flags() -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        return flags

    @staticmethod
    def _read_child(dir_fd: int, name: str, *, max_bytes: int) -> bytes:
        fd: int | None = None
        try:
            fd = os.open(name, EngineSourceStore._file_flags(), dir_fd=dir_fd)
            observed = os.fstat(fd)
            if not stat.S_ISREG(observed.st_mode) or not 1 <= observed.st_size <= max_bytes:
                raise SourceDeliveryReceiverError("source_store_state_invalid")
            chunks: list[bytes] = []
            total = 0
            while True:
                remaining = max_bytes + 1 - total
                if remaining <= 0:
                    raise SourceDeliveryReceiverError("source_store_state_invalid")
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise SourceDeliveryReceiverError("source_store_state_invalid")
                chunks.append(chunk)
            return b"".join(chunks)
        except SourceDeliveryReceiverError:
            raise
        except OSError:
            raise SourceDeliveryReceiverError("source_store_state_invalid") from None
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    raise SourceDeliveryReceiverError("source_store_state_invalid") from None

    def _read_dir(self, path: Path, *, persistence_state: str) -> EngineStoredSource:
        dir_fd: int | None = None
        try:
            dir_fd = os.open(path, self._directory_flags())
            observed = os.fstat(dir_fd)
            if not stat.S_ISDIR(observed.st_mode):
                raise SourceDeliveryReceiverError("source_store_state_invalid")
            raw_meta = self._read_child(dir_fd, "metadata.json", max_bytes=64 * 1024)
            raw_source = self._read_child(
                dir_fd,
                "source.bin",
                max_bytes=SOURCE_DELIVERY_MAX_BYTES,
            )
            value = json.loads(raw_meta.decode("ascii"))
        except SourceDeliveryReceiverError:
            raise
        except Exception:
            raise SourceDeliveryReceiverError("source_store_state_invalid") from None
        finally:
            if dir_fd is not None:
                try:
                    os.close(dir_fd)
                except OSError:
                    raise SourceDeliveryReceiverError("source_store_state_invalid") from None
        if type(value) is not dict or set(value) != {
            "version",
            "engine",
            "jobId",
            "runId",
            "dispatchIdentitySha256",
            "sourceArtifactId",
            "sourceBytes",
            "sourceSha256",
            "sourceMediaType",
            "integrityMac",
        }:
            raise SourceDeliveryReceiverError("source_store_state_invalid")
        observed_mac = value.pop("integrityMac")
        if (
            type(observed_mac) is not str
            or _SHA256_RE.fullmatch(observed_mac) is None
            or not compare_digest(observed_mac, self._metadata_mac(value))
            or value.get("version") != SOURCE_STORE_VERSION
            or value.get("engine") != ENGINE_NAME
        ):
            raise SourceDeliveryReceiverError("source_store_state_invalid")
        return EngineStoredSource(
            engine=ENGINE_NAME,
            job_id=value.get("jobId"),
            run_id=value.get("runId"),
            dispatch_identity_sha256=value.get("dispatchIdentitySha256"),
            source_artifact_id=value.get("sourceArtifactId"),
            source_size_bytes=value.get("sourceBytes"),
            source_sha256=value.get("sourceSha256"),
            source_media_type=value.get("sourceMediaType"),
            persistence_state=persistence_state,
            source_bytes=raw_source,
        )

    def publish(
        self,
        *,
        job_id: str,
        run_id: str,
        dispatch_identity_sha256: str,
        source_artifact_id: str,
        source_bytes: bytes,
        source_sha256: str,
        source_media_type: str,
    ) -> EngineStoredSource:
        if (
            type(dispatch_identity_sha256) is not str
            or _SHA256_RE.fullmatch(dispatch_identity_sha256) is None
            or type(source_artifact_id) is not str
            or _ARTIFACT_ID_RE.fullmatch(source_artifact_id) is None
            or type(source_bytes) is not bytes
            or not 1 <= len(source_bytes) <= SOURCE_DELIVERY_MAX_BYTES
            or type(source_sha256) is not str
            or _SHA256_RE.fullmatch(source_sha256) is None
            or not compare_digest(sha256(source_bytes).hexdigest(), source_sha256)
            or source_media_type not in _ALLOWED_MEDIA_TYPES
        ):
            raise SourceDeliveryReceiverError("source_store_input_invalid")
        final = self._job_dir(job_id, run_id)
        record = {
            "version": SOURCE_STORE_VERSION,
            "engine": ENGINE_NAME,
            "jobId": job_id,
            "runId": run_id,
            "dispatchIdentitySha256": dispatch_identity_sha256,
            "sourceArtifactId": source_artifact_id,
            "sourceBytes": len(source_bytes),
            "sourceSha256": source_sha256,
            "sourceMediaType": source_media_type,
        }
        temp = final.parent / f".{final.name}.{secrets.token_hex(16)}.tmp"
        try:
            temp.mkdir(mode=0o700)
            source_path = temp / "source.bin"
            metadata_path = temp / "metadata.json"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            source_fd = os.open(source_path, flags, 0o400)
            try:
                view = memoryview(source_bytes)
                offset = 0
                while offset < len(view):
                    written = os.write(source_fd, view[offset:])
                    if written <= 0:
                        raise OSError("source_store_write_failed")
                    offset += written
                os.fsync(source_fd)
            finally:
                os.close(source_fd)
            meta_fd = os.open(metadata_path, flags, 0o400)
            try:
                payload = self._metadata_bytes(record)
                offset = 0
                while offset < len(payload):
                    written = os.write(meta_fd, payload[offset:])
                    if written <= 0:
                        raise OSError("source_store_write_failed")
                    offset += written
                os.fsync(meta_fd)
            finally:
                os.close(meta_fd)
            parent_fd = os.open(final.parent, os.O_RDONLY)
            try:
                try:
                    os.rename(temp, final)
                    created = True
                except OSError as exc:
                    if exc.errno in {errno.EEXIST, errno.ENOTEMPTY}:
                        created = False
                    else:
                        raise
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except FileExistsError:
            created = False
        except Exception:
            raise SourceDeliveryReceiverError("source_store_state_invalid") from None
        finally:
            if temp.exists():
                shutil.rmtree(temp, ignore_errors=True)

        stored = self._read_dir(final, persistence_state="written" if created else "replay")
        if (
            stored.job_id != job_id
            or stored.run_id != run_id
            or not compare_digest(stored.dispatch_identity_sha256, dispatch_identity_sha256)
            or stored.source_artifact_id != source_artifact_id
            or stored.source_size_bytes != len(source_bytes)
            or not compare_digest(stored.source_sha256, source_sha256)
            or stored.source_media_type != source_media_type
            or not compare_digest(stored.source_bytes, source_bytes)
        ):
            raise SourceDeliveryReceiverError("source_store_conflict")
        return stored

    def load(self, *, job_id: str, run_id: str) -> EngineStoredSource:
        return self._read_dir(self._job_dir(job_id, run_id), persistence_state="loaded")


@dataclass(frozen=True, slots=True)
class AcceptedSourceDelivery:
    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    source_artifact_id: str
    source_size_bytes: int
    source_sha256: str
    source_media_type: str
    credential_generation_id: str
    timestamp: int
    nonce_sha256: str
    persistence_state: str

    def __post_init__(self) -> None:
        if (
            self.engine != ENGINE_NAME
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or _ARTIFACT_ID_RE.fullmatch(self.source_artifact_id) is None
            or type(self.source_size_bytes) is not int
            or not 1 <= self.source_size_bytes <= SOURCE_DELIVERY_MAX_BYTES
            or _SHA256_RE.fullmatch(self.source_sha256) is None
            or self.source_media_type not in _ALLOWED_MEDIA_TYPES
            or _GENERATION_RE.fullmatch(self.credential_generation_id) is None
            or type(self.timestamp) is not int
            or self.timestamp < 0
            or _SHA256_RE.fullmatch(self.nonce_sha256) is None
            or self.persistence_state not in {"written", "replay"}
        ):
            raise SourceDeliveryReceiverError("source_delivery_result_invalid")

    @property
    def authenticated(self) -> bool:
        return True

    @property
    def trusted_plan_converged(self) -> bool:
        return True

    @property
    def source_persisted(self) -> bool:
        return True

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": SOURCE_DELIVERY_VERSION,
            "environment": SOURCE_DELIVERY_ENVIRONMENT,
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSizeBytes": self.source_size_bytes,
            "sourceSha256": self.source_sha256,
            "sourceMediaType": self.source_media_type,
            "credentialGenerationId": self.credential_generation_id,
            "timestamp": self.timestamp,
            "nonceSha256": self.nonce_sha256,
            "persistenceState": self.persistence_state,
            "authenticated": True,
            "trustedPlanConverged": True,
            "sourcePersisted": True,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
        }


SourceCredentialResolver = Callable[[str, str], bytes | bytearray | memoryview | None]


def source_delivery_credential_key() -> str:
    return ":".join(
        (
            SOURCE_DELIVERY_VERSION,
            SOURCE_DELIVERY_ENVIRONMENT,
            CALLER_SERVICE_IDENTITY,
            ENGINE_NAME,
            AUDIENCE_IDENTITY,
        )
    )


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise SourceDeliveryReceiverError("source_delivery_metadata_invalid") from None


def _expected_identity(plan: dict[str, Any]) -> tuple[dict[str, Any], str]:
    source = plan.get("sourceArtifact")
    runs = plan.get("engineRuns")
    if type(source) is not dict or type(runs) is not list:
        raise SourceDeliveryReceiverError("source_delivery_plan_invalid")
    matching = [run for run in runs if type(run) is dict and run.get("engine") == ENGINE_NAME]
    if len(matching) != 1:
        raise SourceDeliveryReceiverError("source_delivery_plan_invalid")
    run = matching[0]
    expected_artifacts = run.get("expectedArtifacts")
    if type(expected_artifacts) is not list:
        raise SourceDeliveryReceiverError("source_delivery_plan_invalid")
    by_kind = {
        item.get("kind"): item
        for item in expected_artifacts
        if type(item) is dict and type(item.get("kind")) is str
    }
    if set(by_kind) != {"musicxml", "diagnostic"}:
        raise SourceDeliveryReceiverError("source_delivery_plan_invalid")
    payload = {
        "version": "scoremosaic-dispatch-identity-v1",
        "planId": plan.get("planId"),
        "planSha256": plan.get("planSha256"),
        "jobId": plan.get("jobId"),
        "sourceArtifact": {
            "artifactId": source.get("artifactId"),
            "artifactRef": source.get("artifactRef"),
            "sha256": source.get("sha256"),
            "sizeBytes": source.get("sizeBytes"),
            "mediaType": source.get("mediaType"),
        },
        "engineRun": {
            "runId": run.get("runId"),
            "engine": ENGINE_NAME,
            "candidateId": run.get("candidateId"),
            "candidateNamespace": run.get("candidateNamespace"),
            "expectedArtifacts": [
                {
                    "kind": "musicxml",
                    "artifactId": by_kind["musicxml"].get("artifactId"),
                },
                {
                    "kind": "diagnostic",
                    "artifactId": by_kind["diagnostic"].get("artifactId"),
                },
            ],
        },
    }
    return payload, sha256(_canonical_json(payload)).hexdigest()


def _headers(headers: Sequence[tuple[str, str]]) -> dict[str, str]:
    if type(headers) not in {tuple, list}:
        raise SourceDeliveryReceiverError("source_delivery_headers_invalid")
    result: dict[str, str] = {}
    for pair in headers:
        if type(pair) is not tuple or len(pair) != 2:
            raise SourceDeliveryReceiverError("source_delivery_headers_invalid")
        name, value = pair
        if type(name) is not str or type(value) is not str:
            raise SourceDeliveryReceiverError("source_delivery_headers_invalid")
        lowered = name.lower()
        if (
            lowered in result
            or name != name.strip()
            or value != value.strip()
            or not name
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name + value)
        ):
            raise SourceDeliveryReceiverError("source_delivery_headers_invalid")
        result[lowered] = value
    if tuple(result) != SOURCE_DELIVERY_HEADER_NAMES:
        raise SourceDeliveryReceiverError("source_delivery_headers_invalid")
    return result


def _positive_decimal(value: str, *, maximum: int) -> int:
    if not value.isdigit() or value.startswith("0"):
        raise SourceDeliveryReceiverError("source_delivery_headers_invalid")
    parsed = int(value, 10)
    if not 1 <= parsed <= maximum:
        raise SourceDeliveryReceiverError("source_delivery_headers_invalid")
    return parsed


def _select_generation(rotation: SourceDeliveryRotation, generation: str, now_seconds: int) -> None:
    if generation == rotation.current_generation_id:
        if now_seconds < rotation.current_activated_at:
            raise SourceDeliveryReceiverError("source_delivery_generation_invalid")
        return
    if (
        rotation.previous_generation_id is not None
        and generation == rotation.previous_generation_id
        and rotation.previous_valid_until is not None
        and now_seconds <= rotation.previous_valid_until
    ):
        return
    raise SourceDeliveryReceiverError("source_delivery_generation_invalid")


def _source_signature_valid(source_bytes: bytes, media_type: str) -> bool:
    if media_type == "application/pdf":
        return source_bytes.startswith(b"%PDF-")
    if media_type == "image/png":
        return source_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return source_bytes.startswith(b"\xff\xd8\xff")
    return False


def accept_source_delivery(
    *,
    authority: EngineReceiverAuthority,
    store: EngineSourceStore,
    rotation: SourceDeliveryRotation,
    headers: Sequence[tuple[str, str]],
    body: bytes,
    now_seconds: int,
    credential_resolver: SourceCredentialResolver,
) -> AcceptedSourceDelivery:
    if (
        type(authority) is not EngineReceiverAuthority
        or type(store) is not EngineSourceStore
        or type(rotation) is not SourceDeliveryRotation
        or type(body) is not bytes
        or type(now_seconds) is not int
        or now_seconds < 0
        or not callable(credential_resolver)
    ):
        raise SourceDeliveryReceiverError("source_delivery_input_invalid")

    parsed = _headers(headers)
    generation = parsed["x-scoremosaic-source-generation"]
    timestamp_text = parsed["x-scoremosaic-source-timestamp"]
    nonce = parsed["x-scoremosaic-source-nonce"]
    job_id = parsed["x-scoremosaic-source-job"]
    run_id = parsed["x-scoremosaic-source-run"]
    dispatch_sha = parsed["x-scoremosaic-source-dispatch-sha256"]
    artifact_id = parsed["x-scoremosaic-source-artifact"]
    source_size = _positive_decimal(
        parsed["x-scoremosaic-source-bytes"],
        maximum=SOURCE_DELIVERY_MAX_BYTES,
    )
    source_sha = parsed["x-scoremosaic-source-sha256"]
    media_type = parsed["x-scoremosaic-source-media-type"]
    signature = parsed["x-scoremosaic-source-signature"]

    if (
        not timestamp_text.isdigit()
        or timestamp_text.startswith("0")
        or type(nonce) is not str
        or _NONCE_RE.fullmatch(nonce) is None
        or _JOB_ID_RE.fullmatch(job_id) is None
        or _RUN_ID_RE.fullmatch(run_id) is None
        or _SHA256_RE.fullmatch(dispatch_sha) is None
        or _ARTIFACT_ID_RE.fullmatch(artifact_id) is None
        or _SHA256_RE.fullmatch(source_sha) is None
        or media_type not in _ALLOWED_MEDIA_TYPES
        or _SHA256_RE.fullmatch(signature) is None
    ):
        raise SourceDeliveryReceiverError("source_delivery_headers_invalid")
    timestamp = int(timestamp_text, 10)
    if (
        timestamp > now_seconds + SOURCE_DELIVERY_MAX_FUTURE_SKEW_SECONDS
        or now_seconds - timestamp > SOURCE_DELIVERY_MAX_AGE_SECONDS
    ):
        raise SourceDeliveryReceiverError("source_delivery_timestamp_invalid")

    # Semantic convergence is intentionally checked before credential resolution.
    try:
        trusted = authority.load_trusted_plan(job_id=job_id)
        plan = json.loads(trusted.canonical_plan_bytes.decode("ascii"))
    except (EngineReceiverAuthorityError, UnicodeDecodeError, json.JSONDecodeError):
        raise SourceDeliveryReceiverError("source_delivery_plan_invalid") from None
    _, expected_dispatch_sha = _expected_identity(plan)
    source = plan["sourceArtifact"]
    run = next(run for run in plan["engineRuns"] if run["engine"] == ENGINE_NAME)
    if (
        trusted.run_id != run_id
        or run.get("runId") != run_id
        or not compare_digest(expected_dispatch_sha, dispatch_sha)
        or source.get("artifactId") != artifact_id
        or source.get("sizeBytes") != source_size
        or not compare_digest(str(source.get("sha256")), source_sha)
        or source.get("mediaType") != media_type
    ):
        raise SourceDeliveryReceiverError("source_delivery_plan_mismatch")

    _select_generation(rotation, generation, now_seconds)
    key = source_delivery_credential_key()
    try:
        raw = credential_resolver(key, generation)
    except Exception:
        raise SourceDeliveryReceiverError("source_delivery_credential_unavailable") from None
    if raw is None or type(raw) not in (bytes, bytearray, memoryview):
        raise SourceDeliveryReceiverError("source_delivery_credential_unavailable")
    try:
        raw_size = raw.nbytes if type(raw) is memoryview else len(raw)
        secret = bytes(raw)
    except (BufferError, TypeError, ValueError):
        raise SourceDeliveryReceiverError("source_delivery_credential_unavailable") from None
    if not _MIN_CREDENTIAL_BYTES <= raw_size <= _MAX_CREDENTIAL_BYTES:
        raise SourceDeliveryReceiverError("source_delivery_credential_unavailable")

    metadata = {
        "version": SOURCE_DELIVERY_VERSION,
        "algorithm": SOURCE_DELIVERY_ALGORITHM,
        "environment": SOURCE_DELIVERY_ENVIRONMENT,
        "callerIdentity": CALLER_SERVICE_IDENTITY,
        "engine": ENGINE_NAME,
        "audienceIdentity": AUDIENCE_IDENTITY,
        "credentialKey": key,
        "origin": ENGINE_ORIGIN,
        "method": SOURCE_DELIVERY_METHOD,
        "path": SOURCE_DELIVERY_PATH,
        "credentialGenerationId": generation,
        "timestamp": timestamp,
        "nonce": nonce,
        "jobId": job_id,
        "runId": run_id,
        "dispatchIdentitySha256": dispatch_sha,
        "sourceArtifactId": artifact_id,
        "sourceBytes": source_size,
        "sourceSha256": source_sha,
        "sourceMediaType": media_type,
    }
    message = b"\0".join(
        (_SOURCE_SIGNATURE_DOMAIN, _canonical_json(metadata), source_sha.encode("ascii"))
    )
    expected_signature = hmac_new(secret, message, sha256).hexdigest()
    if not compare_digest(expected_signature, signature):
        raise SourceDeliveryReceiverError("source_delivery_signature_invalid")

    if (
        len(body) != source_size
        or not compare_digest(sha256(body).hexdigest(), source_sha)
        or not _source_signature_valid(body, media_type)
    ):
        raise SourceDeliveryReceiverError("source_delivery_body_invalid")

    stored = store.publish(
        job_id=job_id,
        run_id=run_id,
        dispatch_identity_sha256=dispatch_sha,
        source_artifact_id=artifact_id,
        source_bytes=body,
        source_sha256=source_sha,
        source_media_type=media_type,
    )
    return AcceptedSourceDelivery(
        engine=ENGINE_NAME,
        job_id=job_id,
        run_id=run_id,
        dispatch_identity_sha256=dispatch_sha,
        source_artifact_id=artifact_id,
        source_size_bytes=source_size,
        source_sha256=source_sha,
        source_media_type=media_type,
        credential_generation_id=generation,
        timestamp=timestamp,
        nonce_sha256=sha256(nonce.encode("ascii")).hexdigest(),
        persistence_state=stored.persistence_state,
    )
