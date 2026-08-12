"""Gate D.1 durable job/run state-machine foundation.

This module adds no database, object storage, queue, replay store, network
receiver, dispatch transport, or orchestration activation. The current
orchestration contract already defines lifecycle transitions at the engine-run
level, so D.1 deliberately persists no new aggregate job semantics. Instead it
models immutable state snapshots for one exact C.2-C ``DispatchIdentityBinding``
and advances them only through the existing closed run-state transition graph.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .dispatch_identity import (
    DispatchIdentityBinding,
    DispatchIdentityError,
    dispatch_identity_payload,
)

DURABLE_JOB_STATE_CONTRACT_VERSION = "scoremosaic-durable-job-state-v1"

JOB_RUN_STATES = (
    "planned",
    "queued",
    "dispatching",
    "running",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
)
TERMINAL_JOB_RUN_STATES = (
    "completed",
    "failed",
    "cancelled",
    "timed_out",
)

_JOB_RUN_TRANSITIONS = {
    "planned": ("queued", "cancelled"),
    "queued": ("dispatching", "cancelled", "timed_out"),
    "dispatching": ("running", "failed", "cancelled", "timed_out"),
    "running": ("completed", "failed", "cancelled", "timed_out"),
    "completed": (),
    "failed": (),
    "cancelled": (),
    "timed_out": (),
}

# The existing graph is acyclic. Its longest valid path has four transitions:
# planned -> queued -> dispatching -> running -> terminal.
_MAX_REVISION = 4
_VALID_REVISIONS_BY_STATE = {
    "planned": (0,),
    "queued": (1,),
    "dispatching": (2,),
    "running": (3,),
    "completed": (4,),
    "failed": (3, 4),
    "cancelled": (1, 2, 3, 4),
    "timed_out": (2, 3, 4),
}


class DurableJobStateError(ValueError):
    """Bounded failure for the D.1 state-machine contract."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require_dispatch_identity(binding: object) -> DispatchIdentityBinding:
    if type(binding) is not DispatchIdentityBinding:
        raise DurableJobStateError("dispatch_identity_invalid")
    try:
        # Reuse the authoritative C.2-C shape validation and canonical payload.
        dispatch_identity_payload(binding)
    except (DispatchIdentityError, TypeError, ValueError):
        raise DurableJobStateError("dispatch_identity_invalid") from None
    return binding


def _require_state(state: object) -> str:
    if type(state) is not str or state not in JOB_RUN_STATES:
        raise DurableJobStateError("state_invalid")
    return state


def _require_revision(revision: object) -> int:
    if type(revision) is not int or not 0 <= revision <= _MAX_REVISION:
        raise DurableJobStateError("revision_invalid")
    return revision


def validate_durable_job_state_position(state: str, revision: int) -> None:
    """Validate one reachable D.1 state/revision position without doing I/O."""

    current_state = _require_state(state)
    current_revision = _require_revision(revision)
    if current_revision not in _VALID_REVISIONS_BY_STATE[current_state]:
        raise DurableJobStateError("revision_state_mismatch")


def validate_durable_job_state_transition(
    from_state: str,
    from_revision: int,
    next_state: str,
) -> None:
    """Validate one D.1 edge without requiring a dispatch binding or doing I/O."""

    validate_durable_job_state_position(from_state, from_revision)
    current_state = from_state
    current_revision = from_revision

    target_state = _require_state(next_state)
    if target_state not in _JOB_RUN_TRANSITIONS[current_state]:
        raise DurableJobStateError("state_transition_invalid")
    if current_revision + 1 not in _VALID_REVISIONS_BY_STATE[target_state]:
        raise DurableJobStateError("state_transition_invalid")


@dataclass(frozen=True, slots=True)
class DurableJobStateSnapshot:
    """Immutable D.1 snapshot for exactly one C.2-C planned engine run."""

    version: str
    binding: DispatchIdentityBinding
    state: str
    revision: int

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != DURABLE_JOB_STATE_CONTRACT_VERSION
        ):
            raise DurableJobStateError("version_invalid")
        _require_dispatch_identity(self.binding)
        validate_durable_job_state_position(self.state, self.revision)

    @property
    def dispatch_identity_sha256(self) -> str:
        return self.binding.identity_sha256

    @property
    def plan_id(self) -> str:
        return self.binding.plan_id

    @property
    def plan_sha256(self) -> str:
        return self.binding.plan_sha256

    @property
    def job_id(self) -> str:
        return self.binding.job_id

    @property
    def source_artifact_id(self) -> str:
        return self.binding.source_artifact_id

    @property
    def source_sha256(self) -> str:
        return self.binding.source_sha256

    @property
    def run_id(self) -> str:
        return self.binding.run_id

    @property
    def engine(self) -> str:
        return self.binding.engine

    def as_safe_dict(self) -> dict[str, object]:
        """Return bounded provenance/state evidence without transport authority."""

        return {
            "version": self.version,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "jobId": self.job_id,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "runId": self.run_id,
            "engine": self.engine,
            "state": self.state,
            "revision": self.revision,
        }


def build_durable_job_state(
    binding: DispatchIdentityBinding,
) -> DurableJobStateSnapshot:
    """Create the immutable initial D.1 snapshot without performing I/O."""

    validated = _require_dispatch_identity(binding)
    return DurableJobStateSnapshot(
        version=DURABLE_JOB_STATE_CONTRACT_VERSION,
        binding=validated,
        state="planned",
        revision=0,
    )


def transition_durable_job_state(
    current: DurableJobStateSnapshot,
    next_state: str,
) -> DurableJobStateSnapshot:
    """Return the next immutable snapshot or fail closed on any invalid edge."""

    if type(current) is not DurableJobStateSnapshot:
        raise DurableJobStateError("snapshot_invalid")
    validate_durable_job_state_transition(
        current.state,
        current.revision,
        next_state,
    )
    return replace(current, state=next_state, revision=current.revision + 1)