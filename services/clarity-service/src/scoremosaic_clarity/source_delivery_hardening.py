"""Mandatory Stage 5-A source-delivery hardening applied at package import.

The underlying source-delivery module stays byte-identical across engines. This
shim closes two security edges before any source-delivery symbol is exposed:
raw metadata must be canonical byte-for-byte, and a credential generation may
only authenticate requests signed inside its own activation interval.
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import source_delivery as _source

_BaseEngineSourceStore = _source.EngineSourceStore
_base_accept_source_delivery = _source.accept_source_delivery
_ACTIVATED = False


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise _source.SourceDeliveryReceiverError("source_store_state_invalid")
        value[key] = item
    return value


class _HardenedEngineSourceStore(_BaseEngineSourceStore):
    """Require the sealed metadata bytes themselves to be canonical."""

    def _read_dir(self, path, *, persistence_state: str):
        dir_fd: int | None = None
        try:
            dir_fd = os.open(path, self._directory_flags())
            raw_meta = self._read_child(dir_fd, "metadata.json", max_bytes=64 * 1024)
            sealed = json.loads(
                raw_meta.decode("ascii"),
                object_pairs_hook=_duplicate_rejecting_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
        except _source.SourceDeliveryReceiverError:
            raise
        except Exception:
            raise _source.SourceDeliveryReceiverError("source_store_state_invalid") from None
        finally:
            if dir_fd is not None:
                try:
                    os.close(dir_fd)
                except OSError:
                    raise _source.SourceDeliveryReceiverError("source_store_state_invalid") from None

        if type(sealed) is not dict or "integrityMac" not in sealed:
            raise _source.SourceDeliveryReceiverError("source_store_state_invalid")
        record = dict(sealed)
        record.pop("integrityMac", None)
        try:
            expected = self._metadata_bytes(record)
        except Exception:
            raise _source.SourceDeliveryReceiverError("source_store_state_invalid") from None
        if raw_meta != expected:
            raise _source.SourceDeliveryReceiverError("source_store_state_invalid")
        return super()._read_dir(path, persistence_state=persistence_state)


def _hardened_accept_source_delivery(*args, **kwargs):
    rotation = kwargs.get("rotation")
    headers = kwargs.get("headers")
    if type(rotation) is not _source.SourceDeliveryRotation:
        raise _source.SourceDeliveryReceiverError("source_delivery_input_invalid")
    parsed = _source._headers(headers)
    generation = parsed["x-scoremosaic-source-generation"]
    timestamp_text = parsed["x-scoremosaic-source-timestamp"]
    if not timestamp_text.isdigit() or timestamp_text.startswith("0"):
        raise _source.SourceDeliveryReceiverError("source_delivery_headers_invalid")
    request_timestamp = int(timestamp_text, 10)

    if (
        generation == rotation.current_generation_id
        and request_timestamp < rotation.current_activated_at
    ):
        raise _source.SourceDeliveryReceiverError("source_delivery_generation_invalid")
    if (
        rotation.previous_generation_id is not None
        and generation == rotation.previous_generation_id
        and request_timestamp >= rotation.current_activated_at
    ):
        raise _source.SourceDeliveryReceiverError("source_delivery_generation_invalid")
    return _base_accept_source_delivery(*args, **kwargs)


def activate() -> None:
    """Install the hardening exactly once before package import completes."""

    global _ACTIVATED
    if _ACTIVATED:
        return
    _source.EngineSourceStore = _HardenedEngineSourceStore
    _source.accept_source_delivery = _hardened_accept_source_delivery
    _ACTIVATED = True
