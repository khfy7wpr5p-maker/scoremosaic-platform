"""Gate D.2 durable idempotency contract foundation.

This module adds no database, object storage, queue, replay store, storage write,
network transport, receiver route, or orchestration activation. It models an
immutable in-memory idempotency ledger for the existing Gate D.1 job/run state
machine and binds every slot to the exact C.2-C dispatch identity plus the
current D.1 revision.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from .durable_job_state import (
    DurableJobStateError,
    DurableJobStateSnapshot,
    transition_durable_job_state,
    validate_durable_job_state_transition,
)

DURABLE_IDEMPOTENCY_CONTRACT_VERSION = "scoremosaic-durable-idempotency-v1"

_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_SLOT_PATTERN = re.compile(r"^idem_[a-f0-9]{24}$")
_BOUNDARIES = {
    "persistenceEnabled": False,
    "storageWritesEnabled": False,
    "queueEnabled": False,
    "networkDispatchEnabled": False,
    "orchestrationEnabled": False,
}


class DurableIdempotencyError(ValueError):
    """Bounded failure for the Gate D.2 idempotency contract."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require_snapshot(snapshot: object) -> DurableJobStateSnapshot:
    if type(snapshot) is not DurableJobStateSnapshot:
        raise DurableIdempotencyError("snapshot_invalid")
    return snapshot


def _require_next_state(next_state: object) -> str:
    if type(next_state) is not str:
        raise DurableIdempotencyError("transition_invalid")
    return next_state


def _slot_id(dispatch_identity_sha256: str, revision: int) -> str:
    digest = hashlib.sha256(
        _canonical_json(
            {
                "version": DURABLE_IDEMPOTENCY_CONTRACT_VERSION,
                "dispatchIdentitySha256": dispatch_identity_sha256,
                "revision": revision,
            }
        )
    ).hexdigest()
    return f"idem_{digest[:24]}"


def _request_sha256(
    snapshot: DurableJobStateSnapshot,
    next_state: str,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "version": DURABLE_IDEMPOTENCY_CONTRACT_VERSION,
                "slotId": _slot_id(
                    snapshot.dispatch_identity_sha256,
                    snapshot.revision,
                ),
                "dispatchIdentitySha256": snapshot.dispatch_identity_sha256,
                "fromState": snapshot.state,
                "fromRevision": snapshot.revision,
                "toState": next_state,
            }
        )
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class DurableIdempotencyRecord:
    """One immutable server-derived idempotency decision record."""

    slot_id: str
    request_sha256: str
    from_state: str
    from_revision: int
    to_state: str
    result_state: str
    result_revision: int

    def __post_init__(self) -> None:
        if type(self.slot_id) is not str or not _SLOT_PATTERN.fullmatch(self.slot_id):
            raise DurableIdempotencyError("record_invalid")
        if (
            type(self.request_sha256) is not str
            or not _SHA256_PATTERN.fullmatch(self.request_sha256)
        ):
            raise DurableIdempotencyError("record_invalid")
        if type(self.from_state) is not str or type(self.to_state) is not str:
            raise DurableIdempotencyError("record_invalid")
        if type(self.result_state) is not str:
            raise DurableIdempotencyError("record_invalid")
        if type(self.from_revision) is not int or self.from_revision < 0:
            raise DurableIdempotencyError("record_invalid")
        if type(self.result_revision) is not int:
            raise DurableIdempotencyError("record_invalid")
        if self.result_revision != self.from_revision + 1:
            raise DurableIdempotencyError("record_invalid")
        if self.result_state != self.to_state:
            raise DurableIdempotencyError("record_invalid")

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "slotId": self.slot_id,
            "requestSha256": self.request_sha256,
            "fromState": self.from_state,
            "fromRevision": self.from_revision,
            "toState": self.to_state,
            "resultState": self.result_state,
            "resultRevision": self.result_revision,
        }


@dataclass(frozen=True, slots=True)
class DurableIdempotencyLedger:
    """Immutable D.2 ledger bound to one exact C.2-C dispatch identity."""

    version: str
    dispatch_identity_sha256: str
    records: tuple[DurableIdempotencyRecord, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != DURABLE_IDEMPOTENCY_CONTRACT_VERSION
        ):
            raise DurableIdempotencyError("ledger_invalid")
        if (
            type(self.dispatch_identity_sha256) is not str
            or not _SHA256_PATTERN.fullmatch(self.dispatch_identity_sha256)
        ):
            raise DurableIdempotencyError("ledger_invalid")
        if type(self.records) is not tuple:
            raise DurableIdempotencyError("ledger_invalid")

        previous: DurableIdempotencyRecord | None = None
        seen_slots: set[str] = set()
        for record in self.records:
            if type(record) is not DurableIdempotencyRecord:
                raise DurableIdempotencyError("ledger_invalid")
            if record.slot_id in seen_slots:
                raise DurableIdempotencyError("ledger_invalid")
            if record.slot_id != _slot_id(
                self.dispatch_identity_sha256,
                record.from_revision,
            ):
                raise DurableIdempotencyError("ledger_invalid")
            expected_request = hashlib.sha256(
                _canonical_json(
                    {
                        "version": DURABLE_IDEMPOTENCY_CONTRACT_VERSION,
                        "slotId": record.slot_id,
                        "dispatchIdentitySha256": self.dispatch_identity_sha256,
                        "fromState": record.from_state,
                        "fromRevision": record.from_revision,
                        "toState": record.to_state,
                    }
                )
            ).hexdigest()
            if record.request_sha256 != expected_request:
                raise DurableIdempotencyError("ledger_invalid")
            try:
                validate_durable_job_state_transition(
                    record.from_state,
                    record.from_revision,
                    record.to_state,
                )
            except DurableJobStateError:
                raise DurableIdempotencyError("ledger_invalid") from None
            if previous is None:
                if record.from_state != "planned" or record.from_revision != 0:
                    raise DurableIdempotencyError("ledger_invalid")
            else:
                if (
                    record.from_state != previous.result_state
                    or record.from_revision != previous.result_revision
                ):
                    raise DurableIdempotencyError("ledger_invalid")
            seen_slots.add(record.slot_id)
            previous = record

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "recordCount": len(self.records),
            "records": [record.as_safe_dict() for record in self.records],
            "boundaries": dict(_BOUNDARIES),
        }


