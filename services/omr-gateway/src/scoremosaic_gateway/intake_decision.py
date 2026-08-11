"""Integrated fail-closed Safe Intake decision over exact immutable input bytes."""

from __future__ import annotations

from dataclasses import dataclass

from .filename_safety import validate_original_filename
from .safe_intake import (
    SAFE_INTAKE_POLICY_VERSION,
    inspect_image_pixels,
    inspect_pdf_pages,
    measure_input_bytes,
    verify_signature_media_type,
)


class SafeIntakeDecisionError(ValueError):
    """Raised when the integrated decision cannot safely evaluate its input."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SafeIntakeDecision:
    """Bounded server-derived evidence returned only after every required gate passes."""

    policy_version: str
    format_id: str
    media_type: str
    observed_bytes: int
    page_count: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    image_pixel_count: int | None = None


def decide_safe_intake(
    payload: bytes,
    *,
    original_filename: str,
    declared_media_type: str | None,
    max_bytes: int,
    max_pages: int,
) -> SafeIntakeDecision:
    """Return one accepted decision only after B.1-B.6 and format checks pass.

    The caller supplies the complete immutable payload, not a separately trusted
    header. The function does not persist bytes, derive a storage path, accept an
    upload, or dispatch work to an engine. Existing fail-closed primitive errors
    propagate unchanged so their stable rejection categories remain authoritative.
    """

    if not isinstance(payload, bytes):
        raise SafeIntakeDecisionError("intake_payload_invalid")

    observed_bytes = measure_input_bytes((payload,), max_bytes)
    signature_match = verify_signature_media_type(payload, declared_media_type)
    validate_original_filename(original_filename, payload)

    if signature_match.format_id == "pdf":
        page_count = inspect_pdf_pages(payload, max_pages=max_pages)
        return SafeIntakeDecision(
            policy_version=SAFE_INTAKE_POLICY_VERSION,
            format_id=signature_match.format_id,
            media_type=signature_match.media_type,
            observed_bytes=observed_bytes,
            page_count=page_count,
        )

    if signature_match.format_id in {"jpeg", "png"}:
        image = inspect_image_pixels(payload)
        if image.format_id != signature_match.format_id:
            raise SafeIntakeDecisionError("intake_evidence_mismatch")
        return SafeIntakeDecision(
            policy_version=SAFE_INTAKE_POLICY_VERSION,
            format_id=signature_match.format_id,
            media_type=signature_match.media_type,
            observed_bytes=observed_bytes,
            image_width=image.width,
            image_height=image.height,
            image_pixel_count=image.pixel_count,
        )

    raise SafeIntakeDecisionError("intake_format_unsupported")
