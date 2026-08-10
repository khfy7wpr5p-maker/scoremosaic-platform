"""Pure Safe Intake v1 format policy and bounded security primitives.

This module does not accept uploads or declare a document safe for processing.
It identifies an allowlisted format from a small caller-supplied header, verifies
that a bounded declared MIME value matches that signature classification, measures
actually observed byte chunks against a bounded request budget, and can inspect
PDF structure/page count in a bounded helper subprocess. Later Gate B stages must
still verify decoded image/pixel budgets, filename safety, and the integrated
intake decision before external upload can be enabled.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys


SAFE_INTAKE_POLICY_VERSION = "1.0"


class SafeIntakeSignatureError(ValueError):
    """Raised when a header cannot match one allowlisted v1 signature."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SafeIntakeMediaTypeError(ValueError):
    """Raised when declared MIME evidence cannot be safely accepted."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SafeIntakeByteBudgetError(ValueError):
    """Raised when observed input bytes cannot satisfy the bounded byte policy."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SafeIntakePdfError(ValueError):
    """Raised when PDF structural/page evidence cannot be safely accepted."""

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

_DECLARED_MEDIA_TYPE_MAX_CHARS = 64
_MEDIA_TYPE_TOKEN = r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+"
_DECLARED_MEDIA_TYPE_PATTERN = re.compile(
    rf"{_MEDIA_TYPE_TOKEN}/{_MEDIA_TYPE_TOKEN}\Z",
    re.ASCII,
)
_ABSOLUTE_MAX_REQUEST_BYTES = 100 * 1024 * 1024
_ABSOLUTE_MAX_PDF_PAGES = 200
_PDF_INSPECTION_TIMEOUT_SECONDS = 2
_PDF_INSPECTOR_MAX_OUTPUT_BYTES = 1024
_PDF_INSPECTOR_ERROR_CODES = frozenset(
    {
        "pdf_structure_invalid",
        "pdf_encrypted_unsupported",
        "pdf_page_budget_exceeded",
    }
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


def _normalize_declared_media_type(declared_media_type: str | None) -> str:
    if declared_media_type is None or declared_media_type == "":
        raise SafeIntakeMediaTypeError("media_type_missing")

    if not isinstance(declared_media_type, str):
        raise SafeIntakeMediaTypeError("media_type_invalid")

    if len(declared_media_type) > _DECLARED_MEDIA_TYPE_MAX_CHARS:
        raise SafeIntakeMediaTypeError("media_type_invalid")

    try:
        declared_media_type.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SafeIntakeMediaTypeError("media_type_invalid") from exc

    if _DECLARED_MEDIA_TYPE_PATTERN.fullmatch(declared_media_type) is None:
        raise SafeIntakeMediaTypeError("media_type_invalid")

    return declared_media_type.lower()


def _validate_byte_limit(max_bytes: int) -> int:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise SafeIntakeByteBudgetError("byte_limit_invalid")
    if not 1 <= max_bytes <= _ABSOLUTE_MAX_REQUEST_BYTES:
        raise SafeIntakeByteBudgetError("byte_limit_invalid")
    return max_bytes


def _byte_chunk_size(chunk: bytes | bytearray | memoryview) -> int:
    if not isinstance(chunk, (bytes, bytearray, memoryview)):
        raise SafeIntakeByteBudgetError("byte_chunk_invalid")

    view = memoryview(chunk)
    if view.ndim != 1 or view.itemsize != 1:
        raise SafeIntakeByteBudgetError("byte_chunk_invalid")
    return view.nbytes


def _validate_pdf_page_limit(max_pages: int) -> int:
    if isinstance(max_pages, bool) or not isinstance(max_pages, int):
        raise SafeIntakePdfError("pdf_page_limit_invalid")
    if not 1 <= max_pages <= _ABSOLUTE_MAX_PDF_PAGES:
        raise SafeIntakePdfError("pdf_page_limit_invalid")
    return max_pages


def _bounded_pdf_bytes(pdf_bytes: bytes) -> bytes:
    if not isinstance(pdf_bytes, bytes):
        raise SafeIntakePdfError("pdf_structure_invalid")
    if not pdf_bytes or len(pdf_bytes) > _ABSOLUTE_MAX_REQUEST_BYTES:
        raise SafeIntakePdfError("pdf_structure_invalid")

    try:
        signature_match = match_input_signature(pdf_bytes)
    except (SafeIntakeSignatureError, TypeError) as exc:
        raise SafeIntakePdfError("pdf_structure_invalid") from exc
    if signature_match.format_id != "pdf":
        raise SafeIntakePdfError("pdf_structure_invalid")
    return pdf_bytes


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


def verify_signature_media_type(
    header: bytes | bytearray | memoryview,
    declared_media_type: str | None,
) -> SignatureMatch:
    """Bind declared MIME evidence to a fresh match of the supplied header bytes."""

    normalized_media_type = _normalize_declared_media_type(declared_media_type)
    signature_match = match_input_signature(header)

    if normalized_media_type not in SAFE_INTAKE_MEDIA_TYPES:
        raise SafeIntakeMediaTypeError("media_type_unsupported")

    if normalized_media_type != signature_match.media_type:
        raise SafeIntakeMediaTypeError("signature_media_type_mismatch")

    return signature_match


def measure_input_bytes(
    chunks: Iterable[bytes | bytearray | memoryview],
    max_bytes: int,
) -> int:
    """Count observed byte chunks and fail immediately when the budget is exceeded."""

    limit = _validate_byte_limit(max_bytes)
    try:
        iterator = iter(chunks)
    except TypeError as exc:
        raise SafeIntakeByteBudgetError("byte_chunk_invalid") from exc

    observed_bytes = 0
    for chunk in iterator:
        observed_bytes += _byte_chunk_size(chunk)
        if observed_bytes > limit:
            raise SafeIntakeByteBudgetError("byte_budget_exceeded")

    return observed_bytes


def inspect_pdf_pages(
    pdf_bytes: bytes,
    *,
    max_pages: int,
) -> int:
    """Strictly inspect exact immutable PDF bytes in a bounded helper."""

    page_limit = _validate_pdf_page_limit(max_pages)
    payload = _bounded_pdf_bytes(pdf_bytes)
    worker_path = Path(__file__).with_name("pdf_inspector_worker.py")

    try:
        completed = subprocess.run(
            [sys.executable, str(worker_path), str(page_limit)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=_PDF_INSPECTION_TIMEOUT_SECONDS,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise SafeIntakePdfError("pdf_inspection_timeout") from exc
    except OSError as exc:
        raise SafeIntakePdfError("pdf_structure_invalid") from exc

    if completed.returncode != 0:
        raise SafeIntakePdfError("pdf_structure_invalid")
    if len(completed.stdout) > _PDF_INSPECTOR_MAX_OUTPUT_BYTES:
        raise SafeIntakePdfError("pdf_structure_invalid")

    try:
        result = json.loads(completed.stdout.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SafeIntakePdfError("pdf_structure_invalid") from exc

    if not isinstance(result, dict) or set(result) - {"status", "code", "page_count"}:
        raise SafeIntakePdfError("pdf_structure_invalid")

    if result.get("status") == "error":
        code = result.get("code")
        if code in _PDF_INSPECTOR_ERROR_CODES:
            raise SafeIntakePdfError(code)
        raise SafeIntakePdfError("pdf_structure_invalid")

    if result.get("status") != "ok" or set(result) != {"status", "page_count"}:
        raise SafeIntakePdfError("pdf_structure_invalid")

    page_count = result.get("page_count")
    if isinstance(page_count, bool) or not isinstance(page_count, int):
        raise SafeIntakePdfError("pdf_structure_invalid")
    if not 1 <= page_count <= page_limit:
        raise SafeIntakePdfError("pdf_structure_invalid")
    return page_count
