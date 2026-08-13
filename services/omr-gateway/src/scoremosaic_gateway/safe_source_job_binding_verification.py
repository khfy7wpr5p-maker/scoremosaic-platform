"""Gate E.4 closure verification for exact E.4B -> E.4C trust handoff.

This module creates no new source/job authority. It independently rebuilds the
existing E.4C binding from exact E.4B finalization evidence and requires the
supplied E.4C decision to match that authoritative derivation exactly.
"""

from __future__ import annotations

from dataclasses import fields

from .safe_source_job_binding import (
    SafeSourceJobBindingDecision,
    SafeSourceJobBindingError,
    bind_finalized_source_to_job,
)
from .safe_upload_finalization import SafeUploadFinalizationDecision


def _matches_exact_primitive_fields(
    decision: SafeSourceJobBindingDecision,
    expected: SafeSourceJobBindingDecision,
) -> bool:
    for field in fields(SafeSourceJobBindingDecision):
        actual_value = getattr(decision, field.name)
        expected_value = getattr(expected, field.name)
        if type(actual_value) is not type(expected_value):
            return False
        if type(actual_value) not in (str, int):
            return False
        if actual_value != expected_value:
            return False
    return True


def verify_safe_source_job_binding_decision(
    decision: SafeSourceJobBindingDecision,
    *,
    finalization: SafeUploadFinalizationDecision,
) -> None:
    """Fail closed unless E.4C evidence exactly matches fresh E.4B-derived authority."""

    if type(decision) is not SafeSourceJobBindingDecision:
        raise SafeSourceJobBindingError("source_binding_invalid")
    if type(finalization) is not SafeUploadFinalizationDecision:
        raise SafeSourceJobBindingError("source_binding_invalid")

    try:
        decision.__post_init__()
        expected = bind_finalized_source_to_job(finalization)
    except Exception:
        raise SafeSourceJobBindingError("source_binding_invalid") from None

    if not _matches_exact_primitive_fields(decision, expected):
        raise SafeSourceJobBindingError("source_binding_invalid")
