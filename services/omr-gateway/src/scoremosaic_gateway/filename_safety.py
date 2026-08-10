"""Gate B.6 original filename safety primitive for Safe Intake v1."""

from __future__ import annotations

import re
import unicodedata

from .safe_intake import SAFE_INTAKE_POLICY_V1, match_input_signature


class SafeIntakeFilenameError(ValueError):
    """Raised when original filename metadata violates the B.6 safety policy."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_ORIGINAL_FILENAME_MAX_CHARS = 255
_WINDOWS_DRIVE_PREFIX_PATTERN = re.compile(r"^[A-Za-z]:")
_WINDOWS_UNSAFE_FILENAME_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_STEMS = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)
_UNSAFE_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})


def _format_extensions(format_id: str) -> tuple[str, ...]:
    for format_policy in SAFE_INTAKE_POLICY_V1.formats:
        if format_policy.format_id == format_id:
            return format_policy.extensions
    raise SafeIntakeFilenameError("filename_format_unverified")


def _validate_filename_shape(original_filename: str) -> None:
    if not isinstance(original_filename, str):
        raise SafeIntakeFilenameError("filename_invalid")
    if not original_filename or len(original_filename) > _ORIGINAL_FILENAME_MAX_CHARS:
        raise SafeIntakeFilenameError("filename_invalid")
    if original_filename != original_filename.strip():
        raise SafeIntakeFilenameError("filename_invalid")
    if original_filename in {".", ".."} or original_filename.startswith("."):
        raise SafeIntakeFilenameError("filename_path_unsafe")
    if _WINDOWS_DRIVE_PREFIX_PATTERN.match(original_filename):
        raise SafeIntakeFilenameError("filename_path_unsafe")
    if any(character in _WINDOWS_UNSAFE_FILENAME_CHARS for character in original_filename):
        raise SafeIntakeFilenameError("filename_path_unsafe")
    if original_filename.endswith((".", " ")):
        raise SafeIntakeFilenameError("filename_invalid")
    if any(
        unicodedata.category(character) in _UNSAFE_UNICODE_CATEGORIES
        for character in original_filename
    ):
        raise SafeIntakeFilenameError("filename_invalid")

    device_stem = original_filename.split(".", 1)[0].rstrip(" .").upper()
    if device_stem in _WINDOWS_RESERVED_STEMS:
        raise SafeIntakeFilenameError("filename_path_unsafe")


def validate_original_filename(
    original_filename: str,
    header: bytes | bytearray | memoryview,
) -> str:
    """Validate filename metadata against server-derived signature evidence.

    The filename is metadata only. It is never converted into a filesystem or
    storage path here. The final extension must agree with a fresh B.1 signature
    classification; the extension itself never determines the accepted format.
    """

    _validate_filename_shape(original_filename)
    signature_match = match_input_signature(header)
    allowed_extensions = _format_extensions(signature_match.format_id)

    separator_index = original_filename.rfind(".")
    extension = (
        original_filename[separator_index:].lower()
        if separator_index > 0
        else ""
    )
    if extension not in allowed_extensions:
        raise SafeIntakeFilenameError("filename_extension_mismatch")

    return original_filename
