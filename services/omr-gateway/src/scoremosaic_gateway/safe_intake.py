"""Pure Safe Intake v1 format policy and bounded signature matching.

This module does not accept uploads or declare a document safe for processing.
It only identifies an allowlisted format from a small caller-supplied header.
Later Gate B stages must still verify declared MIME, byte/page/pixel budgets,
filename safety, and full document structure before producing an intake decision.
"""

from __future__ import annotations

from dataclasses import dataclass


SAFE_INTAKE_POLICY_VERSION = "1.0"


class SafeIntakeSignatureError(ValueError):
    """Raised when a header cannot match one allowlisted v1 signature."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SafeIntakeFormat:
    format_id: str
    media_type: str
    extensions: tuple[str, ...]
    signatures: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class SafeIntakePolicy:
    schema_version: str
    formats: tuple[SafeIntakeFormat, ...]
    signature_probe_bytes: int


@dataclass(frozen=True, slots=True)
class SignatureMatch:
    """A signature-only classification, not a complete Safe Intake decision."""

    policy_version: str
    format_id: str
    media_type: str


_PDF_VERSION_MARKERS = tuple(
    f"%PDF-1.{minor}".encode("ascii")
    for minor in range(8)
) + (b"%PDF-2.0",)
_PDF_SIGNATURES = tuple(
    version_marker + line_ending
    for version_marker in _PDF_VERSION_MARKERS
    for line_ending in (b"\n", b"\r")
)

SAFE_INTAKE_POLICY_V1 = SafeIntakePolicy(
    schema_version=SAFE_INTAKE_POLICY_VERSION,
    signature_probe_bytes=9,
    formats=(
        SafeIntakeFormat(
            format_id="pdf",
            media_type="application/pdf",
            extensions=(".pdf",),
            signatures=_PDF_SIGNATURES,
        ),
        SafeIntakeFormat(
            format_id="jpeg",
            media_type="image/jpeg",
            extensions=(".jpg", ".jpeg"),
            signatures=(b"\xff\xd8\xff",),
        ),
        SafeIntakeFormat(
            format_id="png",
            media_type="image/png",
            extensions=(".png",),
            signatures=(b"\x89PNG\r\n\x1a\n",),
        ),
    ),
)

SAFE_INTAKE_MEDIA_TYPES = tuple(
    format_policy.media_type
    for format_policy in SAFE_INTAKE_POLICY_V1.formats
)


def _bounded_header(
    header: bytes | bytearray | memoryview,
) -> bytes:
    if not isinstance(header, (bytes, bytearray, memoryview)):
        raise TypeError("header must be a bytes-like object")

    view = memoryview(header)
    if view.ndim != 1 or view.itemsize != 1:
        raise TypeError("header must be a one-dimensional byte buffer")

    return bytes(view[:SAFE_INTAKE_POLICY_V1.signature_probe_bytes])


def match_input_signature(
    header: bytes | bytearray | memoryview,
) -> SignatureMatch:
    """Match one bounded header against the central v1 format allowlist."""

    prefix = _bounded_header(header)
    if not prefix:
        raise SafeIntakeSignatureError("empty_header")

    for format_policy in SAFE_INTAKE_POLICY_V1.formats:
        if any(prefix.startswith(signature) for signature in format_policy.signatures):
            return SignatureMatch(
                policy_version=SAFE_INTAKE_POLICY_V1.schema_version,
                format_id=format_policy.format_id,
                media_type=format_policy.media_type,
            )

    if any(
        signature.startswith(prefix)
        for format_policy in SAFE_INTAKE_POLICY_V1.formats
        for signature in format_policy.signatures
    ):
        raise SafeIntakeSignatureError("truncated_signature")

    raise SafeIntakeSignatureError("unsupported_signature")
