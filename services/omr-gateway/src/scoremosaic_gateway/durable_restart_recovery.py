"""Gate D.5 deterministic restart-recovery decision foundation.

This module performs no persistence, queueing, process restart, retry, network
request, engine execution, orchestration, upload, approval, or publication
operation. It verifies restored D.1-D.4 evidence for one exact engine run and
returns only a bounded read-only recovery disposition.

The v1 safety rule is deliberately conservative: restart never creates a new
attempt or resumes an in-flight dispatch automatically. ``planned``/``queued``
may be identified as pre-dispatch recovery candidates, while ``dispatching``
and ``running`` require reconciliation. Terminal states are preserved exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .artifact_lifecycle import CandidateArtifactLifecycle
from .durable_artifact_storage import DurableArtifactStorageManifest
from .durable_idempotency import DurableIdempotencyLedger
from .durable_job_state import (
    TERMINAL_JOB_RUN_STATES,
    DurableJobStateError,
    DurableJobStateSnapshot,
    validate_durable_job_state_position,
)
from .durable_provenance import (
    DurableProvenanceChain,
    DurableProvenanceError,
    verify_durable_provenance_chain,
)
from .orchestration import ENGINE_NAMES


DURABLE_RESTART_RECOVERY_CONTRACT_VERSION = (
    "scoremosaic-durable-restart-recovery-v1"
)

_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_JOB_ID_PATTERN = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_RUN_ID_PATTERN = re.compile(r"^run_[a-f0-9]{24}$")
_PRE_DISPATCH_STATES = frozenset({"planned", "queued"})
_AMBIGUOUS_IN_FLIGHT_STATES = frozenset({"dispatching", "running"})
_DISPOSITIONS = frozenset(
    {
        "pre_dispatch_candidate",
        "reconciliation_required",
        "terminal_preserved",
    }
)


class DurableRestartRecoveryError(ValueError):
    """Fail-closed D.5 recovery-contract error with one bounded category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require_snapshot(value: object) -> DurableJobStateSnapshot:
    if type(value) is not DurableJobStateSnapshot:
        raise DurableRestartRecoveryError("snapshot_invalid")
    return value


def _require_ledger(value: object) -> DurableIdempotencyLedger:
    if type(value) is not DurableIdempotencyLedger:
        raise DurableRestartRecoveryError("ledger_invalid")
    return value


def _require_manifest(value: object) -> DurableArtifactStorageManifest:
    if type(value) is not DurableArtifactStorageManifest:
        raise DurableRestartRecoveryError("manifest_invalid")
    return value


def _require_lifecycle(value: object) -> CandidateArtifactLifecycle:
    if type(value) is not CandidateArtifactLifecycle:
        raise DurableRestartRecoveryError("lifecycle_invalid")
    return value


def _require_provenance(value: object) -> DurableProvenanceChain:
    if type(value) is not DurableProvenanceChain:
        raise DurableRestartRecoveryError("provenance_invalid")
    return value


def _ledger_tip(ledger: DurableIdempotencyLedger) -> tuple[str, int]:
    if not ledger.records:
        return ("planned", 0)
    latest = ledger.records[-1]
    return (latest.result_state, latest.result_revision)


def _disposition_for_state(state: str) -> tuple[str, bool, bool]:
    if state in TERMINAL_JOB_RUN_STATES:
        return ("terminal_preserved", True, False)
    if state in _PRE_DISPATCH_STATES:
        return ("pre_dispatch_candidate", False, False)
    if state in _AMBIGUOUS_IN_FLIGHT_STATES:
        return ("reconciliation_required", False, True)
    raise DurableRestartRecoveryError("state_invalid")


