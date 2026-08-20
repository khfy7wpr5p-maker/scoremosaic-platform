"""Hardened presence checks for controlled-staging transition records.

This module grants no transition, queue, worker, dispatch, orchestration, or
engine authority. It only answers whether exact server-derived transition
records are present while callers hold the existing job-scoped staging lock.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
import re
import stat

from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError,
    StagingUploadProvider,
)

_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_SUPPORTED_REVISIONS = (1, 2)


class ControlledStagingTransitionStateError(ValueError):
    """Fail-closed transition-presence inspection error."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def transition_record_path(
    provider: StagingUploadProvider,
    *,
    job_id: str,
    run_id: str,
    revision: int = 1,
) -> Path:
    """Derive the exact private staging path for a supported transition record."""

    if type(provider) is not StagingUploadProvider:
        raise ControlledStagingTransitionStateError(
            "transition_state_input_invalid"
        )
    if type(job_id) is not str or _JOB_ID_RE.fullmatch(job_id) is None:
        raise ControlledStagingTransitionStateError(
            "transition_state_input_invalid"
        )
    if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
        raise ControlledStagingTransitionStateError(
            "transition_state_input_invalid"
        )
    if type(revision) is not int or revision not in _SUPPORTED_REVISIONS:
        raise ControlledStagingTransitionStateError(
            "transition_state_input_invalid"
        )
    return (
        provider._root
        / "state"
        / "job_transitions"
        / job_id
        / f"{run_id}-revision-{revision}.json"
    )


def _same_current_parent(
    provider: StagingUploadProvider,
    *,
    path: Path,
    retained_parent_fd: int,
) -> None:
    """Require the retained parent descriptor to remain the canonical parent."""

    current_parent_fd: int | None = None
    try:
        current_parent_fd, current_leaf = provider._open_parent_fd(path, create=False)
        retained = os.fstat(retained_parent_fd)
        current = os.fstat(current_parent_fd)
        if (
            current_leaf != path.name
            or not stat.S_ISDIR(retained.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (retained.st_dev, retained.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise ControlledStagingTransitionStateError(
                "transition_state_path_invalid"
            )
    except ControlledStagingTransitionStateError:
        raise
    except (MinimumStagingVerticalSliceError, OSError):
        raise ControlledStagingTransitionStateError(
            "transition_state_path_invalid"
        ) from None
    finally:
        if current_parent_fd is not None:
            try:
                os.close(current_parent_fd)
            except OSError:
                raise ControlledStagingTransitionStateError(
                    "transition_state_path_invalid"
                ) from None


def _optional_regular_file_exists(
    provider: StagingUploadProvider,
    path: Path,
) -> bool:
    """Check optional state presence without following symlinks.

    Missing path components are the only case treated as absence. Existing
    non-directories, symlinks, descriptor failures, root substitution, and other
    filesystem errors fail closed.
    """

    try:
        relative = provider._relative_path(path)
        current_fd = provider._open_root_fd()
    except MinimumStagingVerticalSliceError:
        raise ControlledStagingTransitionStateError(
            "transition_state_path_invalid"
        ) from None

    try:
        for part in relative.parent.parts:
            try:
                next_fd = os.open(
                    part,
                    provider._directory_open_flags(),
                    dir_fd=current_fd,
                )
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    return False
                raise ControlledStagingTransitionStateError(
                    "transition_state_path_invalid"
                ) from None

            try:
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise ControlledStagingTransitionStateError(
                        "transition_state_path_invalid"
                    )
            except ControlledStagingTransitionStateError:
                try:
                    os.close(next_fd)
                except OSError:
                    pass
                raise
            except OSError:
                try:
                    os.close(next_fd)
                except OSError:
                    pass
                raise ControlledStagingTransitionStateError(
                    "transition_state_path_invalid"
                ) from None

            try:
                os.close(current_fd)
            except OSError:
                try:
                    os.close(next_fd)
                except OSError:
                    pass
                raise ControlledStagingTransitionStateError(
                    "transition_state_path_invalid"
                ) from None
            current_fd = next_fd

        try:
            leaf_stat = os.stat(
                relative.name,
                dir_fd=current_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            _same_current_parent(
                provider,
                path=path,
                retained_parent_fd=current_fd,
            )
            return False
        except OSError:
            raise ControlledStagingTransitionStateError(
                "transition_state_path_invalid"
            ) from None

        if not stat.S_ISREG(leaf_stat.st_mode):
            raise ControlledStagingTransitionStateError(
                "transition_state_path_invalid"
            )
        _same_current_parent(
            provider,
            path=path,
            retained_parent_fd=current_fd,
        )
        return True
    finally:
        try:
            os.close(current_fd)
        except OSError:
            raise ControlledStagingTransitionStateError(
                "transition_state_path_invalid"
            ) from None


def _transition_record_exists_under_lock(
    provider: StagingUploadProvider,
    *,
    job_id: str,
    run_id: str,
    revision: int,
) -> bool:
    """Inspect one exact transition path while the caller holds the job lock."""

    return _optional_regular_file_exists(
        provider,
        transition_record_path(
            provider,
            job_id=job_id,
            run_id=run_id,
            revision=revision,
        ),
    )


def any_transition_record_exists(
    provider: StagingUploadProvider,
    *,
    job_id: str,
    run_ids: tuple[str, ...],
) -> bool:
    """Return whether any exact revision-1 transition exists for the fixed job.

    The whole scan is serialized by the same job lock used by transition writes,
    giving planned recovery one deterministic linearization point.
    """

    if type(provider) is not StagingUploadProvider:
        raise ControlledStagingTransitionStateError(
            "transition_state_input_invalid"
        )
    if type(job_id) is not str or _JOB_ID_RE.fullmatch(job_id) is None:
        raise ControlledStagingTransitionStateError(
            "transition_state_input_invalid"
        )
    if (
        type(run_ids) is not tuple
        or not run_ids
        or any(
            type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None
            for run_id in run_ids
        )
        or len(set(run_ids)) != len(run_ids)
    ):
        raise ControlledStagingTransitionStateError(
            "transition_state_input_invalid"
        )

    try:
        with provider._job_lock(job_id):
            return any(
                _transition_record_exists_under_lock(
                    provider,
                    job_id=job_id,
                    run_id=run_id,
                    revision=1,
                )
                for run_id in run_ids
            )
    except ControlledStagingTransitionStateError:
        raise
    except MinimumStagingVerticalSliceError:
        raise ControlledStagingTransitionStateError(
            "transition_state_path_invalid"
        ) from None
