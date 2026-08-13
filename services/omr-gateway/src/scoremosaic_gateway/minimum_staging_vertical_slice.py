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
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

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
    """Stateful local staging provider with create-once records and source bytes."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise MinimumStagingVerticalSliceError("staging_root_invalid")
        if root.exists() and root.is_symlink():
            raise MinimumStagingVerticalSliceError("staging_root_invalid")
        self._root = root

    def _ensure_directory(self, relative: Path) -> Path:
        if relative.is_absolute() or ".." in relative.parts:
            raise MinimumStagingVerticalSliceError("staging_path_invalid")
        current = self._root
        if not current.exists():
            current.mkdir(mode=0o700, parents=True, exist_ok=True)
        if current.is_symlink() or not current.is_dir():
            raise MinimumStagingVerticalSliceError("staging_root_invalid")
        for part in relative.parts:
            current = current / part
            if current.exists():
                if current.is_symlink() or not current.is_dir():
                    raise MinimumStagingVerticalSliceError("staging_path_invalid")
            else:
                current.mkdir(mode=0o700)
        return current

    @staticmethod
    def _read_file_no_follow(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except OSError:
            raise MinimumStagingVerticalSliceError("staging_state_unavailable") from None
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(fd)

    def _atomic_create(self, path: Path, payload: bytes) -> bool:
        parent = self._ensure_directory(path.parent.relative_to(self._root))
        if parent != path.parent:
            raise MinimumStagingVerticalSliceError("staging_path_invalid")
        fd, temp_name = tempfile.mkstemp(prefix=".scoremosaic-", dir=parent)
        temp_path = Path(temp_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_path, path)
                return True
            except FileExistsError:
                return False
            except OSError:
                raise MinimumStagingVerticalSliceError("staging_state_unavailable") from None
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

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
        created = self._atomic_create(path, _canonical_json_bytes(new_record))
        record = new_record if created else _decode_record(self._read_file_no_follow(path))
        required_keys = set(new_record)
        if set(record) != required_keys:
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
        created = self._atomic_create(path, _canonical_json_bytes(new_record))
        if created:
            return self._finalization_receipt(new_record, outcome="reserved")

        stored = _decode_record(self._read_file_no_follow(path))
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
        existing = self._read_file_no_follow(path)
        if (
            len(existing) != binding.source_size_bytes
            or sha256(existing).hexdigest() != binding.document_sha256
            or existing != payload
        ):
            raise MinimumStagingVerticalSliceError("staging_source_collision")
        return "replay"

    def read_source(self, binding: SafeSourceJobBindingDecision) -> bytes:
        return self._read_file_no_follow(self._source_path(binding))


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
