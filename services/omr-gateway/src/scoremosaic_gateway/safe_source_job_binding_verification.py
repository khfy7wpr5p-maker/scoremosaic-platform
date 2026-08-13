"""Gate E.4 closure verification for exact E.4B -> E.4C trust handoff.

This module creates no new source/job authority. It independently rebuilds the
existing E.4C binding from exact E.4B finalization evidence and requires the
supplied E.4C decision to match that authoritative derivation exactly.
"""

from __future__ import annotations

from .safe_source_job_binding import (
    SafeSourceJobBindingDecision,
    SafeSourceJobBindingError,
    bind_finalized_source_to_job,
)
from .safe_upload_finalization import SafeUploadFinalizationDecision


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

    if decision != expected:
        raise SafeSourceJobBindingError("source_binding_invalid")
