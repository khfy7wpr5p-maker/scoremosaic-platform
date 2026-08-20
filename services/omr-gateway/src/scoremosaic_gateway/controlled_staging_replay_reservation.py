"""Durable staging replay reservation for the authenticated receiver boundary.

This bounded Gate C slice persists only a one-way HMAC-sealed tombstone for the
C.2-D generation-scoped replay key. C.2-E reaches its replay callback only after
semantic identity, generation proof, C.2-A HMAC, observed target, payload, and
request freshness have already passed; this store deliberately does not duplicate
that freshness policy.

Persisted state contains no raw nonce, credential key, credential generation
label, signature, payload, or secret material. The first exact reservation is
accepted. Any later request deriving the same binding+generation+nonce key is
rejected as replay even after the advisory expiry. V1 intentionally performs no
cleanup or nonce reuse: deleting an expired record could resurrect a replay. No
HTTP route, network dispatch, worker, state transition, orchestration, or engine
execution is enabled here.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
from pathlib import Path
import re

from .credential_rotation import (
    MAX_REPLAY_RESERVATION_SECONDS,
    CredentialRotationError,
    GenerationReplayChecker,
    ReplayReservation,
    build_replay_reservation,
)
from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError,
    StagingUploadProvider,
    _MAX_STATE_RECORD_BYTES,
    _decode_record,
)
from .service_auth import EngineAuthBinding


CONTROLLED_STAGING_REPLAY_RESERVATION_VERSION = (
    "scoremosaic-controlled-staging-replay-reservation-v1"
)
REPLAY_RETENTION_MODE = "permanent_tombstone"
_REPLAY_MAC_FIELD = "replay_reservation_integrity_mac"
_REPLAY_MAC_DOMAIN = b"scoremosaic-controlled-staging-replay-reservation-v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_BOUNDARIES = {
    "automaticCleanupAllowed": False,
    "nonceReuseAllowed": False,
    "credentialResolutionAllowed": False,
    "requestSigningAllowed": False,
    "networkDispatchAllowed": False,
    "jobStateMutationAllowed": False,
    "queueRuntimeAllowed": False,
    "workerAllowed": False,
    "orchestrationAllowed": False,
    "engineExecutionAllowed": False,
}
_EXPECTED_RECORD_KEYS = frozenset(
    {
        "version",
        "environment",
        "reservation_key",
        "expires_at",
        "retention_mode",
        "boundaries",
    }
)


class ControlledStagingReplayReservationError(ValueError):
    """Stable fail-closed category for durable staging replay state."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ControlledStagingReplayReservationResult:
    reservation_key: str
    expires_at: int
    accepted: bool
    replay_detected: bool
    persistence_state: str
    retention_mode: str

    def __post_init__(self) -> None:
        if (
            type(self.reservation_key) is not str
            or _SHA256_RE.fullmatch(self.reservation_key) is None
            or type(self.expires_at) is not int
            or self.expires_at < 0
            or type(self.accepted) is not bool
            or type(self.replay_detected) is not bool
            or self.replay_detected is self.accepted
            or type(self.persistence_state) is not str
            or self.persistence_state not in {"written", "existing"}
            or (self.accepted and self.persistence_state != "written")
            or (self.replay_detected and self.persistence_state != "existing")
            or type(self.retention_mode) is not str
            or self.retention_mode != REPLAY_RETENTION_MODE
        ):
            raise ControlledStagingReplayReservationError(
                "staging_replay_result_invalid"
            )

    @property
    def automatic_cleanup_allowed(self) -> bool:
        return False

    @property
    def nonce_reuse_allowed(self) -> bool:
        return False

    @property
    def credential_resolution_allowed(self) -> bool:
        return False

    @property
    def request_signing_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    @property
    def queue_runtime_allowed(self) -> bool:
        return False

    @property
    def worker_allowed(self) -> bool:
        return False

    @property
    def orchestration_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": CONTROLLED_STAGING_REPLAY_RESERVATION_VERSION,
            "environment": "staging",
            "reservationKey": self.reservation_key,
            "expiresAt": self.expires_at,
            "accepted": self.accepted,
            "replayDetected": self.replay_detected,
            "persistenceState": self.persistence_state,
            "retentionMode": self.retention_mode,
            **_EXPECTED_BOUNDARIES,
        }


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        ) from None


def _require_provider(value: object) -> StagingUploadProvider:
    if type(value) is not StagingUploadProvider:
        raise ControlledStagingReplayReservationError(
            "staging_replay_input_invalid"
        )
    return value


def _require_binding(value: object) -> EngineAuthBinding:
    if type(value) is not EngineAuthBinding or value.environment != "staging":
        raise ControlledStagingReplayReservationError(
            "staging_replay_binding_invalid"
        )
    return value


def _require_request_timestamp(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ControlledStagingReplayReservationError(
            "staging_replay_timestamp_invalid"
        )
    return value


def _replay_path(provider: StagingUploadProvider, key: str) -> Path:
    if type(key) is not str or _SHA256_RE.fullmatch(key) is None:
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )
    return (
        provider._root
        / "state"
        / "replay_reservations"
        / key[:2]
        / f"{key}.json"
    )


