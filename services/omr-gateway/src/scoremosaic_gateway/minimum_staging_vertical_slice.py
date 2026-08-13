"""Minimum provider-backed staging slice from E.3C admission to immutable source.

This is the first bounded runtime integration after Gate E.4 contract/convergence
closure. It deliberately starts from one exact E.3C admission decision, then uses
stateful staging-only filesystem providers for E.4A reservation, E.4B Safe Intake
finalization, E.4C source/job binding verification, and one immutable source write.

It does not register a public HTTP route, enable engine dispatch/orchestration, or
select a production database/object-store provider.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import os
from pathlib import Path
import secrets
import stat

from .external_admission import ExternalAdmissionDecision
from .safe_source_job_binding import (
    SafeSourceJobBindingDecision,
    SafeSourceJobBindingError,
    bind_finalized_source_to_job,
)
from .safe_source_job_binding_verification import verify_safe_source_job_binding_decision
from .safe_upload_finalization import (
    SafeUploadFinalizationDecision,
    SafeUploadFinalizationError,
    SafeUploadFinalizationReceipt,
    SafeUploadFinalizationRequest,
    finalize_safe_upload_session,
)
from .safe_upload_session import (
    SafeUploadSessionDecision,
    SafeUploadSessionError,
    SafeUploadSessionPolicy,
    SafeUploadSessionReservationReceipt,
    SafeUploadSessionReservationRequest,
    reserve_safe_upload_session,
)


_MAX_STATE_RECORD_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_STATE_INTEGRITY_KEY_BYTES = 32
_STATE_INTEGRITY_MAC_FIELD = "state_integrity_mac"
_STATE_INTEGRITY_DOMAIN = b"scoremosaic-minimum-staging-state-v1"
_STATE_RECORD_KINDS = frozenset({"session", "finalization"})
_TEMP_CREATE_ATTEMPTS = 8


class MinimumStagingVerticalSliceError(ValueError):
    """Stable fail-closed minimum staging slice failure category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _decode_record(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception:
        raise MinimumStagingVerticalSliceError("staging_state_corrupt") from None
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise MinimumStagingVerticalSliceError("staging_state_corrupt")
    return value


@dataclass(frozen=True, slots=True)
class MinimumStagingVerticalSliceResult:
    """Bounded result of one staging source-ingest execution."""

    session: SafeUploadSessionDecision
    finalization: SafeUploadFinalizationDecision
    binding: SafeSourceJobBindingDecision
    source_write_state: str

    def __post_init__(self) -> None:
        if type(self.session) is not SafeUploadSessionDecision:
            raise MinimumStagingVerticalSliceError("staging_result_invalid")
        if type(self.finalization) is not SafeUploadFinalizationDecision:
            raise MinimumStagingVerticalSliceError("staging_result_invalid")
        if type(self.binding) is not SafeSourceJobBindingDecision:
            raise MinimumStagingVerticalSliceError("staging_result_invalid")
        if type(self.source_write_state) is not str or self.source_write_state not in {
            "written",
            "replay",
        }:
            raise MinimumStagingVerticalSliceError("staging_result_invalid")

    @property
    def job_id(self) -> str:
        return self.binding.job_id

    @property
    def source_artifact_id(self) -> str:
        return self.binding.source_artifact_id

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def orchestration_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "environment": "staging",
            "sessionId": self.session.session_id,
            "finalizationId": self.finalization.finalization_id,
            "jobId": self.binding.job_id,
            "sourceArtifactId": self.binding.source_artifact_id,
            "documentSha256": self.binding.document_sha256,
            "sourceWriteState": self.source_write_state,
            "immutableSourceWritten": True,
            "publicHttpUploadEnabled": False,
            "networkDispatchAllowed": False,
            "orchestrationAllowed": False,
        }


