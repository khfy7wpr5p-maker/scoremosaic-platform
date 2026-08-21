"""Hardening for Stage 5-B3a execution-trigger replay classification.

The base trigger intentionally collapses receiver-authority replay/state errors.
This layer safely rechecks the already-reserved exact replay key so an intact
exact replay is reported as reconciliation-required while corrupt durable state
remains a server-state failure. No process can be started by this recheck.
"""
from __future__ import annotations

from hashlib import sha256

from . import authenticated_execution_trigger as _target
from .receiver_authority import EngineReceiverAuthorityError

_ORIGINAL_ACCEPT = _target.accept_authenticated_execution_trigger
_ACTIVATED = False


def _accept_hardened(*args, **kwargs):
    try:
        return _ORIGINAL_ACCEPT(*args, **kwargs)
    except _target.AuthenticatedExecutionTriggerError as exc:
        if exc.category != "execution_trigger_replay_or_state_invalid":
            raise

        authority = kwargs.get("authority")
        headers = kwargs.get("headers")
        body = kwargs.get("body")
        try:
            parsed = _target._headers(headers)
            generation = parsed["x-scoremosaic-execution-generation"]
            timestamp = int(parsed["x-scoremosaic-execution-timestamp"], 10)
            nonce = parsed["x-scoremosaic-execution-nonce"]
            payload_sha = sha256(body).hexdigest()
            replay_key = _target._replay_key(generation, timestamp, nonce, payload_sha)
            authority.reserve_replay(
                replay_key=replay_key,
                credential_generation_id=generation,
                request_timestamp=timestamp,
                replay_expires_at=timestamp + _target.EXECUTION_TRIGGER_REPLAY_SECONDS,
            )
        except EngineReceiverAuthorityError as state_exc:
            if state_exc.category == "receiver_authority_replay_detected":
                raise _target.AuthenticatedExecutionTriggerError(
                    "execution_trigger_reconciliation_required"
                ) from None
            raise exc from None
        except Exception:
            raise exc from None

        # Reaching here would mean the replay reservation unexpectedly became
        # creatable after the base receiver rejected it. Fail closed as state.
        raise exc from None


def activate() -> None:
    global _ACTIVATED
    if _ACTIVATED:
        return
    _target.accept_authenticated_execution_trigger = _accept_hardened
    _ACTIVATED = True