def _replay_mac(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> str:
    key = getattr(provider, "_state_integrity_key", None)
    if type(key) is not bytes or len(key) != 32:
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )
    if type(record) is not dict or _REPLAY_MAC_FIELD in record:
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )
    message = b"\0".join((_REPLAY_MAC_DOMAIN, _canonical_json_bytes(record)))
    return hmac_new(key, message, sha256).hexdigest()


def _seal_replay(
    provider: StagingUploadProvider,
    record: dict[str, object],
) -> dict[str, object]:
    sealed = dict(record)
    sealed[_REPLAY_MAC_FIELD] = _replay_mac(provider, record)
    return sealed


def _verify_replay(
    provider: StagingUploadProvider,
    sealed: dict[str, object],
) -> dict[str, object]:
    if type(sealed) is not dict or _REPLAY_MAC_FIELD not in sealed:
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )
    observed = sealed.get(_REPLAY_MAC_FIELD)
    if type(observed) is not str or _SHA256_RE.fullmatch(observed) is None:
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )
    record = dict(sealed)
    del record[_REPLAY_MAC_FIELD]
    expected = _replay_mac(provider, record)
    if not compare_digest(observed, expected):
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )
    return record


def _record_from_reservation(reservation: ReplayReservation) -> dict[str, object]:
    return {
        "version": CONTROLLED_STAGING_REPLAY_RESERVATION_VERSION,
        "environment": "staging",
        "reservation_key": reservation.key,
        "expires_at": reservation.expires_at,
        "retention_mode": REPLAY_RETENTION_MODE,
        "boundaries": dict(_EXPECTED_BOUNDARIES),
    }


def _validate_stored_record(record: dict[str, object], expected_key: str) -> int:
    if type(record) is not dict or frozenset(record) != _EXPECTED_RECORD_KEYS:
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )
    expires_at = record.get("expires_at")
    if (
        record.get("version") != CONTROLLED_STAGING_REPLAY_RESERVATION_VERSION
        or record.get("environment") != "staging"
        or record.get("reservation_key") != expected_key
        or type(expires_at) is not int
        or expires_at < 0
        or record.get("retention_mode") != REPLAY_RETENTION_MODE
        or record.get("boundaries") != _EXPECTED_BOUNDARIES
    ):
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )
    return expires_at


def reserve_controlled_staging_generation_replay(
    *,
    provider: StagingUploadProvider,
    binding: EngineAuthBinding,
    generation_id: str,
    nonce: str,
    request_timestamp: int,
) -> ControlledStagingReplayReservationResult:
    """Atomically reserve one already-authenticated generation-scoped nonce."""

    checked_provider = _require_provider(provider)
    checked_binding = _require_binding(binding)
    timestamp = _require_request_timestamp(request_timestamp)

    try:
        reservation = build_replay_reservation(
            checked_binding,
            generation_id,
            nonce,
            request_timestamp=timestamp,
            max_request_age_seconds=MAX_REPLAY_RESERVATION_SECONDS,
        )
    except CredentialRotationError:
        raise ControlledStagingReplayReservationError(
            "staging_replay_contract_invalid"
        ) from None

    path = _replay_path(checked_provider, reservation.key)
    record = _record_from_reservation(reservation)
    sealed_payload = _canonical_json_bytes(_seal_replay(checked_provider, record))
    if len(sealed_payload) > _MAX_STATE_RECORD_BYTES:
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        )

    try:
        created = checked_provider._atomic_create(path, sealed_payload)
        if created:
            return ControlledStagingReplayReservationResult(
                reservation_key=reservation.key,
                expires_at=reservation.expires_at,
                accepted=True,
                replay_detected=False,
                persistence_state="written",
                retention_mode=REPLAY_RETENTION_MODE,
            )

        stored = _verify_replay(
            checked_provider,
            _decode_record(
                checked_provider._read_file_no_follow(
                    path,
                    max_bytes=_MAX_STATE_RECORD_BYTES,
                    overflow_category="staging_state_corrupt",
                )
            ),
        )
        stored_expires_at = _validate_stored_record(stored, reservation.key)
        return ControlledStagingReplayReservationResult(
            reservation_key=reservation.key,
            expires_at=stored_expires_at,
            accepted=False,
            replay_detected=True,
            persistence_state="existing",
            retention_mode=REPLAY_RETENTION_MODE,
        )
    except ControlledStagingReplayReservationError:
        raise
    except MinimumStagingVerticalSliceError:
        raise ControlledStagingReplayReservationError(
            "staging_replay_state_invalid"
        ) from None


def build_controlled_staging_generation_replay_checker(
    *,
    provider: StagingUploadProvider,
) -> GenerationReplayChecker:
    """Return the durable callback used only after C.2-E authentication succeeds."""

    checked_provider = _require_provider(provider)

    def replay_checker(
        binding: EngineAuthBinding,
        generation_id: str,
        nonce: str,
        request_timestamp: int,
    ) -> bool:
        result = reserve_controlled_staging_generation_replay(
            provider=checked_provider,
            binding=binding,
            generation_id=generation_id,
            nonce=nonce,
            request_timestamp=request_timestamp,
        )
        return result.accepted

    return replay_checker