class StagingUploadProvider:
    """Stateful local staging provider with authenticated create-once records."""

    def __init__(self, root: Path, *, state_integrity_key: bytes) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise MinimumStagingVerticalSliceError("staging_root_invalid")
        if (
            type(state_integrity_key) is not bytes
            or len(state_integrity_key) != _STATE_INTEGRITY_KEY_BYTES
        ):
            raise MinimumStagingVerticalSliceError("staging_integrity_key_invalid")
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if root.is_symlink() or not root.is_dir():
                raise MinimumStagingVerticalSliceError("staging_root_invalid")
        except MinimumStagingVerticalSliceError:
            raise
        except OSError:
            raise MinimumStagingVerticalSliceError("staging_state_unavailable") from None
        try:
            root_stat = root.stat(follow_symlinks=False)
        except OSError:
            raise MinimumStagingVerticalSliceError("staging_state_unavailable") from None
        if not stat.S_ISDIR(root_stat.st_mode):
            raise MinimumStagingVerticalSliceError("staging_root_invalid")
        self._root = root
        self._root_identity = (root_stat.st_dev, root_stat.st_ino)
        self._state_integrity_key = bytes(state_integrity_key)

    def _state_record_mac(self, *, kind: str, record: dict[str, object]) -> str:
        if type(kind) is not str or kind not in _STATE_RECORD_KINDS:
            raise MinimumStagingVerticalSliceError("staging_state_corrupt")
        if type(record) is not dict or _STATE_INTEGRITY_MAC_FIELD in record:
            raise MinimumStagingVerticalSliceError("staging_state_corrupt")
        message = b"\0".join(
            (
                _STATE_INTEGRITY_DOMAIN,
                kind.encode("ascii"),
                _canonical_json_bytes(record),
            )
        )
        return hmac_new(self._state_integrity_key, message, sha256).hexdigest()

    def _seal_state_record(
        self,
        *,
        kind: str,
        record: dict[str, object],
    ) -> dict[str, object]:
        sealed = dict(record)
        sealed[_STATE_INTEGRITY_MAC_FIELD] = self._state_record_mac(
            kind=kind,
            record=record,
        )
        return sealed

    def _verify_state_record(
        self,
        *,
        kind: str,
        record: dict[str, object],
    ) -> dict[str, object]:
        if type(record) is not dict:
            raise MinimumStagingVerticalSliceError("staging_state_corrupt")
        stored_mac = record.get(_STATE_INTEGRITY_MAC_FIELD)
        if type(stored_mac) is not str:
            raise MinimumStagingVerticalSliceError("staging_state_corrupt")
        payload = dict(record)
        payload.pop(_STATE_INTEGRITY_MAC_FIELD, None)
        expected_mac = self._state_record_mac(kind=kind, record=payload)
        if not compare_digest(stored_mac, expected_mac):
            raise MinimumStagingVerticalSliceError("staging_state_corrupt")
        return payload

    @staticmethod
    def _directory_open_flags() -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        return flags

    @staticmethod
    def _file_read_flags() -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        return flags

    @staticmethod
    def _file_create_flags() -> int:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        return flags

    @staticmethod
    def _path_error(exc: OSError) -> MinimumStagingVerticalSliceError:
        if exc.errno in {
            errno.ENOENT,
            errno.ENOTDIR,
            getattr(errno, "ELOOP", -1),
        }:
            return MinimumStagingVerticalSliceError("staging_path_invalid")
        return MinimumStagingVerticalSliceError("staging_state_unavailable")

    def _relative_path(self, path: Path) -> Path:
        if not isinstance(path, Path):
            raise MinimumStagingVerticalSliceError("staging_path_invalid")
        try:
            relative = path.relative_to(self._root)
        except ValueError:
            raise MinimumStagingVerticalSliceError("staging_path_invalid") from None
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or "." in relative.parts
        ):
            raise MinimumStagingVerticalSliceError("staging_path_invalid")
        return relative

    def _open_root_fd(self) -> int:
        try:
            fd = os.open(self._root, self._directory_open_flags())
        except OSError as exc:
            raise self._path_error(exc) from None
        try:
            root_stat = os.fstat(fd)
            if not stat.S_ISDIR(root_stat.st_mode):
                raise MinimumStagingVerticalSliceError("staging_root_invalid")
            if (root_stat.st_dev, root_stat.st_ino) != self._root_identity:
                raise MinimumStagingVerticalSliceError("staging_root_invalid")
            return fd
        except MinimumStagingVerticalSliceError:
            os.close(fd)
            raise
        except OSError:
            try:
                os.close(fd)
            except OSError:
                pass
            raise MinimumStagingVerticalSliceError("staging_state_unavailable") from None

    def _open_directory_chain(self, relative: Path, *, create: bool) -> int:
        if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
            raise MinimumStagingVerticalSliceError("staging_path_invalid")
        current_fd = self._open_root_fd()
        try:
            for part in relative.parts:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    except OSError as exc:
                        raise self._path_error(exc) from None
                try:
                    next_fd = os.open(
                        part,
                        self._directory_open_flags(),
                        dir_fd=current_fd,
                    )
                except OSError as exc:
                    raise self._path_error(exc) from None
                try:
                    if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                        raise MinimumStagingVerticalSliceError("staging_path_invalid")
                except MinimumStagingVerticalSliceError:
                    os.close(next_fd)
                    raise
                except OSError:
                    try:
                        os.close(next_fd)
                    except OSError:
                        pass
                    raise MinimumStagingVerticalSliceError(
                        "staging_state_unavailable"
                    ) from None
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except MinimumStagingVerticalSliceError:
            try:
                os.close(current_fd)
            except OSError:
                pass
            raise
        except OSError:
            try:
                os.close(current_fd)
            except OSError:
                pass
            raise MinimumStagingVerticalSliceError("staging_state_unavailable") from None

    def _open_parent_fd(self, path: Path, *, create: bool) -> tuple[int, str]:
        relative = self._relative_path(path)
        leaf = relative.name
        if (
            type(leaf) is not str
            or not leaf
            or leaf in {".", ".."}
            or "/" in leaf
            or "\\" in leaf
        ):
            raise MinimumStagingVerticalSliceError("staging_path_invalid")
        return self._open_directory_chain(relative.parent, create=create), leaf

    def _read_file_no_follow(
        self,
        path: Path,
        *,
        max_bytes: int,
        overflow_category: str,
    ) -> bytes:
        if type(max_bytes) is not int or max_bytes < 0:
            raise MinimumStagingVerticalSliceError("staging_state_unavailable")
        parent_fd, leaf = self._open_parent_fd(path, create=False)
        fd: int | None = None
        try:
            try:
                fd = os.open(leaf, self._file_read_flags(), dir_fd=parent_fd)
            except OSError as exc:
                raise self._path_error(exc) from None
            try:
                file_stat = os.fstat(fd)
            except OSError:
                raise MinimumStagingVerticalSliceError(
                    "staging_state_unavailable"
                ) from None
            if not stat.S_ISREG(file_stat.st_mode):
                raise MinimumStagingVerticalSliceError("staging_path_invalid")

            chunks: list[bytes] = []
            observed = 0
            while True:
                remaining_with_sentinel = max_bytes + 1 - observed
                if remaining_with_sentinel <= 0:
                    raise MinimumStagingVerticalSliceError(overflow_category)
                try:
                    chunk = os.read(
                        fd,
                        min(_READ_CHUNK_BYTES, remaining_with_sentinel),
                    )
                except OSError:
                    raise MinimumStagingVerticalSliceError(
                        "staging_state_unavailable"
                    ) from None
                if not chunk:
                    return b"".join(chunks)
                observed += len(chunk)
                if observed > max_bytes:
                    raise MinimumStagingVerticalSliceError(overflow_category)
                chunks.append(chunk)
        finally:
            close_failed = False
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    close_failed = True
            try:
                os.close(parent_fd)
            except OSError:
                close_failed = True
            if close_failed:
                raise MinimumStagingVerticalSliceError(
                    "staging_state_unavailable"
                ) from None

    def _create_temp_file(self, parent_fd: int) -> tuple[int, str]:
        for _ in range(_TEMP_CREATE_ATTEMPTS):
            leaf = f".scoremosaic-{secrets.token_hex(16)}"
            try:
                fd = os.open(
                    leaf,
                    self._file_create_flags(),
                    0o600,
                    dir_fd=parent_fd,
                )
                return fd, leaf
            except FileExistsError:
                continue
        raise OSError(errno.EEXIST, "temporary staging name collision")

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise OSError(errno.EIO, "staging write made no progress")
            offset += written

    def _atomic_create(self, path: Path, payload: bytes) -> bool:
        parent_fd, final_leaf = self._open_parent_fd(path, create=True)
        temp_fd: int | None = None
        temp_leaf: str | None = None
        try:
            try:
                temp_fd, temp_leaf = self._create_temp_file(parent_fd)
                os.fchmod(temp_fd, 0o600)
                self._write_all(temp_fd, payload)
                os.fsync(temp_fd)
                os.close(temp_fd)
                temp_fd = None
                try:
                    os.link(
                        temp_leaf,
                        final_leaf,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                    return True
                except FileExistsError:
                    return False
            except MinimumStagingVerticalSliceError:
                raise
            except OSError:
                raise MinimumStagingVerticalSliceError(
                    "staging_state_unavailable"
                ) from None
        finally:
            close_failed = False
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    close_failed = True
            if temp_leaf is not None:
                try:
                    os.unlink(temp_leaf, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    close_failed = True
            try:
                os.close(parent_fd)
            except OSError:
                close_failed = True
            if close_failed:
                raise MinimumStagingVerticalSliceError(
                    "staging_state_unavailable"
                ) from None

    def _session_path(self, session_id: str) -> Path:
        return self._root / "state" / "sessions" / f"{session_id}.json"

    def _finalization_path(self, session_id: str) -> Path:
        return self._root / "state" / "finalizations" / f"{session_id}.json"

    def _source_path(self, binding: SafeSourceJobBindingDecision) -> Path:
        if type(binding) is not SafeSourceJobBindingDecision:
            raise MinimumStagingVerticalSliceError("staging_source_binding_invalid")
        if getattr(binding, "environment", None) != "staging":
            raise MinimumStagingVerticalSliceError("staging_environment_required")
        try:
            binding.__post_init__()
        except Exception:
            raise MinimumStagingVerticalSliceError("staging_source_binding_invalid") from None
        relative = Path(binding.source_storage_key)
        if relative.is_absolute() or ".." in relative.parts:
            raise MinimumStagingVerticalSliceError("staging_path_invalid")
        return self._root / "objects" / relative

    @staticmethod
    def _session_record(request: SafeUploadSessionReservationRequest) -> dict[str, object]:
        return {
            "version": request.version,
            "session_id": request.session_id,
            "admission_binding_id": request.admission_binding_id,
            "principal_id": request.principal_id,
            "environment": request.environment,
            "operation_id": request.operation_id,
            "request_sha256": request.request_sha256,
            "request_bytes": request.request_bytes,
            "max_bytes": request.max_bytes,
            "max_pages": request.max_pages,
            "allowed_media_types": list(request.allowed_media_types),
            "created_at_epoch_s": request.requested_at_epoch_s,
            "expires_at_epoch_s": request.requested_at_epoch_s
            + request.session_ttl_seconds,
        }

    def reserve_session(
        self,
        request: SafeUploadSessionReservationRequest,
    ) -> SafeUploadSessionReservationReceipt:
        if type(request) is not SafeUploadSessionReservationRequest:
            raise MinimumStagingVerticalSliceError("staging_session_request_invalid")
        try:
            request.__post_init__()
        except Exception:
            raise MinimumStagingVerticalSliceError("staging_session_request_invalid") from None
        if request.environment != "staging":
            raise MinimumStagingVerticalSliceError("staging_environment_required")

        path = self._session_path(request.session_id)
        new_record = self._session_record(request)
        sealed_new_record = self._seal_state_record(kind="session", record=new_record)
        created = self._atomic_create(path, _canonical_json_bytes(sealed_new_record))
        record = (
            new_record
            if created
            else self._verify_state_record(
                kind="session",
                record=_decode_record(
                    self._read_file_no_follow(
                        path,
                        max_bytes=_MAX_STATE_RECORD_BYTES,
                        overflow_category="staging_state_corrupt",
                    )
                ),
            )
        )
        required_keys = set(new_record)
        if set(record) != required_keys or record.get("version") != request.version:
            raise MinimumStagingVerticalSliceError("staging_state_corrupt")
        try:
            allowed_media_types = tuple(record["allowed_media_types"])
            receipt = SafeUploadSessionReservationReceipt(
                session_id=record["session_id"],
                admission_binding_id=record["admission_binding_id"],
                principal_id=record["principal_id"],
                environment=record["environment"],
                operation_id=record["operation_id"],
                request_sha256=record["request_sha256"],
                request_bytes=record["request_bytes"],
                max_bytes=record["max_bytes"],
                max_pages=record["max_pages"],
                allowed_media_types=allowed_media_types,
                created_at_epoch_s=record["created_at_epoch_s"],
                expires_at_epoch_s=record["expires_at_epoch_s"],
                outcome="reserved" if created else "replay",
            )
        except Exception:
            raise MinimumStagingVerticalSliceError("staging_state_corrupt") from None
        return receipt

    @staticmethod
    def _finalization_record(request: SafeUploadFinalizationRequest) -> dict[str, object]:
        return {
            "version": request.version,
            "session_id": request.session_id,
            "admission_binding_id": request.admission_binding_id,
            "principal_id": request.principal_id,
            "environment": request.environment,
            "operation_id": request.operation_id,
            "finalization_id": request.finalization_id,
            "document_sha256": request.document_sha256,
            "intake_policy_version": request.intake_policy_version,
            "observed_bytes": request.observed_bytes,
            "format_id": request.format_id,
            "media_type": request.media_type,
            "page_count": request.page_count,
            "image_width": request.image_width,
            "image_height": request.image_height,
            "image_pixel_count": request.image_pixel_count,
            "finalized_at_epoch_s": request.requested_at_epoch_s,
        }

    @staticmethod
    def _finalization_receipt(
        record: dict[str, object],
        *,
        outcome: str,
    ) -> SafeUploadFinalizationReceipt:
        try:
            return SafeUploadFinalizationReceipt(
                version=record["version"],
                session_id=record["session_id"],
                admission_binding_id=record["admission_binding_id"],
                principal_id=record["principal_id"],
                environment=record["environment"],
                operation_id=record["operation_id"],
                finalization_id=record["finalization_id"],
                document_sha256=record["document_sha256"],
                intake_policy_version=record["intake_policy_version"],
                observed_bytes=record["observed_bytes"],
                format_id=record["format_id"],
                media_type=record["media_type"],
                page_count=record["page_count"],
                image_width=record["image_width"],
                image_height=record["image_height"],
                image_pixel_count=record["image_pixel_count"],
                finalized_at_epoch_s=record["finalized_at_epoch_s"],
                outcome=outcome,
            )
        except Exception:
            raise MinimumStagingVerticalSliceError("staging_state_corrupt") from None

    def finalize_session(
        self,
        request: SafeUploadFinalizationRequest,
    ) -> SafeUploadFinalizationReceipt:
        if type(request) is not SafeUploadFinalizationRequest:
            raise MinimumStagingVerticalSliceError("staging_finalization_request_invalid")
        try:
            request.__post_init__()
        except Exception:
            raise MinimumStagingVerticalSliceError("staging_finalization_request_invalid") from None
        if request.environment != "staging":
            raise MinimumStagingVerticalSliceError("staging_environment_required")

        path = self._finalization_path(request.session_id)
        new_record = self._finalization_record(request)
        sealed_new_record = self._seal_state_record(
            kind="finalization",
            record=new_record,
        )
        created = self._atomic_create(path, _canonical_json_bytes(sealed_new_record))
        if created:
            return self._finalization_receipt(new_record, outcome="reserved")

        stored = self._verify_state_record(
            kind="finalization",
            record=_decode_record(
                self._read_file_no_follow(
                    path,
                    max_bytes=_MAX_STATE_RECORD_BYTES,
                    overflow_category="staging_state_corrupt",
                )
            ),
        )
        if set(stored) != set(new_record):
            raise MinimumStagingVerticalSliceError("staging_state_corrupt")
        comparable_keys = set(new_record) - {"finalized_at_epoch_s"}
        exact_replay = all(stored[key] == new_record[key] for key in comparable_keys)
        if exact_replay:
            return self._finalization_receipt(stored, outcome="replay")

        conflict = dict(new_record)
        return self._finalization_receipt(conflict, outcome="conflict")

    def write_source(
        self,
        *,
        binding: SafeSourceJobBindingDecision,
        finalization: SafeUploadFinalizationDecision,
        payload: bytes,
    ) -> str:
        if type(binding) is not SafeSourceJobBindingDecision:
            raise MinimumStagingVerticalSliceError("staging_source_binding_invalid")
        if type(finalization) is not SafeUploadFinalizationDecision:
            raise MinimumStagingVerticalSliceError("staging_source_binding_invalid")
        if (
            getattr(binding, "environment", None) != "staging"
            or getattr(finalization, "environment", None) != "staging"
        ):
            raise MinimumStagingVerticalSliceError("staging_environment_required")
        if type(payload) is not bytes:
            raise MinimumStagingVerticalSliceError("staging_source_payload_invalid")
        try:
            verify_safe_source_job_binding_decision(binding, finalization=finalization)
        except SafeSourceJobBindingError:
            raise MinimumStagingVerticalSliceError("staging_source_binding_invalid") from None
        if (
            len(payload) != binding.source_size_bytes
            or sha256(payload).hexdigest() != binding.document_sha256
        ):
            raise MinimumStagingVerticalSliceError("staging_source_payload_mismatch")

        path = self._source_path(binding)
        created = self._atomic_create(path, payload)
        if created:
            return "written"
        existing = self._read_file_no_follow(
            path,
            max_bytes=binding.source_size_bytes,
            overflow_category="staging_source_collision",
        )
        if (
            len(existing) != binding.source_size_bytes
            or sha256(existing).hexdigest() != binding.document_sha256
            or existing != payload
        ):
            raise MinimumStagingVerticalSliceError("staging_source_collision")
        return "replay"

    def read_source(self, binding: SafeSourceJobBindingDecision) -> bytes:
        path = self._source_path(binding)
        existing = self._read_file_no_follow(
            path,
            max_bytes=binding.source_size_bytes,
            overflow_category="staging_source_collision",
        )
        if (
            len(existing) != binding.source_size_bytes
            or sha256(existing).hexdigest() != binding.document_sha256
        ):
            raise MinimumStagingVerticalSliceError("staging_source_collision")
        return existing


def run_minimum_staging_vertical_slice(
    *,
    admission: ExternalAdmissionDecision,
    session_policy: SafeUploadSessionPolicy,
    payload: bytes,
    original_filename: str,
    declared_media_type: str,
    observed_at_epoch_s: int,
    provider: StagingUploadProvider,
) -> MinimumStagingVerticalSliceResult:
    """Execute the smallest staging-only E.3C -> E.4 -> immutable-source path."""

    if type(admission) is not ExternalAdmissionDecision:
        raise MinimumStagingVerticalSliceError("staging_admission_invalid")
    if getattr(admission, "environment", None) != "staging":
        raise MinimumStagingVerticalSliceError("staging_environment_required")
    if type(session_policy) is not SafeUploadSessionPolicy:
        raise MinimumStagingVerticalSliceError("staging_session_policy_invalid")
    if getattr(session_policy, "environment", None) != "staging":
        raise MinimumStagingVerticalSliceError("staging_environment_required")
    if type(provider) is not StagingUploadProvider:
        raise MinimumStagingVerticalSliceError("staging_provider_invalid")
    if type(payload) is not bytes:
        raise MinimumStagingVerticalSliceError("staging_source_payload_invalid")

    try:
        session = reserve_safe_upload_session(
            policy=session_policy,
            admission=admission,
            observed_at_epoch_s=observed_at_epoch_s,
            reserver=provider.reserve_session,
        )
    except SafeUploadSessionError as exc:
        raise MinimumStagingVerticalSliceError(
            "staging_upload_session_failed"
        ) from exc

    try:
        finalization = finalize_safe_upload_session(
            session=session,
            payload=payload,
            original_filename=original_filename,
            declared_media_type=declared_media_type,
            observed_at_epoch_s=observed_at_epoch_s,
            finalizer=provider.finalize_session,
        )
    except SafeUploadFinalizationError as exc:
        category = (
            "staging_upload_finalization_conflict"
            if exc.category == "upload_finalization_conflict"
            else "staging_upload_finalization_failed"
        )
        raise MinimumStagingVerticalSliceError(category) from exc

    try:
        binding = bind_finalized_source_to_job(finalization)
        verify_safe_source_job_binding_decision(binding, finalization=finalization)
    except SafeSourceJobBindingError as exc:
        raise MinimumStagingVerticalSliceError("staging_source_binding_failed") from exc

    source_write_state = provider.write_source(
        binding=binding,
        finalization=finalization,
        payload=payload,
    )
    return MinimumStagingVerticalSliceResult(
        session=session,
        finalization=finalization,
        binding=binding,
        source_write_state=source_write_state,
    )