@dataclass(frozen=True, slots=True)
class DurableRestartRecoveryDecision:
    """Bounded read-only restart disposition for one exact restored run."""

    version: str
    dispatch_identity_sha256: str
    job_id: str
    run_id: str
    engine: str
    state: str
    revision: int
    storage_manifest_sha256: str
    provenance_chain_sha256: str
    disposition: str
    terminal: bool
    reconciliation_required: bool
    automatic_execution_allowed: bool
    retry_allowed: bool
    network_dispatch_allowed: bool
    state_mutation_allowed: bool

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != DURABLE_RESTART_RECOVERY_CONTRACT_VERSION
        ):
            raise DurableRestartRecoveryError("decision_invalid")
        if (
            type(self.dispatch_identity_sha256) is not str
            or _SHA256_PATTERN.fullmatch(self.dispatch_identity_sha256) is None
            or type(self.storage_manifest_sha256) is not str
            or _SHA256_PATTERN.fullmatch(self.storage_manifest_sha256) is None
            or type(self.provenance_chain_sha256) is not str
            or _SHA256_PATTERN.fullmatch(self.provenance_chain_sha256) is None
        ):
            raise DurableRestartRecoveryError("decision_invalid")
        if (
            type(self.job_id) is not str
            or _JOB_ID_PATTERN.fullmatch(self.job_id) is None
            or type(self.run_id) is not str
            or _RUN_ID_PATTERN.fullmatch(self.run_id) is None
        ):
            raise DurableRestartRecoveryError("decision_invalid")
        if type(self.engine) is not str or self.engine not in ENGINE_NAMES:
            raise DurableRestartRecoveryError("decision_invalid")
        try:
            validate_durable_job_state_position(self.state, self.revision)
        except DurableJobStateError:
            raise DurableRestartRecoveryError("decision_invalid") from None
        if type(self.disposition) is not str or self.disposition not in _DISPOSITIONS:
            raise DurableRestartRecoveryError("decision_invalid")
        if type(self.terminal) is not bool or type(self.reconciliation_required) is not bool:
            raise DurableRestartRecoveryError("decision_invalid")
        if any(
            type(value) is not bool
            for value in (
                self.automatic_execution_allowed,
                self.retry_allowed,
                self.network_dispatch_allowed,
                self.state_mutation_allowed,
            )
        ):
            raise DurableRestartRecoveryError("decision_invalid")
        if any(
            (
                self.automatic_execution_allowed,
                self.retry_allowed,
                self.network_dispatch_allowed,
                self.state_mutation_allowed,
            )
        ):
            raise DurableRestartRecoveryError("decision_authority_invalid")

        expected_disposition, expected_terminal, expected_reconciliation = (
            _disposition_for_state(self.state)
        )
        if (
            self.disposition != expected_disposition
            or self.terminal is not expected_terminal
            or self.reconciliation_required is not expected_reconciliation
        ):
            raise DurableRestartRecoveryError("decision_invalid")

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "jobId": self.job_id,
            "runId": self.run_id,
            "engine": self.engine,
            "state": self.state,
            "revision": self.revision,
            "storageManifestSha256": self.storage_manifest_sha256,
            "provenanceChainSha256": self.provenance_chain_sha256,
            "disposition": self.disposition,
            "terminal": self.terminal,
            "reconciliationRequired": self.reconciliation_required,
            "automaticExecutionAllowed": self.automatic_execution_allowed,
            "retryAllowed": self.retry_allowed,
            "networkDispatchAllowed": self.network_dispatch_allowed,
            "stateMutationAllowed": self.state_mutation_allowed,
        }


def evaluate_durable_restart_recovery(
    snapshot: DurableJobStateSnapshot,
    ledger: DurableIdempotencyLedger,
    manifest: DurableArtifactStorageManifest,
    *,
    lifecycle: CandidateArtifactLifecycle,
    provenance: DurableProvenanceChain,
) -> DurableRestartRecoveryDecision:
    """Verify restored D.1-D.4 evidence and return one non-authoritative decision."""

    checked_snapshot = _require_snapshot(snapshot)
    checked_ledger = _require_ledger(ledger)
    checked_manifest = _require_manifest(manifest)
    checked_lifecycle = _require_lifecycle(lifecycle)
    checked_provenance = _require_provenance(provenance)

    if checked_ledger.dispatch_identity_sha256 != checked_snapshot.dispatch_identity_sha256:
        raise DurableRestartRecoveryError("identity_mismatch")
    if _ledger_tip(checked_ledger) != (
        checked_snapshot.state,
        checked_snapshot.revision,
    ):
        raise DurableRestartRecoveryError("idempotency_state_mismatch")

    try:
        verify_durable_provenance_chain(
            checked_provenance,
            checked_snapshot,
            checked_manifest,
            lifecycle=checked_lifecycle,
        )
    except DurableProvenanceError as exc:
        if exc.category == "identity_mismatch":
            raise DurableRestartRecoveryError("identity_mismatch") from None
        raise DurableRestartRecoveryError("provenance_mismatch") from None

    disposition, terminal, reconciliation_required = _disposition_for_state(
        checked_snapshot.state
    )
    return DurableRestartRecoveryDecision(
        version=DURABLE_RESTART_RECOVERY_CONTRACT_VERSION,
        dispatch_identity_sha256=checked_snapshot.dispatch_identity_sha256,
        job_id=checked_snapshot.job_id,
        run_id=checked_snapshot.run_id,
        engine=checked_snapshot.engine,
        state=checked_snapshot.state,
        revision=checked_snapshot.revision,
        storage_manifest_sha256=checked_manifest.manifest_sha256,
        provenance_chain_sha256=checked_provenance.chain_sha256,
        disposition=disposition,
        terminal=terminal,
        reconciliation_required=reconciliation_required,
        automatic_execution_allowed=False,
        retry_allowed=False,
        network_dispatch_allowed=False,
        state_mutation_allowed=False,
    )