@dataclass(frozen=True, slots=True)
class DurableIdempotencyResult:
    """Result of one D.2 transition application or exact replay."""

    ledger: DurableIdempotencyLedger
    snapshot: DurableJobStateSnapshot
    replayed: bool

    def __post_init__(self) -> None:
        if type(self.ledger) is not DurableIdempotencyLedger:
            raise DurableIdempotencyError("result_invalid")
        if type(self.snapshot) is not DurableJobStateSnapshot:
            raise DurableIdempotencyError("result_invalid")
        if type(self.replayed) is not bool:
            raise DurableIdempotencyError("result_invalid")
        if self.snapshot.dispatch_identity_sha256 != self.ledger.dispatch_identity_sha256:
            raise DurableIdempotencyError("result_invalid")


def build_durable_idempotency_ledger(
    initial: DurableJobStateSnapshot,
) -> DurableIdempotencyLedger:
    """Create an empty ledger only for the exact initial D.1 snapshot."""

    snapshot = _require_snapshot(initial)
    if snapshot.state != "planned" or snapshot.revision != 0:
        raise DurableIdempotencyError("initial_snapshot_required")
    return DurableIdempotencyLedger(
        version=DURABLE_IDEMPOTENCY_CONTRACT_VERSION,
        dispatch_identity_sha256=snapshot.dispatch_identity_sha256,
    )


def _ledger_tip(ledger: DurableIdempotencyLedger) -> tuple[str, int]:
    if not ledger.records:
        return ("planned", 0)
    last = ledger.records[-1]
    return (last.result_state, last.result_revision)


def apply_durable_transition_idempotently(
    ledger: DurableIdempotencyLedger,
    current: DurableJobStateSnapshot,
    next_state: str,
) -> DurableIdempotencyResult:
    """Apply one D.1 transition once, replay it exactly, or fail closed."""

    if type(ledger) is not DurableIdempotencyLedger:
        raise DurableIdempotencyError("ledger_invalid")
    snapshot = _require_snapshot(current)
    state = _require_next_state(next_state)
    if snapshot.dispatch_identity_sha256 != ledger.dispatch_identity_sha256:
        raise DurableIdempotencyError("dispatch_identity_mismatch")

    slot_id = _slot_id(snapshot.dispatch_identity_sha256, snapshot.revision)
    request_sha256 = _request_sha256(snapshot, state)
    existing = next(
        (record for record in ledger.records if record.slot_id == slot_id),
        None,
    )
    if existing is not None:
        if existing.request_sha256 != request_sha256:
            raise DurableIdempotencyError("idempotency_conflict")
        try:
            replay_snapshot = transition_durable_job_state(snapshot, state)
        except DurableJobStateError:
            raise DurableIdempotencyError("transition_invalid") from None
        if (
            replay_snapshot.state != existing.result_state
            or replay_snapshot.revision != existing.result_revision
        ):
            raise DurableIdempotencyError("ledger_invalid")
        return DurableIdempotencyResult(
            ledger=ledger,
            snapshot=replay_snapshot,
            replayed=True,
        )

    if (snapshot.state, snapshot.revision) != _ledger_tip(ledger):
        raise DurableIdempotencyError("idempotency_state_mismatch")

    try:
        result_snapshot = transition_durable_job_state(snapshot, state)
    except DurableJobStateError:
        raise DurableIdempotencyError("transition_invalid") from None

    record = DurableIdempotencyRecord(
        slot_id=slot_id,
        request_sha256=request_sha256,
        from_state=snapshot.state,
        from_revision=snapshot.revision,
        to_state=state,
        result_state=result_snapshot.state,
        result_revision=result_snapshot.revision,
    )
    updated_ledger = DurableIdempotencyLedger(
        version=ledger.version,
        dispatch_identity_sha256=ledger.dispatch_identity_sha256,
        records=ledger.records + (record,),
    )
    return DurableIdempotencyResult(
        ledger=updated_ledger,
        snapshot=result_snapshot,
        replayed=False,
    )
